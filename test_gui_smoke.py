"""Offline Tk smoke test for Diagnose, ANSI terminal and Legacy Raw."""
import os
import tkinter as tk
import unittest
from unittest.mock import patch

from nettalabbo import App
from legacy_protocols import LegacyResult


@unittest.skipUnless(os.environ.get('DISPLAY'), 'GUI display required')
class GuiSmokeTests(unittest.TestCase):
    def test_diagnose_remote_colours_and_legacy_raw(self):
        root = tk.Tk()
        try:
            with patch.object(App, 'read_settings', return_value={}), \
                    patch.object(App, 'persist', return_value=None):
                app = App(root)
                self.assertIn('Diagnose', app.pages)
                self.assertFalse(app.diagnose_dnsbl.get())
                self.assertFalse(app.diagnose_smtp.get())
                self.assertIn('SSH', app.remote_consoles)
                self.assertIn('Telnet', app.remote_consoles)

                app.remote_write('SSH', '\x1b[31mRED\x1b[0m')
                console = app.remote_consoles['SSH']
                self.assertIn('RED', console.get('1.0', 'end'))
                colours = [console.tag_cget(name, 'foreground')
                           for name in console.tag_names()
                           if name.startswith('ansi_style_')]
                self.assertIn('#cd3131', colours)

                wire = b'1Folder\t/menu\texample.org\t70\r\n.\r\n'
                result = LegacyResult('gopher://example.org/1', 'gopher',
                                      'Gopher menu', wire.decode(),
                                      [('Folder', 'gopher://example.org/1/menu')],
                                      len(wire), wire)
                app.legacy_display_mode.set('Raw')
                app.legacy_show_result(result)
                self.assertEqual(app.output['Legacy Navigator'].get('1.0', 'end-1c'),
                                 wire.decode())
                app.legacy_display_mode.set('Rendered')
                app.legacy_show_result(result)
                self.assertEqual(len(app.legacy_current_links), 1)
                self.assertEqual(app.legacy_current_links[0][1],
                                 'gopher://example.org/1/menu')
                if hasattr(app, 'legacy_theme'):
                    app.legacy_theme.set('Dark')
                    self.assertEqual(app.output['Legacy Navigator'].cget('background'),
                                     '#17222b')
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
