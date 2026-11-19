"""Offline tests for DNS record lookups (dig is replaced by a fake runner)."""
import subprocess
import unittest
from unittest.mock import patch

import dns_lookup as dl

MX_REPLY = """;; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 4242
;; flags: qr rd ra; QUERY: 1, ANSWER: 2, AUTHORITY: 0, ADDITIONAL: 1

;; ANSWER SECTION:
example.org.\t\t300\tIN\tMX\t10 mail1.example.org.
example.org.\t\t300\tIN\tMX\t20 mail2.example.org.
"""
TXT_REPLY = """;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 7
example.org.\t3600\tIN\tTXT\t"v=spf1 include:_spf.example.net ~all"
"""
NX_REPLY = ';; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 9\n'


def runner_for(stdout, returncode=0, seen=None):
    def run(command, **kwargs):
        if seen is not None:
            seen.append(command)
        return subprocess.CompletedProcess(command, returncode, stdout, '')
    return run


@patch('dns_lookup.dig_available', return_value=True)
class QueryTest(unittest.TestCase):
    def test_mx_command_and_parsing(self, _dig):
        seen = []
        result = dl.query('example.org', 'MX', runner=runner_for(MX_REPLY, seen=seen))
        self.assertEqual(seen[0][-2:], ['MX', 'example.org'])
        self.assertNotIn('@', ' '.join(seen[0]))
        self.assertEqual(result['status'], 'NOERROR')
        self.assertEqual([a['data'] for a in result['answers']],
                         ['10 mail1.example.org.', '20 mail2.example.org.'])
        text = dl.format_result(result)
        self.assertIn('MX records for example.org', text)
        self.assertIn('TTL    300', text)

    def test_txt_keeps_spaces(self, _dig):
        result = dl.query('example.org', 'TXT', runner=runner_for(TXT_REPLY))
        self.assertIn('include:_spf.example.net ~all', result['answers'][0]['data'])

    def test_custom_server(self, _dig):
        seen = []
        result = dl.query('example.org', 'A', '9.9.9.9', runner=runner_for(MX_REPLY, seen=seen))
        self.assertIn('@9.9.9.9', seen[0])
        self.assertEqual(result['server'], '9.9.9.9')

    def test_reverse_lookup(self, _dig):
        seen = []
        result = dl.query('8.8.8.8', 'PTR', runner=runner_for('', seen=seen))
        self.assertEqual(seen[0][-2:], ['-x', '8.8.8.8'])
        self.assertEqual(result['record'], 'PTR')

    def test_nxdomain(self, _dig):
        result = dl.query('nothing.example', 'A', runner=runner_for(NX_REPLY))
        self.assertIn('does not exist', dl.format_result(result))

    def test_no_records(self, _dig):
        result = dl.query('example.org', 'CAA', runner=runner_for(';; status: NOERROR\n'))
        self.assertIn('no CAA records', dl.format_result(result))

    def test_dig_error(self, _dig):
        failing = lambda command, **k: subprocess.CompletedProcess(command, 9, '', ';; connection timed out')
        with self.assertRaisesRegex(dl.DnsLookupError, 'timed out'):
            dl.query('example.org', 'A', runner=failing)

    def test_international_name(self, _dig):
        seen = []
        dl.query('perché.it', 'A', runner=runner_for(MX_REPLY, seen=seen))
        self.assertEqual(seen[0][-1], 'xn--perch-fsa.it')


class ValidationTest(unittest.TestCase):
    def test_rejects_option_injection_and_garbage(self):
        for bad in ('-f /etc/passwd', '+short', 'a b', 'exa$mple.org', '', 'x' * 300):
            with self.assertRaises(dl.DnsLookupError, msg=bad):
                dl.validate_query(bad, 'A')
        for bad in ('-x', '@evil', 'not a server'):
            with self.assertRaises(dl.DnsLookupError, msg=bad):
                dl.validate_server(bad)

    def test_type_rules(self):
        with self.assertRaises(dl.DnsLookupError):
            dl.validate_query('8.8.8.8', 'MX')
        with self.assertRaises(dl.DnsLookupError):
            dl.validate_query('example.org', 'PTR')
        with self.assertRaises(dl.DnsLookupError):
            dl.validate_query('example.org', 'AXFR')
        self.assertEqual(dl.validate_query('_sip._tcp.example.org', 'SRV')[1], '_sip._tcp.example.org')

    def test_missing_dig(self):
        with patch('dns_lookup.dig_available', return_value=False):
            with self.assertRaisesRegex(dl.DnsLookupError, 'dig'):
                dl.query('example.org', 'A')


if __name__ == '__main__':
    unittest.main()
