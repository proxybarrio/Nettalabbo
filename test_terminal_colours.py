import unittest
from terminal_colours import ColourTerminalScreen, xterm_color

class TerminalColourTests(unittest.TestCase):
    def test_palette(self):
        self.assertEqual(xterm_color(196), '#ff0000')
        self.assertEqual(xterm_color(232), '#080808')
        self.assertIsNone(xterm_color(300))
    def test_ansi_color_and_reset(self):
        screen = ColourTerminalScreen()
        self.assertEqual(screen.feed('abc\x1b[31mRED\x1b[0m!'), 'abcRED!')
        runs = list(screen.styled_runs())
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0][:3], (1, 3, 6))
        self.assertEqual(runs[0][3][0], '#cd3131')
    def test_256_and_truecolor_spanning_chunks(self):
        s = ColourTerminalScreen()
        s.feed('\x1b[38;5;')
        s.feed('196mRED\x1b[48;2;1;2;3m!')
        runs = list(s.styled_runs())
        self.assertEqual(runs[0][3][0], '#ff0000')
        self.assertEqual(runs[-1][3][1], '#010203')
    def test_moving_cursor_overwrites_styles(self):
        s = ColourTerminalScreen()
        s.feed('\x1b[31mred\x1b[0m\rX')
        self.assertEqual(s.feed(''), 'Xed')
        self.assertEqual(list(s.styled_runs())[0][:3], (1, 1, 3))
    def test_erase_clears_styles(self):
        s = ColourTerminalScreen()
        s.feed('\x1b[31mABCD\x1b[0m\r\x1b[2K')
        self.assertEqual(list(s.styled_runs()), [])
        s.feed('\x1b[31mABC\x1b[2J')
        self.assertEqual(list(s.styled_runs()), [])
    def test_osc_does_not_execute_or_display(self):
        s = ColourTerminalScreen()
        self.assertEqual(s.feed('\x1b]0;ignored\x07safe'), 'safe')
    def test_history_is_bounded(self):
        s = ColourTerminalScreen(max_lines=3)
        s.feed('\x1b[32mone\ntwo\nthree\nfour')
        self.assertEqual(len(s.lines), len(s.cell_styles))
        self.assertLessEqual(len(s.lines), 3)
if __name__ == '__main__':
    unittest.main()