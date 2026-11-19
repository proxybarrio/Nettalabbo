import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent

class LegacyRemovalTests(unittest.TestCase):
    def test_declared_conflicts_and_replaces_all_legacy_packages(self):
        text = (ROOT / 'packaging' / 'control').read_text()
        for key in ('Conflicts', 'Replaces'):
            line = next(x for x in text.splitlines() if x.startswith(key+': '))
            for package in ('netlabbo', 'netlab-xubuntu', 'network-laboratory-xubuntu'):
                self.assertIn(package, line)
    def test_installer_checks_removal_before_installing(self):
        s = (ROOT / 'install-nettalabbo.sh').read_text()
        self.assertIn('INSTALLED_LEGACY=()', s)
        self.assertIn('apt-get -s install "$PACKAGE"', s)
        self.assertIn('^Remv ${old_name}', s)
        self.assertIn('if legacy_is_installed "$old_name"; then', s)
        self.assertNotIn('apt-get purge', s)
        self.assertNotIn('sudo apt-get remove', s)
        self.assertLess(s.index('^Remv ${old_name}'), s.index('sudo apt-get install "$PACKAGE"'))
    def test_user_config_migration_preserved(self):
        s = (ROOT/'nettalabbo.py').read_text()
        self.assertIn("Path.home() / '.config' / 'netlabbo' / 'settings.json'",s)

if __name__ == '__main__': unittest.main()
