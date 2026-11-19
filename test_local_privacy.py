"""Offline regression test for private user configuration files."""
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import nettalabbo

class PrivateSettingsTest(unittest.TestCase):
    def test_private_atomic_settings_file(self):
        with tempfile.TemporaryDirectory() as base:
            directory=Path(base)/'nettalabbo'
            directory.mkdir(mode=0o755)
            target=directory/'settings.json'
            target.write_text('{"old":true}')
            os.chmod(target, 0o644)
            fake=nettalabbo.App.__new__(nettalabbo.App)
            fake.settings={'last_tab':'Domain Inspector','history':['example.org']}
            with patch.object(nettalabbo, 'APP_DIR', directory), patch.object(nettalabbo,'SETTINGS_FILE',target):
                nettalabbo.App.persist(fake)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertIn('example.org',target.read_text())
            self.assertFalse(list(directory.glob('.settings-*.tmp')))

if __name__ == '__main__': unittest.main()
