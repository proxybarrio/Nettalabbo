"""Presentation palettes for the Legacy Navigator.

Colours are UI-only. Protocol payloads, extracted destinations and Raw output
must not depend on the selected palette.
"""

PALETTES = {
    'Classic': {
        'background': '#f6f1e5', 'foreground': '#292b30',
        'heading': '#355c78', 'info': '#67685f',
        'folder': '#245a88', 'document': '#187563', 'external': '#80579c',
    },
    'Dark': {
        'background': '#17222b', 'foreground': '#e1e8ee',
        'heading': '#e0bc7a', 'info': '#aebecb',
        'folder': '#76b6f1', 'document': '#7fdbb3', 'external': '#d6a5eb',
    },
    'Monochrome': {
        'background': '#101e17', 'foreground': '#9ee1a7',
        'heading': '#c5f6c2', 'info': '#8dbb95',
        'folder': '#a0e2aa', 'document': '#a0e2aa', 'external': '#a0e2aa',
    },
}

THEME_NAMES = tuple(PALETTES)


def palette(name):
    """Unknown settings fall back safely to the Classic appearance."""
    return PALETTES.get(name, PALETTES['Classic']).copy()


def link_legend(name):
    if name == 'Monochrome':
        return 'Underlined: clickable links  ·  Muted: information'
    return 'Blue: menus  ·  Green: documents  ·  Purple: external destinations' if name == 'Classic' else (
        'Light blue: menus  ·  Mint: documents  ·  Lilac: external destinations'
    )
