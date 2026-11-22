import unittest
from urllib.parse import urlsplit

from legacy_directory import GROUPS, SERVICES, anchor, services_by_group
from legacy_protocols import CATALOG, SCHEMES, parse_url


class LegacyDirectoryTest(unittest.TestCase):
    def test_every_protocol_is_explained(self):
        names = {service[0] for service in SERVICES}
        self.assertEqual(names, {entry[0] for entry in CATALOG})

    def test_group_matches_capability(self):
        modes = {entry[0]: entry[3] for entry in CATALOG}
        for name, group, *_ in SERVICES:
            expected = {'read': ('ready', 'experimental'), 'remote': ('remote',),
                        'upload': ('upload',), 'reference': ('reference',)}[modes[name]]
            self.assertIn(group, expected, name)

    def test_examples_are_openable(self):
        for name, _group, _form, description, examples in SERVICES:
            self.assertTrue(description.strip(), name)
            for label, url in examples:
                self.assertTrue(label.strip())
                if url.startswith('nettalabbo:'):
                    continue
                self.assertIn(urlsplit(url).scheme, SCHEMES, url)
                parse_url(url)

    def test_groups_in_order_and_complete(self):
        grouped = services_by_group()
        self.assertEqual([g[0] for g in grouped], [g[0] for g in GROUPS])
        self.assertEqual(sum(len(g[4]) for g in grouped), len(SERVICES))

    def test_anchor_is_tk_safe(self):
        names = [anchor(service[0]) for service in SERVICES]
        self.assertEqual(len(set(names)), len(names))
        for name in names:
            self.assertRegex(name, r'^\w+$')


if __name__ == '__main__':
    unittest.main()
