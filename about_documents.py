"""Bundled offline About documents, read from project source or Debian package.

Only allow-listed filenames are loaded; the app never fetches legal notices
from the network and never needs personal data to show them.
"""
from pathlib import Path

ABOUT_DOCUMENTS = {
    'why': ('Why Nettalabbo?', 'WHY_NETTALABBO.md'),
    'credits': ('Credits & Legal Terms', 'CREDITS.md'),
    'warning': ('Experimental Software & Disclaimer', 'DISCLAIMER.md'),
    'licence': ('MIT License', 'LICENSE'),
}


def load_about_document(key, roots=None):
    """Return (window title, bundled content), or raise FileNotFoundError."""
    title, name = ABOUT_DOCUMENTS[key]
    if roots is None:
        roots = (Path(__file__).resolve().parent, Path('/usr/share/doc/nettalabbo'))
    for root in roots:
        file = Path(root) / name
        try:
            return title, file.read_text(encoding='utf-8')
        except FileNotFoundError:
            continue
    raise FileNotFoundError('About document not installed: ' + name)
