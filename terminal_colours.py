"""ANSI SGR colour support for Nettalabbo's existing PTY screen.

The terminal's text/cursor state remains owned by TerminalScreen. This subclass
tracks presentation attributes by cell and never interprets remote escape
sequences as Tk commands or executable code.
"""
from remote_terminal import TerminalScreen

BASE = (
    '#000000', '#cd3131', '#0dbc79', '#e5e510',
    '#2472c8', '#bc3fbc', '#11a8cd', '#e5e5e5',
    '#666666', '#f14c4c', '#23d18b', '#f5f543',
    '#3b8eea', '#d670d6', '#29b8db', '#ffffff',
)
EMPTY = (None, None, False, False, False)


def xterm_color(n):
    """Return a CSS-like hex colour for an ANSI palette index."""
    if not isinstance(n, int) or n < 0 or n > 255:
        return None
    if n < 16:
        return BASE[n]
    if n >= 232:
        g = 8 + (n - 232) * 10
        return f'#{g:02x}{g:02x}{g:02x}'
    n -= 16
    v = [0, 95, 135, 175, 215, 255]
    r, g, b = v[n // 36], v[(n // 6) % 6], v[n % 6]
    return f'#{r:02x}{g:02x}{b:02x}'


class ColourTerminalScreen(TerminalScreen):
    """Extended screen with per-character styling and bounded history."""

    def __init__(self, max_lines=1200):
        super().__init__(max_lines=max_lines)
        self.cell_styles = [[]]
        self.current_style = EMPTY

    def clear(self):
        super().clear()
        self.cell_styles = [[]]
        self.current_style = EMPTY

    def _row(self):
        before = len(self.lines)
        # Base screen drops the oldest row after reaching max_lines.
        # Track the number dropped even when the total stays unchanged.
        wanted = min(max(0, self.y), self.max_lines) + 1
        removed = max(0, before + max(0, wanted - before) - self.max_lines)
        super()._row()
        if removed:
            del self.cell_styles[:removed]
        while len(self.cell_styles) < len(self.lines):
            self.cell_styles.append([])
        if len(self.cell_styles) > len(self.lines):
            del self.cell_styles[:len(self.cell_styles) - len(self.lines)]

    def _put(self, char):
        if self.x > 300:
            return
        super()._put(char)
        row = self.cell_styles[self.y]
        index = self.x - 1
        while len(row) <= index:
            row.append(EMPTY)
        row[index] = self.current_style

    def _sgr(self, seq):
        params = [int(p) if p.isdigit() else 0 for p in seq.split(';')]
        fg, bg, bold, underline, reverse = self.current_style
        i = 0
        while i < len(params):
            n = params[i]
            if n == 0:
                fg, bg, bold, underline, reverse = EMPTY
            elif n == 1:
                bold = True
            elif n == 22:
                bold = False
            elif n == 4:
                underline = True
            elif n == 24:
                underline = False
            elif n == 7:
                reverse = True
            elif n == 27:
                reverse = False
            elif 30 <= n <= 37 or 90 <= n <= 97:
                fg = BASE[(n - 30) if n <= 37 else (n - 90 + 8)]
            elif 40 <= n <= 47 or 100 <= n <= 107:
                bg = BASE[(n - 40) if n <= 47 else (n - 100 + 8)]
            elif n == 39:
                fg = None
            elif n == 49:
                bg = None
            elif n in (38, 48) and i + 2 < len(params):
                value = None
                consumed = 0
                if params[i+1] == 5:
                    value = xterm_color(params[i+2])
                    consumed = 2
                elif params[i+1] == 2 and i + 4 < len(params):
                    rgb = params[i+2:i+5]
                    if all(0 <= v <= 255 for v in rgb):
                        value = '#' + ''.join(f'{v:02x}' for v in rgb)
                    consumed = 4
                if value is not None:
                    if n == 38:
                        fg = value
                    else:
                        bg = value
                i += consumed
            i += 1
        self.current_style = (fg, bg, bold, underline, reverse)

    def _csi(self, seq, cmd):
        if cmd == 'm' and not seq.startswith('?'):
            self._sgr(seq)
            return
        if cmd == 'K':
            mode = int(seq) if seq.isdigit() else 0
            if self.y < len(self.cell_styles):
                row = self.cell_styles[self.y]
                if mode == 2:
                    row[:] = []
                elif mode == 1:
                    row[:min(self.x+1,len(row))] = [EMPTY]*min(self.x+1,len(row))
                else:
                    del row[self.x:]
        super()._csi(seq, cmd)

    def styled_runs(self):
        """Yield (line, start, end, style) for styled text spans, Tk indexed."""
        for row_no, (chars, styles) in enumerate(zip(self.lines, self.cell_styles), 1):
            start = 0
            last = EMPTY
            for i in range(len(chars)+1):
                current = styles[i] if i < len(chars) and i < len(styles) else EMPTY
                if current != last or i == len(chars):
                    if last != EMPTY and i > start:
                        yield row_no, start, i, last
                    start, last = i, current