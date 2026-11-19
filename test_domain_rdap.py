"""Offline, reproducible tests. Run: python3 -m unittest test_domain_rdap.py"""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
import domain_rdap

BOOTSTRAP = {'services': [
    [['com', 'net'], ['https://rdap.example-registry.test/rdap/']],
    [['uk'], ['https://rdap.example-uk.test/']],
    [['co.uk'], ['https://rdap.example-co-uk.test/']],
]}
RDAP_RESPONSE = {
    'objectClassName': 'domain', 'ldhName': 'sample.com',
    'status': ['active'], 'secureDNS': {'delegationSigned': True},
    'events': [{'eventAction': 'registration', 'eventDate': '2016-01-01T00:00:00Z'},
               {'eventAction': 'expiration', 'eventDate': '2028-01-01T00:00:00Z'}],
    'nameservers': [{'ldhName': 'ns1.sample.com'}, {'ldhName': 'ns2.sample.com'}],
    'entities': [
        {'roles': ['registrar'], 'vcardArray': ['vcard', [['fn', {}, 'text', 'Sample Registrar Ltd']]]},
        {'roles': ['registrant'], 'vcardArray': ['vcard', [['fn', {}, 'text', 'Public Organisation']]]},
    ]
}


class DomainTests(TestCase):
    def test_normalise_domains_and_url(self):
        self.assertEqual(domain_rdap.normalise_domain('  HTTPS://www.Example.ORG/path '), 'www.example.org')
        self.assertEqual(domain_rdap.normalise_domain('BÜCHER.de.'), 'xn--bcher-kva.de')
        with self.assertRaises(domain_rdap.LookupError):
            domain_rdap.normalise_domain('name@example.org')
        with self.assertRaises(domain_rdap.LookupError):
            domain_rdap.normalise_domain('192.168.1.1')

    def test_longest_matching_suffix(self):
        self.assertEqual(domain_rdap.bootstrap_services('website.co.uk', BOOTSTRAP),
                         ('co.uk', ['https://rdap.example-co-uk.test/']))
        with self.assertRaises(domain_rdap.LookupError):
            domain_rdap.bootstrap_services('example.zzz', BOOTSTRAP)

    def test_public_holder_and_registrar_are_distinct(self):
        rows, report = domain_rdap.summarise_rdap(
            'sample.com', 'com', 'https://rdap.example-registry.test/rdap/', 'IANA', RDAP_RESPONSE)
        d = dict(rows)
        self.assertEqual(d['Registrar'], 'Sample Registrar Ltd')
        self.assertEqual(d['Registrant / public holder'], 'Public Organisation')
        self.assertEqual(d['Registered'], '2016-01-01T00:00:00Z')
        self.assertEqual(d['DNSSEC'], 'Signed')
        self.assertEqual(d['Nameservers'], 'ns1.sample.com, ns2.sample.com')

    def test_redaction_never_guesses_owner(self):
        rows, _ = domain_rdap.summarise_rdap(
            'sample.com', 'com', 'https://rdap.example-registry.test/rdap/', 'IANA',
            {'ldhName': 'sample.com', 'entities': RDAP_RESPONSE['entities'][:1], 'redacted': [{'name': 'Registrant Name'}]})
        self.assertEqual(dict(rows)['Registrant / public holder'],
                         'Not disclosed in the public RDAP response')

    def test_lookup_uses_iana_and_domain_endpoint(self):
        root = {'domains': [{'name': 'com', 'status': 'active', 'type': 'generic',
                             'manager': {'organization': 'Sample Registry'},
                             'rdap_base_urls': ['https://rdap.example-registry.test/rdap/'],
                             'whois_server': None}]}
        with TemporaryDirectory() as tmp, patch.object(domain_rdap, '_load_tld_registry', return_value=(root, 'IANA')):
            with patch.object(domain_rdap, '_fetch_json', return_value=RDAP_RESPONSE) as get:
                rows, report, raw = domain_rdap.lookup_domain('sample.com', Path(tmp) / 'bootstrap.json')
                get.assert_called_once_with('https://rdap.example-registry.test/rdap/domain/sample.com')
                self.assertEqual(dict(rows)['Registrar'], 'Sample Registrar Ltd')
                self.assertEqual(dict(rows)['Registry operator'], 'Sample Registry')
                self.assertIn('RDAP query: https://rdap.', report)

    def test_iana_cc_tld_it_automatically_uses_whois(self):
        root = {'domains': [{'name': 'it', 'status': 'active', 'type': 'country-code',
                             'manager': {'organization': 'IIT - CNR'},
                             'rdap_base_urls': [], 'whois_server': 'whois.nic.it'}]}
        raw = ('Domain: conne.example.it\nRegistrant\n Organization: Public Owner Ltd\n'
               'Registrar\n Organization: Italian Registrar Ltd\nCreated: 2015-01-01\n')
        with TemporaryDirectory() as tmp, patch.object(domain_rdap, '_load_tld_registry', return_value=(root, 'IANA')):
            with patch.object(domain_rdap, '_whois_query', return_value=raw) as query:
                rows, report, _ = domain_rdap.lookup_domain('conne.example.it', Path(tmp) / 'bootstrap.json')
        query.assert_called_once_with('conne.example.it', 'whois.nic.it')
        d = dict(rows)
        self.assertEqual(d['Registry operator'], 'IIT - CNR')
        self.assertEqual(d['Registrar'], 'Italian Registrar Ltd')
        self.assertEqual(d['Registrant / public holder'], 'Public Owner Ltd')
        self.assertIn('RAW WHOIS RESPONSE', report)

    def test_iana_brand_custom_tld_detected_without_hardcoding(self):
        root = {'domains': [{'name': 'google', 'status': 'active', 'type': 'generic',
                             'manager': {'organization': 'Charleston Road Registry Inc.'},
                             'rdap_base_urls': ['https://rdap.test/'], 'whois_server': None}]}
        with TemporaryDirectory() as tmp, patch.object(domain_rdap, '_load_tld_registry', return_value=(root, 'IANA')):
            with patch.object(domain_rdap, '_fetch_json', return_value=RDAP_RESPONSE):
                rows, _, _ = domain_rdap.lookup_domain('about.google', Path(tmp) / 'bootstrap.json')
                self.assertEqual(dict(rows)['Registry operator'], 'Charleston Road Registry Inc.')

    def test_non_iana_custom_namespace_needs_explicit_server(self):
        with TemporaryDirectory() as tmp, patch.object(domain_rdap, '_load_tld_registry', return_value=({'domains': []}, 'IANA')):
            with self.assertRaisesRegex(domain_rdap.LookupError, 'not found in the public IANA root'):
                domain_rdap.lookup_domain('server.devcorp', Path(tmp) / 'bootstrap.json')
        with TemporaryDirectory() as tmp:
            services = [{'suffix': 'devcorp', 'protocol': 'whois', 'endpoint': 'whois.intra.example'}]
            with patch.object(domain_rdap, '_whois_query', return_value='Registrant Organization: Internal Corp') as whois:
                rows, _, _ = domain_rdap.lookup_domain('server.devcorp', Path(tmp) / 'bootstrap.json', services)
                self.assertEqual(dict(rows)['Registrant / public holder'], 'Internal Corp')
                whois.assert_called_once_with('server.devcorp', 'whois.intra.example')

    def test_rdap_fails_then_iana_whois_fallback(self):
        root = {'domains': [{'name': 'tv', 'status': 'active',
                             'manager': {'organization': 'Registry Test'},
                             'rdap_base_urls': ['https://rdap.test/'], 'whois_server': 'whois.nic.tv'}]}
        with TemporaryDirectory() as tmp, patch.object(domain_rdap, '_load_tld_registry', return_value=(root, 'IANA')):
            with patch.object(domain_rdap, '_fetch_json', side_effect=domain_rdap.LookupError('service unavailable')):
                with patch.object(domain_rdap, '_whois_query', return_value='Registrar: TV Registrar'):
                    rows, report, _ = domain_rdap.lookup_domain('site.tv', Path(tmp) / 'bootstrap.json')
                    self.assertEqual(dict(rows)['Registrar'], 'TV Registrar')
                    self.assertIn('RDAP attempts failed', report)

    def test_registry_no_public_service_still_identifies_operator(self):
        root = {'domains': [{'name': 'newbrand', 'status': 'active', 'type': 'generic',
                             'manager': {'organization': 'Brand LLC'},
                             'rdap_base_urls': [], 'whois_server': None}]}
        with TemporaryDirectory() as tmp, patch.object(domain_rdap, '_load_tld_registry', return_value=(root, 'IANA')):
            rows, report, _ = domain_rdap.lookup_domain('www.newbrand', Path(tmp) / 'bootstrap.json')
            self.assertEqual(dict(rows)['Registry operator'], 'Brand LLC')
            self.assertIn('Registrant information could not be retrieved', report)

    def test_registry_cache_uses_active_iana_document(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'tld_registry.json'
            cache.write_text('{"domains": [{"name": "it"}]}', encoding='utf-8')
            with patch.object(domain_rdap, '_fetch_json') as fetch:
                data, source = domain_rdap._load_tld_registry(cache)
            self.assertEqual(data['domains'][0]['name'], 'it')
            self.assertIn('cached', source)
            fetch.assert_not_called()


if __name__ == '__main__': main()
