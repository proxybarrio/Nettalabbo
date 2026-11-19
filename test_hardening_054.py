"""0.5.4 release candidate regressions for ANSI and Legacy rendering.

Offline only: never connects to remote services.
"""
import unittest

from remote_terminal import TerminalScreen
from terminal_colours import ColourTerminalScreen
from legacy_protocols import LegacyResult
from legacy_view import segments, distinct_links, raw_text
from legacy_theme import THEME_NAMES, palette

class HardenedTerminalTests(unittest.TestCase):
    def test_extreme_cursor_coordinates_are_bounded(self):
        s = TerminalScreen(max_lines=20)
        s.feed('\x1b[999999999999;999999999999Htest')
        self.assertLessEqual(len(s.lines), 20)
        self.assertLessEqual(s.y, 20)
        s.feed('\x1b[999999999999Bhello')
        self.assertLessEqual(len(s.lines), 20)

    def test_scrollback_colour_rows_stay_aligned(self):
        s = ColourTerminalScreen(max_lines=3)
        s.feed('\x1b[31mRED\n\x1b[32mGREEN\n\x1b[34mBLUE\n\x1b[33mYELLOW')
        self.assertEqual(len(s.lines), len(s.cell_styles))
        self.assertEqual(len(s.lines), 3)
        self.assertEqual(''.join(s.lines[0]), 'GREEN')
        self.assertEqual(s.cell_styles[0][0][0], '#0dbc79')
        self.assertEqual(''.join(s.lines[-1]), 'YELLOW')
        self.assertEqual(s.cell_styles[-1][0][0], '#e5e510')

    def test_ansi_payload_cannot_execute_controls_as_text(self):
        s = ColourTerminalScreen()
        self.assertEqual(s.feed('safe\x1b]0;remote title\x07\x1b[31mred'), 'safered')
        self.assertTrue(all('\x1b' not in ''.join(x) for x in s.lines))

class LegacyColourRegressionTests(unittest.TestCase):
    def test_gopher_raw_and_links_preserved_across_themes(self):
        wire = b'1Folder\t/menu\texample.org\t70\r\n0Read me\t/doc\texample.org\t70\r\niInfo\t\t\t\r\n.\r\n'
        links = [('Folder','gopher://example.org/1/menu'),
                 ('Read me','gopher://example.org/0/doc')]
        res = LegacyResult('gopher://example.org/1','gopher',
                           'Gopher menu', wire.decode(), links, len(wire),wire)
        before = distinct_links(segments(res))
        for name in THEME_NAMES:
            palette(name)
            self.assertEqual(raw_text(res), wire.decode())
            self.assertEqual(distinct_links(segments(res)), before)
        self.assertEqual(len(before), 2)

    def test_gemini_raw_heading_and_urls_preserved(self):
        wire = b'20 text/gemini\r\n# Heading\n=> gemini://example.net/item Article\n'
        content = '# Heading\n=> gemini://example.net/item Article\n'
        res = LegacyResult('gemini://example.net/','gemini','20 text/gemini',
                           content,[('Article','gemini://example.net/item')],len(wire),wire)
        before = segments(res)
        self.assertIn(('heading','Heading\n',None), before)
        self.assertEqual(len(distinct_links(before)), 1)
        for name in THEME_NAMES:
            palette(name)
            self.assertEqual(segments(res),before)
            self.assertEqual(raw_text(res),wire.decode())

if __name__ == '__main__':
    unittest.main()
