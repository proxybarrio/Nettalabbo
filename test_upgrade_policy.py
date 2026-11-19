"""Regression checks: every Debian revision must upgrade a single stable package."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class UpgradePolicyTests(unittest.TestCase):
    def test_stable_debian_package_identity(self):
        control=(ROOT / 'packaging/control').read_text()
        self.assertRegex(control, r'(?m)^Package: nettalabbo$')
        self.assertRegex(control, r'(?m)^Version: 0\.5\.3-[1-9][0-9]*$')
        for old in ('netlabbo', 'netlab-xubuntu', 'network-laboratory-xubuntu'):
            self.assertIn(old, control)
    def test_build_filename_generated_from_control(self):
        script=(ROOT / 'packaging/build_deb.sh').read_text()
        self.assertIn('PACKAGE_NAME=', script)
        self.assertIn('PACKAGE_VERSION=', script)
        self.assertIn('${PACKAGE_NAME}_${PACKAGE_VERSION}_all.deb', script)
    def test_preserves_user_settings_without_remove_script(self):
        app=(ROOT / 'nettalabbo.py').read_text()
        self.assertIn("APP_DIR = Path.home() / '.config' / 'nettalabbo'", app)
        self.assertIn("Path.home() / '.config' / 'netlabbo' / 'settings.json'", app)
        for script in ('preinst','postinst','prerm','postrm'):
            self.assertFalse((ROOT / 'packaging' / script).exists())

if __name__ == '__main__': unittest.main()
