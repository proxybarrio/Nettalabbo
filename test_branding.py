"""Offline checks for the independent Nettalabbo identity and settings migration."""
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import nettalabbo

class BrandingTests(unittest.TestCase):
    def test_brand(self):
        self.assertEqual(nettalabbo.VERSION, '0.5.5')
        self.assertEqual(nettalabbo.APP_DIR.name, 'nettalabbo')

    def test_icon_assets(self):
        assets = Path(nettalabbo.__file__).parent / 'assets'
        self.assertTrue((assets / 'nettalabbo_192.png').is_file())
        self.assertTrue((assets / 'nettalabbo_64.png').is_file())

    def test_migration(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            previous = root / 'old.json'
            previous.write_text('{"last_tab":"DNS"}')
            with patch.object(nettalabbo, 'SETTINGS_FILE', root / 'current.json'), \
                 patch.object(nettalabbo, 'LEGACY_SETTINGS_FILES', [previous]):
                self.assertEqual(nettalabbo.App.read_settings(None)['last_tab'], 'DNS')

if __name__ == '__main__': unittest.main()
