"""Safe, original presentation for legacy-network results.

Keep wire data separate from readable clickable view. No HTML interpretation.
All links are extracted only from protocol parsers; no arbitrary terminal escape
sequences are executed by the Tk text widget.
"""
from urllib.parse import urlsplit
import re

# Only explicitly supported protocols and external HTTP(S) may be clicked.
# No file://, javascript:, data:, or shell command execution.
CLICKABLE_SCHEMES = frozenset((
    'gopher', 'gophers', 'gemini', 'spartan', 'nex', 'scroll',
    'finger', 'news', 'nntp', 'telnet', 'ssh', 'ftp', 'dict',
    'scorpion', 'scorpions', 'guppy', 'text', 'molerat',
    'mercury', 'titan', 'http', 'https'
))
INLINE_URL_RE = re.compile(
    r'''(?i)(?<![\w@])(?:(?:[a-z][a-z0-9+.-]*://)|www\.)[^\s<>"'`]+'''
)
TRAILING_PUNCTUATION = '.!?,;:"\''


def url_in_text(value):
    """Return a safe, recognised link target, or None."""
    target = ('https://' + value) if value.lower().startswith('www.') else value
    try:
        parts = urlsplit(target)
        if parts.scheme.lower() not in CLICKABLE_SCHEMES or not parts.hostname:
            return None
        # A malformed port must not crash rendering.
        _ = parts.port
        if parts.username or parts.password:
            return None
    except ValueError:
        return None
    return target


def inline_segments(kind, text):
    """Hyperlink plain-text URLs without altering surrounding whitespace."""
    output = []
    pos = 0
    for match in INLINE_URL_RE.finditer(text):
        token = match.group(0)
        candidate = token.rstrip(TRAILING_PUNCTUATION)
        while candidate.endswith((')', ']', '}')):
            closing = candidate[-1]
            opening = {')': '(', ']': '[', '}': '{'}[closing]
            if candidate.count(closing) <= candidate.count(opening):
                break
            candidate = candidate[:-1]
        destination = url_in_text(candidate)
        if not destination:
            continue
        start = match.start()
        end = start + len(candidate)
        if start > pos:
            output.append((kind, text[pos:start], None))
        scheme = urlsplit(destination).scheme.lower()
        if scheme in ('http', 'https', 'ssh', 'telnet'):
            link_kind = 'external'
        elif scheme in ('gopher', 'gophers') and urlsplit(destination).path[:2] in ('/1', '/7'):
            link_kind = 'folder'
        else:
            link_kind = 'document'
        output.append((link_kind, text[start:end], destination))
        pos = end
    if pos < len(text):
        output.append((kind, text[pos:], None))
    return output or [(kind, text, None)]


def distinct_links(pieces):
    """Return the unique navigation targets visible in Rendered mode."""
    found = []
    seen = set()
    for kind, label, destination in pieces:
        if destination and destination not in seen:
            found.append((label.strip().lstrip('▸• '), destination))
            seen.add(destination)
    return found


def linkify_pieces(pieces):
    output = []
    for kind, label, destination in pieces:
        if destination or not label:
            output.append((kind, label, destination))
        else:
            output.extend(inline_segments(kind, label))
    return output



GOPHER_MENU_TYPES = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'g', 'I', 'h', 's', 'i', 'T', '+'}


def segments(result):
    """Return [(kind, text, destination)] suitable for a Tk Text renderer.

    kind is 'text', 'heading', 'info', 'folder', 'document', or 'external'.
    All click targets originate from result.links produced by protocol parsers.
    """
    scheme = (result.protocol or '').lower()
    content = result.content or ''
    links = list(result.links or [])
    pieces = []
    if scheme in ('gopher', 'gophers') and result.status.lower().startswith('gopher'):
        # One item per line, in order. Information rows are never hyperlinks.
        link_index = 0
        for line in content.splitlines():
            if line == '.':
                continue
            if not line:
                pieces.append(('text', '\n', None))
                continue
            marker = line[0]
            label = line[1:].split('\t', 1)[0] if marker in GOPHER_MENU_TYPES else line
            if marker in ('i', '3'):
                pieces.append(('info', label + '\n', None))
            elif marker in GOPHER_MENU_TYPES and link_index < len(links):
                name, address = links[link_index]
                # Only consume for valid items returned by gopher_fetch.
                if name == label:
                    link_index += 1
                    kind = 'folder' if marker in ('1','7') else 'external' if marker in ('8','h') else 'document'
                    pieces.append((kind, ('▸ ' if kind == 'folder' else '• ') + label + '\n', address))
                else:
                    pieces.append(('text', label + '\n', None))
            else:
                pieces.append(('text', label + '\n', None))
        return linkify_pieces(pieces)
    # Gemtext and allied formats share => targets. Preserve headings and text.
    seen = set()
    for line in content.splitlines():
        text = line.lstrip()
        if text.startswith('=>'):
            url_and_label = text[2:].strip().split(None, 1)
            link = next(((title, url) for title, url in links if title == (url_and_label[1] if len(url_and_label) > 1 else url_and_label[0]) and url not in seen), None) if url_and_label else None
            if link:
                title, target = link
                seen.add(target)
                kind = 'external' if urlsplit(target).scheme in ('http', 'https', 'ssh', 'telnet') else 'document'
                pieces.append((kind, '▸ ' + title + '\n', target))
                continue
        if line.startswith('#') and scheme in ('gemini','scroll','spartan','nex','guppy','molerat','text','scorpion','scorpions'):
            pieces.append(('heading', line.lstrip('# ').strip() + '\n', None))
        else:
            pieces.append(('text', line + '\n', None))
    # E.g. redirects or automatically parsed links that are not inline.
    missing = [(title, target) for title, target in links if target not in seen]
    if missing:
        pieces.append(('heading', '\nRelated links\n', None))
        for title, target in missing:
            pieces.append(('external' if urlsplit(target).scheme in ('http','https','ssh','telnet') else 'document',
                           '▸ ' + title + '\n', target))
    return linkify_pieces(pieces)


def raw_text(result):
    """Show the actual raw server response when retained by the adapter.

    Fallback is explicitly labelled body-only rather than falsely claiming to
    reconstruct the unmodified response when a parser discarded metadata.
    """
    wire = getattr(result, 'raw_response', b'')
    if getattr(result, 'is_file', False):
        return file_hex_dump(wire)
    if wire:
        return wire.decode('utf-8', errors='replace')
    return ('Raw transport bytes were not retained by this protocol adapter.\n'
            'The following is the decoded response body, without formatting.\n\n'
            + (result.content or ''))


def file_hex_dump(data, limit=512):
    """First bytes of a file as a classic hex dump (offset, hex, printable)."""
    lines = ['File, {:,} bytes. First {} bytes:'.format(len(data), min(limit, len(data))), '']
    for offset in range(0, min(limit, len(data)), 16):
        chunk = data[offset:offset + 16]
        hexpart = ' '.join('{:02x}'.format(b) for b in chunk)
        text = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append('{:08x}  {:<47}  {}'.format(offset, hexpart, text))
    return '\n'.join(lines) + '\n'


def link_color(kind):
    return {'folder': '#1458ad', 'document': '#137044', 'external': '#ac4c0d'}[kind]
