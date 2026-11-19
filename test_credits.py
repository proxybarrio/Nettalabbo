"""Verify public attribution and independent development notice."""
from pathlib import Path
import unittest
import nettalabbo

ROOT = Path(__file__).resolve().parent

class CreditsTests(unittest.TestCase):
    def test_author_and_licence(self):
        credits = (ROOT / 'CREDITS.md').read_text()
        licence = (ROOT / 'LICENSE').read_text()
        self.assertIn('Proxybarrio', credits)
        self.assertIn('AI-assisted', credits)
        self.assertIn('MIT License', credits)
        self.assertIn('Alexander Danileiko', credits)
        self.assertIn('not affiliated', credits)
        self.assertIn('2026 Proxybarrio and contributors', licence)

    def test_about_credits(self):
        source = (ROOT / 'nettalabbo.py').read_text()
        self.assertIn('Created by Proxybarrio, with AI-assisted development.', source)
        self.assertIn('NetLab95', source)
        self.assertIn('Alexander Danileiko', source)
        self.assertIn('not a port', source)
        self.assertEqual(nettalabbo.VERSION, '0.5.4')

if __name__ == '__main__': unittest.main()
