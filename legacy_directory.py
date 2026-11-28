"""Plain-language directory of the services the Legacy Navigator can open.

Shown as the Navigator's start page, so people can see what each service is
and try it with one click. Examples are public services documented as active;
where no verified public example exists, none is given.
"""

# key, title, short label for the index, explanation
GROUPS = [
    ('ready', 'Ready to browse', 'Read',
     'Open and read these directly in Nettalabbo.'),
    ('experimental', 'Experimental readers', 'Experimental',
     'Newer or rarer protocols. Basic reading works, but public servers are few and change often: '
     'if you know one, type its address in the bar above.'),
    ('remote', 'Interactive terminals', 'Terminals',
     'Bulletin boards, games and public UNIX systems open in the Telnet or SSH page.'),
    ('upload', 'Upload', 'Upload',
     'Sending files, only when you choose a file and confirm.'),
    ('reference', 'Not yet available', 'Coming later',
     'Listed so you know they exist; Nettalabbo cannot open them yet.'),
]

# name, group, address form, plain description, [(example label, url)]
SERVICES = [
    ('Gopher', 'ready', 'gopher://',
     'Menus of links and plain text: how the Internet was browsed before the Web (1991). '
     'Still kept alive by enthusiasts.',
     [('Floodgap, the best-known Gopher server', 'gopher://gopher.floodgap.com/1')]),
    ('Gemini', 'ready', 'gemini://',
     'A modern, minimal alternative to the Web (2019): simple text pages over encrypted connections.',
     [('Gemini project home', 'gemini://geminiprotocol.net/'),
      ('Kennedy, a search engine for Gemini', 'gemini://kennedy.gemi.dev/')]),
    ('Spartan', 'ready', 'spartan://',
     'A cousin of Gemini without encryption, so it is very simple to run and to read.',
     [('tilde.cafe community server', 'spartan://tilde.cafe/')]),
    ('Finger', 'ready', 'finger://',
     'Ask a server about a person or a topic (1971). Some servers answer with weather or news.',
     [('Weather forecast for Oslo (replace oslo with your city)', 'finger://graph.no/oslo')]),
    ('DICT', 'ready', 'dict://',
     'Dictionary definitions from public dictionary servers.',
     [('Look up "hello" on dict.org', 'dict://dict.org:2628/hello')]),
    ('Anonymous FTP', 'ready', 'ftp://',
     'Browse public file archives, read only.',
     [('GNU project archive', 'ftp://ftp.gnu.org/gnu/')]),
    ('Usenet / NNTP', 'ready', 'nntp://',
     'Discussion groups from the 1980s that are still active. The Newsgroups page is a full reader: '
     'threads, replies and posting, anonymously or with an account.',
     [('Open the Newsgroups reader (Paganini, Gmane, Eternal September and more)', 'nettalabbo:newsgroups')]),
    ('Nex', 'ready', 'nex://',
     'Directory listings and plain text in the simplest possible protocol.',
     [('Nightfall City community', 'nex://nightfall.city/')]),
    ('Scroll', 'experimental', 'scroll://', 'Gemini-like documents with extra metadata.', []),
    ('Text / SuperText', 'experimental', 'text://', 'Plain text documents served on port 1961.', []),
    ('Guppy', 'experimental', 'guppy://', 'Gemini-like pages sent over UDP instead of TCP.', []),
    ('Mercury', 'experimental', 'mercury://', 'Gemini without encryption, plain text only.', []),
    ('Scorpion', 'experimental', 'scorpion://', 'Read-only documents from Scorpion servers.', []),
    ('Molerat', 'experimental', 'molerat://', 'Early alpha protocol; read-only retrieval.', []),
    ('Telnet / SSH', 'remote', 'telnet:// · ssh://',
     'Live text sessions with bulletin boards (BBS), games (MUD) and public UNIX systems.',
     [('Open the catalogue of public Telnet and SSH services', 'nettalabbo:catalogue')]),
    ('Titan', 'upload', 'titan://',
     'Upload a file to a Gemini capsule that accepts uploads. Use the Titan upload button.',
     []),
    ('Terse', 'reference', 'terse://',
     'Under research: no verified specification yet.',
     []),
]

NO_EXAMPLE = 'No verified public example yet: type an address in the bar above.'


def services_by_group():
    """[(group key, title, short label, explanation, [service, ...]), ...] in display order."""
    return [(key, title, short, explanation, [s for s in SERVICES if s[1] == key])
            for key, title, short, explanation in GROUPS]


def anchor(name):
    """Tk tag and mark names must not contain spaces."""
    return ''.join(c if c.isalnum() else '_' for c in name)
