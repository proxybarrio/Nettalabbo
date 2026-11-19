"""Read-only clients for the classic Internet time services.

Daytime (RFC 867, port 13), Time (RFC 868, port 37, TCP or UDP) and SNTP
(RFC 4330 / RFC 5905, UDP port 123). Nothing here changes the system clock.

The server catalogue lists public services documented as active today, and
a separate list of historic servers that may no longer be in service.
"""
from __future__ import annotations

import datetime as dt
import socket
import struct
import time

NTP_EPOCH_OFFSET = 2208988800  # seconds between 1900-01-01 and 1970-01-01
PORTS = {'Daytime': 13, 'TCP': 37, 'UDP': 37, 'SNTP': 123}

# protocols: Daytime = RFC 867 on TCP 13; Time = RFC 868 on port 37; SNTP = UDP 123.
TIME_SERVERS = [
    {'host': 'time.inrim.it', 'protocols': ('SNTP', 'Time', 'Daytime'),
     'note': 'INRiM, Torino. Italian national time (UTC(IT)).'},
    {'host': 'ntp1.inrim.it', 'protocols': ('SNTP',),
     'note': 'INRiM primary NTP server 1.'},
    {'host': 'ntp2.inrim.it', 'protocols': ('SNTP',),
     'note': 'INRiM primary NTP server 2.'},
    {'host': 'time.nist.gov', 'protocols': ('SNTP', 'Time', 'Daytime'),
     'note': 'NIST Internet Time Service, USA (round robin). Please do not poll more than once every 4 seconds.',
     },
    {'host': 'time-a-g.nist.gov', 'protocols': ('SNTP', 'Time', 'Daytime'),
     'note': 'NIST, Gaithersburg, Maryland.'},
    {'host': 'time-a-wwv.nist.gov', 'protocols': ('SNTP', 'Time', 'Daytime'),
     'note': 'NIST, WWV, Fort Collins, Colorado.'},
    {'host': 'it.pool.ntp.org', 'protocols': ('SNTP',),
     'note': 'NTP Pool, Italian zone (volunteer servers).'},
    {'host': 'pool.ntp.org', 'protocols': ('SNTP',),
     'note': 'NTP Pool, nearest volunteer servers.'},
    {'host': 'ptbtime1.ptb.de', 'protocols': ('SNTP',),
     'note': 'PTB, Braunschweig. German national time.'},
    {'host': 'ntp.metas.ch', 'protocols': ('SNTP',),
     'note': 'METAS, Bern. Swiss national time.'},
    {'host': 'ntp.se', 'protocols': ('SNTP',),
     'note': 'Netnod, Sweden (anycast).'},
    {'host': 'time.cloudflare.com', 'protocols': ('SNTP',),
     'note': 'Cloudflare (anycast).'},
    {'host': 'time.google.com', 'protocols': ('SNTP',),
     'note': 'Google Public NTP. Uses leap-second smearing.'},
    {'host': 'time.windows.com', 'protocols': ('SNTP',),
     'note': 'Microsoft.'},
    {'host': 'time.apple.com', 'protocols': ('SNTP',),
     'note': 'Apple.'},
]

HISTORIC_TIME_SERVERS = [
    '198.83.19.241', 'bernina.ethz.ch', 'black-ice.cc.vt.edu', 'clepsydra.dec.com',
    'esavax.esa.lanl.gov', 'fartein.ifi.uio.no', 'harbor.ecn.purdue.edu',
    'ns.arc.nasa.gov', 'ntp.adelaide.edu.au', 'ntp.univ-lyon1.fr',
    'ntp0.strath.ac.uk', 'ntp1.strath.ac.uk', 'salmon.maths.tcd.ie',
]
HISTORIC_NOTE = 'Historic time server. It may no longer be in service.'


class TimeServiceError(Exception):
    pass


def _family_of(protocol):
    return 'Daytime' if protocol == 'Daytime' else ('SNTP' if protocol == 'SNTP' else 'Time')


def suggested_servers(protocol, include_historic=False):
    """Hostnames for a mode ('Daytime', 'TCP', 'UDP' or 'SNTP'), historic ones last."""
    family = _family_of(protocol)
    hosts = [entry['host'] for entry in TIME_SERVERS if family in entry['protocols']]
    return hosts + list(HISTORIC_TIME_SERVERS) if include_historic else hosts


def server_note(host):
    host = (host or '').strip().lower()
    for entry in TIME_SERVERS:
        if entry['host'] == host:
            return entry['note']
    return HISTORIC_NOTE if host in HISTORIC_TIME_SERVERS else ''


def _utc(seconds):
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc)


def _ntp_to_unix(raw64):
    seconds, fraction = struct.unpack('!II', raw64)
    if seconds == 0 and fraction == 0:
        return None
    # Era 0 ends in 2036: values below 2^31 belong to era 1 (RFC 4330 section 3).
    if seconds < 0x80000000:
        seconds += 1 << 32
    return seconds - NTP_EPOCH_OFFSET + fraction / 4294967296.0


def _unix_to_ntp(value):
    seconds = int(value) + NTP_EPOCH_OFFSET
    fraction = int((value - int(value)) * 4294967296.0)
    return struct.pack('!II', seconds & 0xFFFFFFFF, fraction & 0xFFFFFFFF)


def _udp_exchange(host, port, payload, timeout, size, clock=time.time):
    """Send one datagram to each resolved address until a reply arrives."""
    last_error = None
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    except OSError as exc:
        raise TimeServiceError(f'Cannot resolve {host}: {exc}') from exc
    for family, socktype, proto, _canon, address in addresses:
        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.settimeout(timeout)
                sock.connect(address)
                data = payload(clock()) if callable(payload) else payload
                sent_at = clock()
                sock.send(data)
                reply = sock.recv(size)
                return reply, data, sent_at, clock(), address[0]
        except OSError as exc:
            last_error = exc
    raise TimeServiceError(f'No reply from {host}:{port}/udp ({last_error})')


def query_sntp(host, timeout=4.0, clock=time.time):
    """One SNTP v4 client exchange with offset and round-trip delay."""
    request = {}

    def build(now):
        transmit = _unix_to_ntp(now)
        request['transmit'] = transmit
        # LI = 0, VN = 4, Mode = 3 (client); our transmit time lets us match the reply.
        return b'\x23' + 39 * b'\0' + transmit

    reply, _data, t1, t4, address = _udp_exchange(host, PORTS['SNTP'], build, timeout, 512, clock)
    if len(reply) < 48:
        raise TimeServiceError('Incomplete SNTP response')
    li_vn_mode, stratum = reply[0], reply[1]
    mode = li_vn_mode & 0x7
    leap = li_vn_mode >> 6
    if mode != 4:
        raise TimeServiceError(f'Unexpected NTP mode {mode} (expected 4, server)')
    if reply[24:32] != request['transmit']:
        raise TimeServiceError('Reply does not match this request (originate timestamp)')
    reference = reply[12:16]
    if stratum == 0:
        code = reference.decode('ascii', 'replace').strip('\0')
        raise TimeServiceError(f'Server sent Kiss-o\'-Death code {code!r}: stop querying it for now')
    if leap == 3:
        raise TimeServiceError('Server reports its clock is not synchronised (leap indicator 3)')
    t2 = _ntp_to_unix(reply[32:40])
    t3 = _ntp_to_unix(reply[40:48])
    if t2 is None or t3 is None:
        raise TimeServiceError('SNTP response without receive/transmit timestamp')
    offset = ((t2 - t1) + (t3 - t4)) / 2
    delay = (t4 - t1) - (t3 - t2)
    if stratum == 1:
        ref_id = reference.decode('ascii', 'replace').strip('\0') or '?'
    else:
        ref_id = socket.inet_ntoa(reference) if any(reference) else '-'
    return {
        'protocol': 'SNTP', 'host': host, 'address': address,
        'remote_utc': _utc(t3), 'local_utc': _utc(t4),
        'offset': offset, 'delay': delay, 'stratum': stratum,
        'version': (li_vn_mode >> 3) & 0x7, 'reference': ref_id, 'leap': leap,
    }


def query_time_tcp(host, timeout=5.0, clock=time.time):
    t1 = clock()
    try:
        with socket.create_connection((host, PORTS['TCP']), timeout=timeout) as sock:
            sock.settimeout(timeout)
            raw = b''
            while len(raw) < 4:
                chunk = sock.recv(4 - len(raw))
                if not chunk:
                    break
                raw += chunk
            address = sock.getpeername()[0]
    except OSError as exc:
        raise TimeServiceError(f'{host}:37/tcp: {exc}') from exc
    t4 = clock()
    if len(raw) != 4:
        raise TimeServiceError('Incomplete RFC 868 time response')
    return _rfc868_result('TCP', host, address, raw, t1, t4)


def query_time_udp(host, timeout=5.0, clock=time.time):
    reply, _data, t1, t4, address = _udp_exchange(host, PORTS['UDP'], b'', timeout, 8, clock)
    if len(reply) < 4:
        raise TimeServiceError('Incomplete RFC 868 time response')
    return _rfc868_result('UDP', host, address, reply[:4], t1, t4)


def _rfc868_result(protocol, host, address, raw, t1, t4):
    seconds = struct.unpack('!I', raw)[0]
    if seconds < 0x80000000:  # wraps in 2036, same convention as NTP
        seconds += 1 << 32
    remote = seconds - NTP_EPOCH_OFFSET
    midpoint = (t1 + t4) / 2
    return {'protocol': protocol, 'host': host, 'address': address,
            'remote_utc': _utc(remote), 'local_utc': _utc(t4),
            # whole-second resolution: the difference is only indicative
            'offset': remote - midpoint, 'delay': t4 - t1}


def query_daytime(host, timeout=5.0, clock=time.time):
    t1 = clock()
    chunks = []
    try:
        with socket.create_connection((host, PORTS['Daytime']), timeout=timeout) as sock:
            sock.settimeout(timeout)
            address = sock.getpeername()[0]
            while sum(map(len, chunks)) < 1024:
                try:
                    chunk = sock.recv(1024)
                except socket.timeout:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
    except OSError as exc:
        raise TimeServiceError(f'{host}:13/tcp: {exc}') from exc
    text = b''.join(chunks).decode('ascii', 'replace').strip()
    if not text:
        raise TimeServiceError('Daytime server closed the connection without data')
    return {'protocol': 'Daytime', 'host': host, 'address': address,
            'text': text, 'delay': clock() - t1}


QUERIES = {'SNTP': query_sntp, 'TCP': query_time_tcp, 'UDP': query_time_udp,
           'Daytime': query_daytime}


def query(protocol, host, timeout=None):
    function = QUERIES[protocol]
    return function(host) if timeout is None else function(host, timeout)


def query_with_fallback(protocol, first_host, stop=None, include_historic=False,
                        on_attempt=None, query_function=None, timeout=None):
    """Try first_host, then the other documented servers for that protocol.

    Returns (result, attempts) where attempts is a list of (host, error or None).
    Raises TimeServiceError when no server answers.
    """
    query_function = query_function or (lambda h: query(protocol, h, timeout))
    candidates = [first_host] if first_host else []
    for host in suggested_servers(protocol, include_historic):
        if host not in candidates:
            candidates.append(host)
    attempts = []
    for host in candidates:
        if stop is not None and stop.is_set():
            break
        if on_attempt:
            on_attempt(host)
        try:
            result = query_function(host)
        except (TimeServiceError, OSError, ValueError, OverflowError) as exc:
            attempts.append((host, str(exc)))
            continue
        attempts.append((host, None))
        return result, attempts
    raise TimeServiceError('No time server answered: ' +
                           '; '.join(f'{h} ({e})' for h, e in attempts))


def format_result(result):
    lines = [f"Server: {result['host']} [{result['address']}]  ·  {result['protocol']}"]
    if result['protocol'] == 'Daytime':
        lines.append(result['text'])
        lines.append(f"Round trip: {result['delay'] * 1000:.0f} ms")
        return '\n'.join(lines) + '\n'
    lines.append(f"Remote time (UTC): {result['remote_utc'].isoformat(timespec='milliseconds')}")
    lines.append(f"Local time  (UTC): {result['local_utc'].isoformat(timespec='milliseconds')}")
    if result['protocol'] == 'SNTP':
        lines.append(f"Clock offset: {result['offset'] * 1000:+.1f} ms (positive: your clock is behind)")
        lines.append(f"Round trip delay: {result['delay'] * 1000:.1f} ms")
        lines.append(f"Stratum {result['stratum']}  ·  NTP v{result['version']}  ·  reference {result['reference']}")
    else:
        lines.append(f"Approximate offset: {result['offset']:+.1f} s (RFC 868 has one-second resolution)")
        lines.append(f"Round trip: {result['delay'] * 1000:.0f} ms")
    return '\n'.join(lines) + '\n'
