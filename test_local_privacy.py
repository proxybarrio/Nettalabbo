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

    def test_hardens_existing_and_legacy_configuration(self):
        with tempfile.TemporaryDirectory() as base:
            current=Path(base)/'nettalabbo'
            legacy=Path(base)/'netlabbo'
            for directory in (current, legacy):
                directory.mkdir(mode=0o755)
                os.chmod(directory, 0o755)
            files=[current/'settings.json', current/'rdap_bootstrap.json', legacy/'settings.json']
            for path in files:
                path.write_text('{}')
                os.chmod(path, 0o644)
            outside=Path(base)/'outside.txt'
            outside.write_text('x'); os.chmod(outside, 0o644)
            (current/'link').symlink_to(outside)
            nettalabbo.harden_private_paths(current, [legacy/'settings.json', Path(base)/'missing'/'settings.json'])
            for directory in (current, legacy):
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            for path in files:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o644)
            self.assertFalse((Path(base)/'missing').exists())

    def test_read_settings_hardens_before_reading(self):
        with tempfile.TemporaryDirectory() as base:
            directory=Path(base)/'nettalabbo'
            directory.mkdir(); os.chmod(directory, 0o755)
            target=directory/'settings.json'
            target.write_text('{"history":["example.org"]}'); os.chmod(target, 0o644)
            fake=nettalabbo.App.__new__(nettalabbo.App)
            with patch.object(nettalabbo,'APP_DIR',directory), patch.object(nettalabbo,'SETTINGS_FILE',target), patch.object(nettalabbo,'LEGACY_SETTINGS_FILES',[]):
                settings=nettalabbo.App.read_settings(fake)
            self.assertEqual(settings['history'], ['example.org'])
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

if __name__ == '__main__': unittest.main()
