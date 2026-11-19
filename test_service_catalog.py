"""Offline tests for WhoIs/Quote suggestions and the IANA referral parser."""
import unittest
import service_catalog as sc


class CatalogTest(unittest.TestCase):
    def test_suggestions(self):
        self.assertIn('whois.nic.it', sc.suggestions('WhoIs_server'))
        self.assertEqual(sc.suggestions('Quote_host')[0], 'djxmmx.net')
        self.assertIn('nic.ddn.mil', sc.suggestions('WhoIs_server'))
        self.assertEqual(sc.suggestions('Quote_host')[-1], 'www.rmm.com')
        self.assertEqual(sc.suggestions('WhoIs_server')[0], 'whois.iana.org')

    def test_iana_referral(self):
        reply = '% IANA WHOIS server\n\ndomain:       IT\n\nwhois:        whois.nic.it\n'
        self.assertEqual(sc.whois_referral(reply), 'whois.nic.it')
        self.assertEqual(sc.whois_referral('refer:        whois.arin.net\n'), 'whois.arin.net')

    def test_referral_rejects_garbage(self):
        self.assertEqual(sc.whois_referral('whois: not a host!\n'), '')
        self.assertEqual(sc.whois_referral('whois: localhost\n'), '')
        self.assertEqual(sc.whois_referral('no fields here'), '')


if __name__ == '__main__':
    unittest.main()
