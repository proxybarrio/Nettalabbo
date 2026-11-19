"""Regression cases for conservative email DNS policy inspection."""
import unittest
from mail_policy import txt_value, spf_review, dmarc_review, dkim_review
from diagnose import diagnose

class FakeResolver:
    def __init__(self, replies=None):
        self.replies = replies or {}
        self.calls = []
    def query(self, domain, kind):
        self.calls.append((domain, kind))
        value = self.replies.get((domain, kind), [])
        if isinstance(value, Exception):
            raise value
        return value

class MailPolicyTests(unittest.TestCase):
    def test_txt_fragments_are_joined(self):
        self.assertEqual(txt_value('"v=spf1 include:" "example.org -all"'),
                         'v=spf1 include:example.org -all')
    def test_spf_validation(self):
        self.assertEqual(spf_review(['"v=spf1 -all"'])[0], 'pass')
        self.assertEqual(spf_review(['"v=spf1 -all"', '"v=spf1 +all"'])[0], 'fail')
        self.assertEqual(spf_review(['"v=spf1 ip4:192.0.2.1"'])[0], 'warn')
        many = '"v=spf1 ' + ' '.join('include:d%d.example.org' % n for n in range(11)) + ' -all"'
        self.assertEqual(spf_review([many])[0], 'fail')
    def test_dmarc_validation(self):
        self.assertEqual(dmarc_review(['"v=DMARC1; p=reject"'])[0], 'pass')
        self.assertEqual(dmarc_review(['"v=DMARC1; p=none"'])[0], 'warn')
        self.assertEqual(dmarc_review(['"v=DMARC1; p=reject; p=none"'])[0], 'fail')
        self.assertEqual(dmarc_review(['"v=DMARC1; p=wrong"'])[0], 'fail')
    def test_dkim_validation(self):
        self.assertEqual(dkim_review(['"v=DKIM1; k=rsa; p=ABC"'])[0], 'pass')
        self.assertEqual(dkim_review(['"v=DKIM1; p="'])[0], 'warn')
    def test_dnsbl_access_denied_unknown_not_listed(self):
        r = FakeResolver({('example.org.dbl.spamhaus.org', 'A'): ['127.255.255.254']})
        result = diagnose('example.org', r, check_blacklists=True)
        rows = [x for x in result.checks if x.name.startswith('Domain DNSBL')]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, 'unknown')
    def test_dnsbl_negative_is_not_proof_of_reputation(self):
        r = FakeResolver()
        result = diagnose('example.org', r, check_blacklists=True)
        rows = [x for x in result.checks if x.name.startswith('Domain DNSBL')]
        self.assertEqual(rows[0].status, 'unknown')
    def test_no_opt_in_no_dnsbl_requests(self):
        r = FakeResolver()
        diagnose('example.org', r)
        self.assertFalse(any('spamhaus.org' in name or 'spamcop.net' in name
                             for name, _ in r.calls))
class SpfStandardSyntaxTest(unittest.TestCase):
    def test_cidr_lengths_and_unknown_modifiers(self):
        for record in ('"v=spf1 a/24 mx -all"', '"v=spf1 mx:mail.example.org/24 a//64 -all"',
                       '"v=spf1 ip4:192.0.2.0/24 ra=postmaster -all"', '"v=spf1 include:_spf.example.net ~all"'):
            self.assertEqual(spf_review([record])[0], 'pass', record)

    def test_still_rejects_unknown_mechanisms(self):
        self.assertEqual(spf_review(['"v=spf1 foo:example.org -all"'])[0], 'warn')
        self.assertEqual(spf_review(['"v=spf1 =bad -all"'])[0], 'warn')

    def test_lookup_limit_counts_cidr_mechanisms(self):
        record = '"v=spf1 ' + ' '.join('a/24' for _ in range(11)) + ' -all"'
        self.assertEqual(spf_review([record])[0], 'fail')

    def test_unquoted_value(self):
        self.assertEqual(txt_value('v=spf1 a/24 -all'), 'v=spf1 a/24 -all')
        self.assertEqual(spf_review(['v=spf1 a/24 -all'])[0], 'pass')


if __name__ == '__main__':
    unittest.main()
