"""Unprivileged traceroute for Linux, without the external traceroute program.

Each probe is sent with a limited TTL (hop limit). Routers that drop it reply
with ICMP "time exceeded"; Linux queues that reply on the sending socket when
IP_RECVERR / IPV6_RECVERR is enabled, together with the router's address
(the "offender"). This is how tracepath works, and it needs no root rights,
no capabilities and no particular traceroute version.

Probe kinds:
  UDP   datagrams to high ports, always available to normal users;
        the destination answers with "port unreachable".
  ICMP  echo requests through Linux ping sockets, available when
        net.ipv4.ping_group_range includes the user's group;
        the destination answers with an echo reply.
Auto sends both and keeps the first answer for each hop.
"""
import ipaddress
import select
import socket
import struct
import time

IP_RECVERR = getattr(socket, 'IP_RECVERR', 11)
IPV6_RECVERR = getattr(socket, 'IPV6_RECVERR', 25)
MSG_ERRQUEUE = getattr(socket, 'MSG_ERRQUEUE', 0x2000)
SO_EE_ORIGIN_ICMP, SO_EE_ORIGIN_ICMP6 = 2, 3
BASE_PORT = 33434
_EE = struct.Struct('=IBBBBII')  # struct sock_extended_err


class TraceError(Exception):
    pass


def resolve(host, prefer_ipv6=False):
    """Return (family, address) of host, IPv4 first unless prefer_ipv6."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_DGRAM)
    except OSError as exc:
        raise TraceError(f'Cannot resolve {host}: {exc}') from exc
    infos.sort(key=lambda info: (info[0] == socket.AF_INET6) != prefer_ipv6)
    family, _, _, _, sockaddr = infos[0]
    return family, sockaddr[0]


def icmp_echo_available(family=socket.AF_INET):
    """True when Linux lets this user open an unprivileged ICMP (ping) socket."""
    proto = socket.IPPROTO_ICMP if family == socket.AF_INET else socket.IPPROTO_ICMPV6
    try:
        socket.socket(family, socket.SOCK_DGRAM, proto).close()
        return True
    except OSError:
        return False


def _offender(cmsg_data, family):
    """Router address and ICMP type/code from a sock_extended_err control message."""
    if len(cmsg_data) < _EE.size:
        return None
    errno_, origin, icmp_type, icmp_code, _pad, _info, _data = _EE.unpack_from(cmsg_data)
    if origin not in (SO_EE_ORIGIN_ICMP, SO_EE_ORIGIN_ICMP6):
        return None
    raw = cmsg_data[_EE.size:]
    address = None
    try:
        if family == socket.AF_INET and len(raw) >= 8:
            address = socket.inet_ntop(socket.AF_INET, raw[4:8])
        elif family == socket.AF_INET6 and len(raw) >= 24:
            address = socket.inet_ntop(socket.AF_INET6, raw[8:24])
    except (OSError, ValueError):
        address = None
    return address, icmp_type, icmp_code


class _Probe:
    def __init__(self, hop, kind, sock, sent_at, ident):
        self.hop, self.kind, self.sock, self.sent_at, self.ident = hop, kind, sock, sent_at, ident


class Tracer:
    """Send probes for a range of hops and collect the first answer for each."""

    def __init__(self, host, method='Auto', max_hops=30, first_hop=1, timeout=2.0,
                 payload_size=32, tries=2, parallel=4, delay=0.0, stop=None,
                 clock=time.monotonic, silent_limit=8):
        self.family, self.address = resolve(host)
        self.max_hops = max(1, min(64, int(max_hops)))
        self.first_hop = max(1, min(self.max_hops, int(first_hop)))
        self.timeout = max(0.5, float(timeout))
        self.payload = b'NETTALABBO-TRACE'.ljust(max(0, min(1400, int(payload_size))), b'.')
        self.tries = max(1, min(3, int(tries)))
        self.parallel = max(1, min(16, int(parallel)))
        self.delay = max(0.0, float(delay))
        self.stop = stop
        self.clock = clock
        try:
            socket.socket(self.family, socket.SOCK_DGRAM).close()
        except OSError as exc:
            kind = 'IPv6' if self.family == socket.AF_INET6 else 'IPv4'
            raise TraceError(f'{host} is reachable only over {kind}, which this computer '
                             f'cannot use ({exc.strerror or exc}).') from exc
        self.kinds = self._kinds(method)
        # Stop after this many consecutive unanswered hops following the last
        # answer: the destination is very likely filtered (0 disables).
        self.silent_limit = max(0, int(silent_limit))
        self.stopped_silent = False
        self._seq = 0

    def _kinds(self, method):
        icmp = icmp_echo_available(self.family)
        if method == 'ICMP':
            if not icmp:
                raise TraceError('ICMP probes are not permitted for this user on this system '
                                 '(net.ipv4.ping_group_range). Use Auto or UDP.')
            return ['ICMP']
        if method == 'UDP':
            return ['UDP']
        return ['ICMP', 'UDP'] if icmp else ['UDP']

    def _stopped(self):
        return self.stop is not None and self.stop.is_set()

    def _open(self, kind, hop):
        v6 = self.family == socket.AF_INET6
        if kind == 'ICMP':
            sock = socket.socket(self.family, socket.SOCK_DGRAM,
                                 socket.IPPROTO_ICMPV6 if v6 else socket.IPPROTO_ICMP)
        else:
            sock = socket.socket(self.family, socket.SOCK_DGRAM)
        if v6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_UNICAST_HOPS, hop)
            sock.setsockopt(socket.IPPROTO_IPV6, IPV6_RECVERR, 1)
        else:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, hop)
            sock.setsockopt(socket.IPPROTO_IP, IP_RECVERR, 1)
        sock.setblocking(False)
        return sock

    def _send(self, kind, hop):
        self._seq += 1
        sock = self._open(kind, hop)
        ident = None
        try:
            if kind == 'ICMP':
                icmp_type = 128 if self.family == socket.AF_INET6 else 8
                header = struct.pack('!BBHHH', icmp_type, 0, 0, 0, self._seq & 0xFFFF)
                sock.sendto(header + self.payload, (self.address, 0))
                ident = self._seq & 0xFFFF
            else:
                port = BASE_PORT + (self._seq % 2000)
                sock.sendto(self.payload, (self.address, port))
        except OSError:
            # Errors such as EHOSTUNREACH are still reported through the error queue.
            pass
        return _Probe(hop, kind, sock, self.clock(), ident)

    def _read(self, probe):
        """Return (address, reached, kind) when the probe got an answer, else None."""
        sock = probe.sock
        level = socket.IPPROTO_IPV6 if self.family == socket.AF_INET6 else socket.IPPROTO_IP
        try:
            _data, ancdata, _flags, _addr = sock.recvmsg(2048, 512, MSG_ERRQUEUE)
            for cmsg_level, _cmsg_type, cmsg_data in ancdata:
                if cmsg_level != level:
                    continue
                found = _offender(cmsg_data, self.family)
                if not found or not found[0]:
                    continue
                address, icmp_type, icmp_code = found
                if self.family == socket.AF_INET:
                    exceeded = icmp_type == 11
                else:
                    exceeded = icmp_type == 3
                reached = (not exceeded) and address == self.address
                flag = '' if exceeded or reached else _unreachable_flag(self.family, icmp_type, icmp_code)
                return address, reached, flag
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            pass
        if probe.kind == 'ICMP':
            try:
                data, peer = sock.recvfrom(2048)
                if data and data[0] in (0, 129):  # echo reply
                    return peer[0], True, ''
            except (BlockingIOError, InterruptedError):
                pass
            except OSError:
                pass  # a queued ICMP error may surface as an exception on recv
        return None

    def trace(self):
        """Yield (hop, address or None, rtt_ms or None, reached, flag) in hop order."""
        results = {}       # hop -> (address, rtt_ms, reached, flag) or None when unanswered
        attempts = {}      # hop -> attempts sent
        outstanding = {}   # hop -> list of open probes of the current attempt
        next_hop, last_hop, emitted = self.first_hop, self.max_hops, self.first_hop
        silent = 0
        try:
            while emitted <= last_hop and not self._stopped():
                while next_hop <= last_hop and len(outstanding) < self.parallel:
                    outstanding[next_hop] = [self._send(kind, next_hop) for kind in self.kinds]
                    attempts[next_hop] = 1
                    next_hop += 1
                    if self.delay:
                        time.sleep(self.delay)
                socks = [p.sock for probes in outstanding.values() for p in probes]
                if socks:
                    ready, _, errored = select.select(socks, [], socks, 0.1)
                    ready = set(ready) | set(errored)
                else:
                    ready = set()
                now = self.clock()
                for hop in sorted(outstanding):
                    probes = outstanding[hop]
                    for probe in probes:
                        if hop in results or probe.sock not in ready:
                            continue
                        answer = self._read(probe)
                        if answer:
                            address, reached, flag = answer
                            results[hop] = (address, (now - probe.sent_at) * 1000.0, reached, flag)
                            if reached or flag:
                                # Destination reached, or an "unreachable" answer:
                                # later hops cannot be traced.
                                last_hop = min(last_hop, hop)
                    if hop in results or hop > last_hop:
                        for probe in probes:
                            probe.sock.close()
                        del outstanding[hop]
                    elif all(now - p.sent_at >= self.timeout for p in probes):
                        for probe in probes:
                            probe.sock.close()
                        if attempts[hop] < self.tries and not self._stopped():
                            attempts[hop] += 1
                            outstanding[hop] = [self._send(kind, hop) for kind in self.kinds]
                        else:
                            results[hop] = None
                            del outstanding[hop]
                while emitted <= last_hop and emitted in results:
                    found = results[emitted]
                    if found is None:
                        silent += 1
                        yield emitted, None, None, False, ''
                    else:
                        silent = 0
                        yield (emitted,) + found
                    emitted += 1
                    if self.silent_limit and silent >= self.silent_limit and emitted <= last_hop:
                        self.stopped_silent = True
                        last_hop = emitted - 1
        finally:
            for probes in outstanding.values():
                for probe in probes:
                    probe.sock.close()


def _unreachable_flag(family, icmp_type, icmp_code):
    """traceroute-style marker for an ICMP unreachable from an intermediate host."""
    if family == socket.AF_INET and icmp_type == 3:
        return {0: '!N', 1: '!H', 2: '!P', 3: '', 9: '!X', 10: '!X', 13: '!X'}.get(icmp_code, f'!<{icmp_code}>')
    if family == socket.AF_INET6 and icmp_type == 1:
        return {0: '!N', 1: '!X', 3: '!H', 4: ''}.get(icmp_code, f'!<{icmp_code}>')
    return ''


def reverse_name(address, timeout=1.5):
    """Best-effort reverse DNS name, '' when none or too slow."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(socket.gethostbyaddr, address)
        try:
            return future.result(timeout=timeout)[0]
        except Exception:
            return ''


def is_valid_target(text):
    text = (text or '').strip()
    if not text or text.startswith('-') or len(text) > 253:
        return False
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return all(part and all(c.isalnum() or c == '-' for c in part) for part in text.rstrip('.').split('.'))


__all__ = ['Tracer', 'TraceError', 'icmp_echo_available', 'resolve', 'reverse_name', 'is_valid_target']
