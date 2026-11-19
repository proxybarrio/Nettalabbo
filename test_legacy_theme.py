"""Regression tests for optional Legacy Navigator colour palettes.

These deliberately avoid Tk and real network traffic.
"""
import unittest

from legacy_theme import THEME_NAMES, palette
from legacy_protocols import LegacyResult
from legacy_view import segments, raw_text, distinct_links


class LegacyColourTests(unittest.TestCase):
    def test_palettes_contain_all_render_roles(self):
        required = {'background', 'foreground', 'heading', 'info',
                    'folder', 'document', 'external'}
        self.assertEqual(set(THEME_NAMES), {'Classic', 'Dark', 'Monochrome'})
        for name in THEME_NAMES:
            self.assertEqual(set(palette(name)), required)
            self.assertTrue(all(color.startswith('#') and len(color) == 7
                                for color in palette(name).values()))

    def test_unknown_palette_defaults_to_classic(self):
        self.assertEqual(palette('unknown'), palette('Classic'))

    def test_palette_changes_cannot_mutate_shared_settings(self):
        theme = palette('Dark')
        theme['folder'] = 'red'
        self.assertNotEqual(palette('Dark')['folder'], 'red')

    def test_gopher_links_and_raw_bytes_are_theme_independent(self):
        raw = b'1Directory\t/folder\tserver.test\t70\r\niInformation\t\t\t\r\n.\r\n'
        result = LegacyResult('gopher://server.test/1', 'gopher', 'Gopher menu',
                              raw.decode(), [('Directory', 'gopher://server.test/1/folder')],
                              len(raw), raw)
        original_segments = segments(result)
        original_links = distinct_links(original_segments)
        original_raw = raw_text(result)
        for name in THEME_NAMES:
            palette(name)
            self.assertEqual(segments(result), original_segments)
            self.assertEqual(distinct_links(segments(result)), original_links)
            self.assertEqual(raw_text(result), original_raw)


if __name__ == '__main__':
    unittest.main()
