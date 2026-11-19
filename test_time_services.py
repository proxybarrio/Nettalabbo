"""Offline tests for time_services against local fake servers."""
import socket
import struct
import threading
import unittest
from unittest.mock import patch

import time_services as ts


def ntp_stamp(unix):
    return ts._unix_to_ntp(unix)


class FakeUDP(threading.Thread):
    def __init__(self, respond):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        self.respond = respond

    def run(self):
        data, peer = self.sock.recvfrom(512)
        reply = self.respond(data)
        if reply is not None:
            self.sock.sendto(reply, peer)
        self.sock.close()


class FakeTCP(threading.Thread):
    def __init__(self, payload):
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.payload = payload

    def run(self):
        conn, _ = self.sock.accept()
        conn.sendall(self.payload)
        conn.close()
        self.sock.close()


def sntp_reply(request, server_time, stratum=1, mode=4, leap=0, ref=b'GPS\0', origin=None):
    header = bytes([(leap << 6) | (4 << 3) | mode, stratum, 6, 0xEC]) + 8 * b'\0' + ref
    stamp = ntp_stamp(server_time)
    return header + stamp + (origin if origin is not None else request[40:48]) + stamp + stamp


class SntpTest(unittest.TestCase):
    def run_sntp(self, respond, clock_values):
        server = FakeUDP(respond)
        server.start()
        clock = iter(clock_values).__next__
        with patch.dict(ts.PORTS, {'SNTP': server.port}):
            try:
                return ts.query_sntp('127.0.0.1', timeout=2, clock=clock)
            finally:
                server.join(2)

    def test_offset_and_delay(self):
        # local clock 10 s behind the server, 0.2 s round trip
        result = self.run_sntp(lambda r: sntp_reply(r, 1_800_000_010.1),
                               [1_800_000_000.0, 1_800_000_000.0, 1_800_000_000.2])
        self.assertAlmostEqual(result['offset'], 10.0, places=3)
        self.assertAlmostEqual(result['delay'], 0.2, places=3)
        self.assertEqual(result['stratum'], 1)
        self.assertEqual(result['reference'], 'GPS')

    def test_request_is_v4_client(self):
        seen = {}

        def respond(request):
            seen['first'] = request[0]
            return sntp_reply(request, 1_800_000_000)
        self.run_sntp(respond, [1_800_000_000.0] * 3)
        self.assertEqual(seen['first'], 0x23)

    def test_kiss_of_death(self):
        with self.assertRaisesRegex(ts.TimeServiceError, 'RATE'):
            self.run_sntp(lambda r: sntp_reply(r, 1_800_000_000, stratum=0, ref=b'RATE'),
                          [1_800_000_000.0] * 3)

    def test_rejects_unmatched_reply(self):
        with self.assertRaisesRegex(ts.TimeServiceError, 'originate'):
            self.run_sntp(lambda r: sntp_reply(r, 1_800_000_000, origin=8 * b'\1'),
                          [1_800_000_000.0] * 3)

    def test_rejects_unsynchronised_server(self):
        with self.assertRaisesRegex(ts.TimeServiceError, 'not synchronised'):
            self.run_sntp(lambda r: sntp_reply(r, 1_800_000_000, leap=3), [1_800_000_000.0] * 3)

    def test_era_after_2036(self):
        later = 2_200_000_000.0  # 2039, NTP seconds have wrapped
        result = self.run_sntp(lambda r: sntp_reply(r, later), [later] * 3)
        self.assertEqual(result['remote_utc'].year, 2039)


class ClassicTimeTest(unittest.TestCase):
    def test_rfc868_tcp(self):
        server = FakeTCP(struct.pack('!I', (1_800_000_000 + ts.NTP_EPOCH_OFFSET) & 0xFFFFFFFF))
        server.start()
        with patch.dict(ts.PORTS, {'TCP': server.port}):
            result = ts.query_time_tcp('127.0.0.1', timeout=2)
        self.assertEqual(int(result['remote_utc'].timestamp()), 1_800_000_000)

    def test_rfc868_udp(self):
        server = FakeUDP(lambda r: struct.pack('!I', 1_800_000_000 + ts.NTP_EPOCH_OFFSET))
        server.start()
        with patch.dict(ts.PORTS, {'UDP': server.port}):
            result = ts.query_time_udp('127.0.0.1', timeout=2)
        self.assertEqual(int(result['remote_utc'].timestamp()), 1_800_000_000)

    def test_daytime_reads_whole_reply(self):
        server = FakeTCP(b'\n61000 26-11-19 16:00:00 00 0 0 123.4 UTC(NIST) * \n')
        server.start()
        with patch.dict(ts.PORTS, {'Daytime': server.port}):
            result = ts.query_daytime('127.0.0.1', timeout=2)
        self.assertIn('UTC(NIST)', result['text'])
        self.assertIn('UTC(NIST)', ts.format_result(result))


class CatalogueTest(unittest.TestCase):
    def test_suggestions_by_protocol(self):
        self.assertIn('time.inrim.it', ts.suggested_servers('Daytime'))
        self.assertIn('time.nist.gov', ts.suggested_servers('TCP'))
        self.assertNotIn('time.google.com', ts.suggested_servers('Daytime'))
        self.assertIn('time.google.com', ts.suggested_servers('SNTP'))

    def test_historic_servers_only_on_request(self):
        self.assertEqual(len(ts.HISTORIC_TIME_SERVERS), 13)
        self.assertNotIn('bernina.ethz.ch', ts.suggested_servers('SNTP'))
        self.assertIn('bernina.ethz.ch', ts.suggested_servers('SNTP', True))
        self.assertIn('Historic', ts.server_note('bernina.ethz.ch'))

    def test_fallback_tries_next_server(self):
        calls = []

        def fake(host):
            calls.append(host)
            if host == 'dead.example':
                raise ts.TimeServiceError('timeout')
            return {'host': host}
        result, attempts = ts.query_with_fallback('SNTP', 'dead.example', query_function=fake)
        self.assertEqual(calls[:2], ['dead.example', ts.suggested_servers('SNTP')[0]])
        self.assertEqual(result['host'], calls[1])
        self.assertEqual(attempts[0], ('dead.example', 'timeout'))

    def test_fallback_respects_stop(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaises(ts.TimeServiceError):
            ts.query_with_fallback('SNTP', 'x', stop=stop, query_function=lambda h: {'host': h})


if __name__ == '__main__':
    unittest.main()
