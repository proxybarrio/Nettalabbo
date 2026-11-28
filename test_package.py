"""Check that all runtime utilities are required by the installer."""
import unittest
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent

class PackageTests(unittest.TestCase):
    def test_complete_install_dependencies(self):
        text = (ROOT / 'packaging' / 'control').read_text()
        dep_line = next(line for line in text.splitlines() if line.startswith('Depends: '))
        dependencies = dep_line.partition(': ')[2]
        for name in ('python3', 'python3-tk', 'iputils-ping', 'traceroute',
                     'openssh-client', 'telnet', 'ca-certificates', 'bind9-dnsutils | dnsutils'):
            self.assertIn(name, dependencies)
        self.assertIn('python3 (>= 3.8)', dependencies)
        self.assertNotIn('python3 (>= 3.10)', dependencies)
        self.assertNotIn('inetutils-telnet', dependencies)
        self.assertNotIn('Suggests:', text)
        self.assertNotIn('Recommends:', text)
        self.assertRegex(text, r'(?m)^Version: 0\.5\.[4-9]-[0-9]+$')
        self.assertIn('Package: nettalabbo', text)
        self.assertIn('Conflicts: netlabbo, network-laboratory-xubuntu, netlab-xubuntu', text)
        self.assertIn('Replaces: netlabbo, network-laboratory-xubuntu, netlab-xubuntu', text)

    def test_appstream_and_launcher(self):
        xml = ElementTree.parse(ROOT / 'org.nettalabbo.Nettalabbo.metainfo.xml').getroot()
        self.assertEqual(xml.findtext('project_license'), 'MIT')
        self.assertEqual(xml.findtext('icon'), 'nettalabbo')
        self.assertTrue((ROOT / 'assets/nettalabbo_128.png').is_file())
        launcher = (ROOT / 'packaging' / 'nettalabbo.desktop').read_text()
        self.assertIn('Icon=nettalabbo', launcher)

if __name__ == '__main__':
    unittest.main()
