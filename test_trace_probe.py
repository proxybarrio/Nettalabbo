"""Tests for the built-in unprivileged tracer (no root, no external traceroute)."""
import os
import socket
import struct
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import trace_probe as tp


def ipv4_loopback_usable():
    try:
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM).close()
        return True
    except OSError:
        return False


class OffenderParsingTest(unittest.TestCase):
    def test_ipv4_time_exceeded(self):
        ee = tp._EE.pack(113, tp.SO_EE_ORIGIN_ICMP, 11, 0, 0, 0, 0)
        sockaddr = struct.pack('=HH4s8x', socket.AF_INET, 0, socket.inet_aton('192.0.2.7'))
        self.assertEqual(tp._offender(ee + sockaddr, socket.AF_INET), ('192.0.2.7', 11, 0))

    def test_ipv6_time_exceeded(self):
        ee = tp._EE.pack(113, tp.SO_EE_ORIGIN_ICMP6, 3, 0, 0, 0, 0)
        sockaddr = struct.pack('=HHI16sI', socket.AF_INET6, 0, 0,
                               socket.inet_pton(socket.AF_INET6, '2001:db8::7'), 0)
        self.assertEqual(tp._offender(ee + sockaddr, socket.AF_INET6), ('2001:db8::7', 3, 0))

    def test_local_errors_are_ignored(self):
        ee = tp._EE.pack(90, 1, 0, 0, 0, 0, 0)  # SO_EE_ORIGIN_LOCAL
        self.assertIsNone(tp._offender(ee + bytes(16), socket.AF_INET))
        self.assertIsNone(tp._offender(b'short', socket.AF_INET))

    def test_unreachable_flags(self):
        self.assertEqual(tp._unreachable_flag(socket.AF_INET, 3, 0), '!N')
        self.assertEqual(tp._unreachable_flag(socket.AF_INET, 3, 1), '!H')
        self.assertEqual(tp._unreachable_flag(socket.AF_INET, 3, 13), '!X')
        self.assertEqual(tp._unreachable_flag(socket.AF_INET6, 1, 4), '')


@unittest.skipUnless(ipv4_loopback_usable(), 'IPv4 not available')
class LoopbackTraceTest(unittest.TestCase):
    """Real packets to 127.0.0.1 as the current (normally unprivileged) user."""

    def test_udp_reaches_loopback_in_one_hop(self):
        hops = list(tp.Tracer('127.0.0.1', 'UDP', timeout=1).trace())
        self.assertEqual(len(hops), 1)
        hop, address, rtt, reached, flag = hops[0]
        self.assertEqual((hop, address, reached, flag), (1, '127.0.0.1', True, ''))
        self.assertGreaterEqual(rtt, 0)

    def test_auto_uses_available_kinds(self):
        tracer = tp.Tracer('127.0.0.1', 'Auto', timeout=1)
        self.assertIn('UDP', tracer.kinds)
        self.assertEqual(tracer.kinds[0] == 'ICMP', tp.icmp_echo_available())
        self.assertTrue(list(tracer.trace())[-1][3])

    def test_icmp_refused_cleanly_when_not_permitted(self):
        with patch.object(tp, 'icmp_echo_available', return_value=False):
            with self.assertRaisesRegex(tp.TraceError, 'ping_group_range'):
                tp.Tracer('127.0.0.1', 'ICMP')
            self.assertEqual(tp.Tracer('127.0.0.1', 'Auto').kinds, ['UDP'])

    def test_stop_returns_immediately(self):
        stop = threading.Event()
        stop.set()
        self.assertEqual(list(tp.Tracer('127.0.0.1', 'UDP', stop=stop).trace()), [])


class FakeTracer(tp.Tracer):
    """Hops listed in `answers` reply; every other probe stays silent."""

    def __init__(self, answers, **kwargs):
        self.answers = answers
        self.pairs = []
        with patch.object(tp, 'resolve', return_value=(socket.AF_INET, '198.51.100.9')):
            super().__init__('example.test', 'UDP', **kwargs)

    def _send(self, kind, hop):
        mine, other = socket.socketpair()
        self.pairs.append(other)
        if hop in self.answers:
            other.send(b'x')
        return tp._Probe(hop, kind, mine, self.clock(), None)

    def _read(self, probe):
        return self.answers.get(probe.hop)


class TraceLogicTest(unittest.TestCase):
    def test_silent_hops_and_destination(self):
        tracer = FakeTracer({1: ('192.0.2.1', False, ''), 3: ('198.51.100.9', True, '')},
                            timeout=0.5, tries=1)
        result = [(h, a, reached) for h, a, _rtt, reached, _flag in tracer.trace()]
        self.assertEqual(result, [(1, '192.0.2.1', False), (2, None, False), (3, '198.51.100.9', True)])

    def test_stops_after_consecutive_silence(self):
        tracer = FakeTracer({1: ('192.0.2.1', False, '')}, timeout=0.3, tries=1,
                            parallel=16, silent_limit=4, max_hops=30)
        result = list(tracer.trace())
        self.assertEqual(len(result), 5)
        self.assertTrue(tracer.stopped_silent)

    def test_unreachable_ends_trace(self):
        tracer = FakeTracer({1: ('192.0.2.1', False, ''), 2: ('192.0.2.2', False, '!N')},
                            timeout=0.3, tries=1, max_hops=10)
        result = list(tracer.trace())
        self.assertEqual([r[0] for r in result], [1, 2])
        self.assertEqual(result[-1][4], '!N')

    def test_first_hop_and_parallel_order(self):
        answers = {h: (f'192.0.2.{h}', h == 6, '') for h in range(3, 7)}
        tracer = FakeTracer(answers, timeout=0.3, first_hop=3, parallel=4)
        self.assertEqual([r[0] for r in tracer.trace()], [3, 4, 5, 6])


class ErrorsTest(unittest.TestCase):
    def test_unresolvable_host(self):
        with self.assertRaisesRegex(tp.TraceError, 'Cannot resolve'):
            tp.Tracer('no-such-host.invalid')

    def test_missing_address_family_is_explained(self):
        real_socket = socket.socket

        def no_ipv6(family=socket.AF_INET, *args, **kwargs):
            if family == socket.AF_INET6:
                raise OSError(97, 'Address family not supported by protocol')
            return real_socket(family, *args, **kwargs)
        with patch.object(tp, 'resolve', return_value=(socket.AF_INET6, '2001:db8::1')), \
                patch.object(tp.socket, 'socket', side_effect=no_ipv6):
            with self.assertRaisesRegex(tp.TraceError, 'only over IPv6'):
                tp.Tracer('ipv6-only.example')


class TracePageTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'HOME': self.home.name})
        self.env.start()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'No display: {exc}')
        self.root.withdraw()
        import nettalabbo
        self.nettalabbo = nettalabbo
        self.app = nettalabbo.App(self.root)

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.env.stop()
        self.home.cleanup()

    def run_page(self, rows, stopped_silent=False):
        class Fake:
            def __init__(inner, host, stop=None, **settings):
                inner.kinds, inner.address, inner.stopped_silent = ['UDP'], '198.51.100.9', stopped_silent
                inner.thread = threading.current_thread()

            def trace(inner):
                return iter(rows)
        self.app.inputs['Trace_host'].set('example.test')
        with patch.object(self.nettalabbo.trace_probe, 'Tracer', Fake), \
                patch.object(self.nettalabbo.trace_probe, 'reverse_name', return_value='router.test'):
            self.app.execute_network('Trace')
            for _ in range(60):
                self.root.update()
                if 'Trace' not in self.app.tasks:
                    break
                time.sleep(0.05)
            self.root.update()
        tree = self.app.trees['Trace']
        return [tree.item(i)['values'] for i in tree.get_children()], self.app.status['Trace'].get()

    def test_complete_trace(self):
        rows, status = self.run_page([(1, '192.0.2.1', 1.5, False, ''), (2, None, None, False, ''),
                                      (3, '198.51.100.9', 9.25, True, '')])
        self.assertEqual([r[0] for r in rows], [1, 2, 3])
        self.assertEqual(rows[0][1:], ['192.0.2.1', 'router.test', '1.50 ms'])
        self.assertEqual(rows[1][1], '*')
        self.assertEqual(status, 'Completed.')

    def test_settings_are_read_before_the_worker(self):
        with patch.object(self.app, 'native_trace_settings', wraps=self.app.native_trace_settings) as read:
            self.run_page([(1, '198.51.100.9', 1.0, True, '')])
        self.assertEqual(read.call_count, 1)

    def test_filtered_destination_is_explained(self):
        rows, status = self.run_page([(1, '192.0.2.1', 1.0, False, '')] +
                                     [(h, None, None, False, '') for h in range(2, 10)], stopped_silent=True)
        self.assertIn('does not reply', rows[-1][3])
        self.assertIn('Partial', status)

    def test_unreachable_is_explained(self):
        rows, status = self.run_page([(1, '192.0.2.1', 1.0, False, '!N')])
        self.assertIn('network is unreachable', rows[-1][3])
        self.assertIn('unreachable', status)

    def test_errors_appear_in_the_table(self):
        def boom(*args, **kwargs):
            raise RuntimeError('simulated failure')
        with patch.object(self.app, 'run_native_trace', boom):
            rows, _status = self.run_page([])
        self.assertIn('simulated failure', rows[-1][3])


if __name__ == '__main__':
    unittest.main()
