import unittest
from diagnose import diagnose, domain_name

class FakeResolver:
    def __init__(self, answers=None, failures=()):
        self.answers = answers or {}
        self.failures = set(failures)
        self.requests = []
    def query(self, name, kind):
        self.requests.append((name, kind))
        if (name, kind) in self.failures:
            raise RuntimeError('DNS timeout')
        return self.answers.get((name, kind), [])

class DiagnoseTests(unittest.TestCase):
    def fixture(self):
        return FakeResolver({
            ('example.org','A'): ['93.184.216.34'],
            ('example.org','MX'): ['10 mail.example.org.'],
            ('mail.example.org','A'): ['93.184.216.35'],
            ('example.org','TXT'): ['"v=spf1 mx -all"'],
            ('_dmarc.example.org','TXT'): ['"v=DMARC1; p=reject"'],
            ('s1._domainkey.example.org','TXT'): ['"v=DKIM1; k=rsa; p=ABC"'],
        })
    def test_good_dns_does_not_look_up_blacklists_without_consent(self):
        fake=self.fixture()
        report=diagnose('example.org', fake, dkim_selector='s1')
        self.assertTrue(any(x.name=='SPF' and x.status=='pass' for x in report.checks))
        self.assertTrue(any(x.name=='DMARC' and x.status=='pass' for x in report.checks))
        self.assertTrue(any(x.name=='DKIM' and x.status=='pass' for x in report.checks))
        self.assertTrue(any(x.name=='MX records' and x.status=='pass' for x in report.checks))
        self.assertTrue(any(x.name=='DNSBL' and x.status=='skipped' for x in report.checks))
        self.assertFalse(any('spamhaus' in name for name,kind in fake.requests))
    def test_blacklist_status_is_not_false_clean(self):
        fake=self.fixture()
        fake.answers[('example.org.dbl.spamhaus.org','A')]=['127.0.1.2']
        fake.failures.add(('35.216.184.93.zen.spamhaus.org','A'))
        report=diagnose('example.org',fake,check_blacklists=True)
        self.assertTrue(any('Domain DNSBL:' in x.name and x.status=='warn' for x in report.checks))
        self.assertTrue(any('DNSBL:' in x.name and x.status=='unknown' for x in report.checks))
    def test_ip_blacklists_target_mail_servers_not_website(self):
        fake = self.fixture()
        diagnose('example.org', fake, check_blacklists=True)
        self.assertIn(('35.216.184.93.zen.spamhaus.org','A'), fake.requests)
        self.assertNotIn(('34.216.184.93.zen.spamhaus.org','A'), fake.requests)

    def test_duplicate_spf_and_missing_dmarc(self):
        fake=FakeResolver({('example.org','TXT'): ['"v=spf1 -all"','"v=spf1 +all"']})
        report=diagnose('example.org',fake)
        self.assertTrue(any(x.name=='SPF' and x.status=='fail' for x in report.checks))
        self.assertTrue(any(x.name=='DMARC' and x.status=='warn' for x in report.checks))
    def test_invalid_domain_refused_before_query(self):
        fake=FakeResolver()
        for text in ('-x.example', 'bad name.com', 'example', 'x..com', 'x;rm -rf /.com'):
            with self.assertRaises(ValueError):
                diagnose(text,fake)
        self.assertEqual(fake.requests,[])
    def test_idna(self):
        self.assertEqual(domain_name('perché.it'),'xn--perch-fsa.it')
    def test_smtp_is_opt_in_and_read_only(self):
        fake = self.fixture()
        calls = []
        def probe(kind, host, port):
            calls.append((kind, host, port))
            return 'SMTP connection: mail.example.org:25\nTLS negotiated: yes\nNo email sent.'
        default = diagnose('example.org', fake, mail_probe=probe)
        self.assertEqual(calls, [])
        self.assertTrue(any(x.name == 'SMTP connectivity' and x.status == 'skipped'
                            for x in default.checks))
        enabled = diagnose('example.org', fake, check_smtp=True, mail_probe=probe)
        self.assertEqual(calls, [('SMTP', 'mail.example.org', 25)])
        self.assertTrue(any(x.name == 'SMTP connectivity' and x.status == 'pass'
                            for x in enabled.checks))

    def test_smtp_errors_are_unknown_not_success(self):
        def unavailable(*args):
            raise OSError('Connection timed out')
        report = diagnose('example.org', self.fixture(), check_smtp=True, mail_probe=unavailable)
        self.assertTrue(any(x.name == 'SMTP connectivity' and x.status == 'unknown'
                            for x in report.checks))

    def test_no_dkim_guess(self):
        r=diagnose('example.org', FakeResolver())
        self.assertTrue(any(x.name=='DKIM' and x.status=='skipped' for x in r.checks))
    def test_null_mx(self):
        r=diagnose('example.org', FakeResolver({('example.org','MX'):['0 .']}))
        self.assertTrue(any(x.name=='MX records' and x.status=='warn' and 'Null' in x.detail for x in r.checks))
    def test_failure_not_reported_clean(self):
        fake=FakeResolver(failures=[('example.org','MX')])
        r=diagnose('example.org', fake)
        self.assertTrue(any(x.name=='MX records' and x.status=='unknown' for x in r.checks))
if __name__=='__main__':
    unittest.main()


class DiagnoseLiveFindingsTest(unittest.TestCase):
    """Cases found while testing against real local DNS and SMTP servers."""

    def base(self):
        return FakeResolver({
            ('example.org', 'A'): ['93.184.216.34'],
            ('example.org', 'MX'): ['10 mail.example.org.'],
            ('mail.example.org', 'A'): ['127.0.0.1'],
        })

    def status(self, report, name):
        return [(x.status, x.detail) for x in report.checks if x.name == name]

    def test_mta_sts_and_tls_rpt_are_parsed_and_validated(self):
        fake = self.base()
        fake.answers[('_mta-sts.example.org', 'TXT')] = ['"v=STSv1; id=20261119"']
        fake.answers[('_smtp._tls.example.org', 'TXT')] = ['"v=TLSRPTv1; rua=mailto:tls@example.org"']
        report = diagnose('example.org', fake)
        self.assertEqual(self.status(report, 'MTA STS'), [('pass', 'v=STSv1; id=20261119')])
        self.assertEqual(self.status(report, 'TLS RPT')[0][0], 'pass')

    def test_mta_sts_wrong_or_duplicate(self):
        fake = self.base()
        fake.answers[('_mta-sts.example.org', 'TXT')] = ['"hello"']
        fake.answers[('_smtp._tls.example.org', 'TXT')] = ['"v=TLSRPTv1; rua=a"', '"v=TLSRPTv1; rua=b"']
        report = diagnose('example.org', fake)
        self.assertEqual(self.status(report, 'MTA STS')[0][0], 'warn')
        self.assertEqual(self.status(report, 'TLS RPT')[0][0], 'fail')

    def test_ip_dnsbl_skip_is_reported(self):
        report = diagnose('example.org', self.base(), check_blacklists=True)
        self.assertEqual(self.status(report, 'IP DNSBL')[0][0], 'skipped')
        self.assertIn('public', self.status(report, 'IP DNSBL')[0][1])

    def smtp_status(self, error):
        def probe(kind, host, port):
            raise error
        report = diagnose('example.org', self.base(), check_smtp=True, mail_probe=probe)
        return self.status(report, 'SMTP connectivity')[0]

    def test_untrusted_certificate_is_a_warning(self):
        import ssl
        status, detail = self.smtp_status(ssl.SSLCertVerificationError('certificate verify failed'))
        self.assertEqual(status, 'warn')
        self.assertIn('could not be verified', detail)

    def test_refused_port_25_explains_isp_blocking(self):
        status, detail = self.smtp_status(ConnectionRefusedError(111, 'Connection refused'))
        self.assertEqual(status, 'unknown')
        self.assertIn('port 25', detail)

    def test_multiline_details_are_indented(self):
        fake = self.base()
        probe = lambda kind, host, port: 'SMTP connection: x\nEHLO: 250 ok\nTLS negotiated: yes\n'
        text = diagnose('example.org', fake, check_smtp=True, mail_probe=probe).as_text()
        self.assertIn('\n    EHLO: 250 ok', text)
        self.assertNotIn('\nTLS negotiated', text)


if __name__ == "__main__":
    unittest.main()

