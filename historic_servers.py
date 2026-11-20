"""Hand-curated directory of historic and still-running public remote systems.

These are public documentation references, NOT runtime availability claims.
A selected item pre-fills a connection form; no automatic connection occurs.
"""
from __future__ import annotations

HISTORIC_SERVERS = (
    {'id':'iscabbs','name':'ISCABBS (1989)','host':'bbs.iscabbs.com','port':23,'access':'telnet',
     'description':'Long-running public bulletin board system from 1989.',
     'note':'Public Telnet BBS. Never enter confidential passwords over Telnet.',
     'url':'https://iscabbs.rocks/connect-to-iscabbs.html'},
    {'id':'telehack','name':'Telehack','host':'telehack.com','port':23,'access':'telnet',
     'description':'Interactive historical terminal and online computer museum.',
     'note':'An accessible environment for trying vintage commands; availability can change.',
     'url':'https://telehack.com/telehack.html'},
    {'id':'fics','name':'Free Internet Chess Server (1995)','host':'freechess.org','port':5000,'access':'telnet',
     'description':'Text-based public chess server (FICS).',
     'note':'Guest or registered access; type commands in the terminal after connecting.',
     'url':'https://www.freechess.org/'},
    {'id':'aardwolf','name':'Aardwolf MUD (1996)','host':'aardmud.org','port':4000,'access':'telnet',
     'description':'Long-running multi-user text adventure game.',
     'note':'The project documents Telnet ports 23, 4000 and 4010.',
     'url':'https://www.aardwolf.com/play/index.htm'},
    {'id':'batmud','name':'BatMUD (1990)','host':'batmud.bat.org','port':23,'access':'telnet',
     'description':'Long-running fantasy multiplayer text adventure.',
     'note':'Port 2023 is also listed in the official documentation.',
     'url':'https://www.bat.org/client-plugins'},
    {'id':'mapscii','name':'MapSCII world map','host':'mapscii.me','port':23,'access':'telnet',
     'description':'Zoomable world map drawn in the terminal with Braille and ASCII characters.',
     'note':'Use the arrow keys, a and z to zoom, q to quit. Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://github.com/rastapasta/mapscii'},
    {'id':'starwars','name':'Star Wars ASCII animation','host':'towel.blinkenlights.nl','port':23,'access':'telnet',
     'description':'The classic Star Wars Episode IV animation in ASCII characters.',
     'note':'Reachable over IPv6 only: it works only if your connection has IPv6. Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'telnetwiki','name':'Wikipedia over Telnet','host':'telnet.wiki.gd','port':23,'access':'telnet',
     'description':'Live Wikipedia articles in a text terminal, with an AI assistant.',
     'note':'Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'doom','name':'Doom in the terminal','host':'doom.w-graj.net','port':666,'access':'telnet',
     'description':'Plays the classic Doom game rendered as text.',
     'note':'Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'macdemo','name':'Classic Mac desktop demo','host':'www.vintagecomputing.com','port':1984,'access':'telnet',
     'description':'A 1984-style Macintosh desktop drawn in text, with mouse support.',
     'note':'Works best in a terminal with mouse reporting. Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'nyan','name':'NyanCat alternative','host':'halite.md.vc','port':23,'access':'telnet',
     'description':'Animated cat in ANSI colours.',
     'note':'Press Ctrl+] then type quit to leave a looping animation in a standard telnet client; in Nettalabbo use Disconnect. Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'galacticomm','name':'Galacticomm BBS','host':'gcomm.com','port':23,'access':'telnet',
     'description':'Bulletin board running Galacticomm, a classic 1980s and 1990s BBS platform.',
     'note':'Public BBS. Never reuse real passwords over Telnet. Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'archaic','name':'Archaic Binary BBS','host':'bbs.archaicbinary.net','port':23,'access':'telnet',
     'description':'Retro bulletin board with message areas and door games.',
     'note':'Public BBS. Never reuse real passwords over Telnet. Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'lord','name':'Legend of the Red Dragon','host':'lord.stabs.org','port':23,'access':'telnet',
     'description':'The famous BBS door game from 1989, still played online.',
     'note':'Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'achaea','name':'Achaea, Dreams of Divine Lands','host':'achaea.com','port':23,'access':'telnet',
     'description':'Long-running fantasy text role-playing game (MUD).',
     'note':'Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://www.achaea.com/'},
    {'id':'avalon','name':'Avalon: The Legend Lives','host':'avalon-rpg.com','port':23,'access':'telnet',
     'description':'One of the oldest online text role-playing games, started in 1989.',
     'note':'Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'zombiemud','name':'ZombieMUD','host':'zombiemud.org','port':23,'access':'telnet',
     'description':'Multi-user text adventure game.',
     'note':'Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'igormud','name':'Igor MUD','host':'igormud.org','port':1701,'access':'telnet',
     'description':'Long-running multi-user text adventure game.',
     'note':'Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'forgotten','name':'Forgotten Kingdoms','host':'forgottenkingdoms.org','port':4000,'access':'telnet',
     'description':'Role-play focused fantasy MUD.',
     'note':'Listed as online by telnet.org (list updated 11 November 2026).',
     'url':'https://telnet.org/htm/places.htm'},
    {'id':'nyx','name':'Nyx public UNIX (1986)','host':'nyx.nyx.net','port':22,'access':'ssh',
     'description':'Historic public-access UNIX system offering shell and community services.',
     'note':'Official 2026 website specifies nyx.nyx.net via SSH for validated accounts. Telnet access is unconfirmed. SSH host key was updated in May 2026.',
     'url':'https://www.nyx.net/'},
    {'id':'sdf','name':'SDF public UNIX (1987)','host':'tty.sdf.org','port':22,'access':'ssh',
     'description':'Historic community UNIX service with Gopher, mail and shell tools.',
     'note':'For initial signup the official instructions show ssh new@tty.sdf.org.',
     'username':'new','url':'https://wiki.sdf.org/doku.php?id=logging_in_to_sdf_servers'},
    {'id':'panix','name':'Panix (1989)','host':'shell.panix.com','port':22,'access':'ssh',
     'description':'Historic commercial public shell service.',
     'note':'An existing account is required. Use SSH rather than unencrypted Telnet.',
     'url':'https://www.panix.com/help/serverinfo.html'},
    {'id':'eskimo','name':'Eskimo North (1980s)','host':'eskimo.com','port':22,'access':'ssh',
     'description':'Historic shell and hosting provider, offering UNIX access.',
     'note':'Account required; exact host for your subscription may differ.',
     'url':'https://www.eskimo.com/services/shells/servers/'},
    {'id':'well','name':'The WELL (1985)','host':'well.com','port':None,'access':'reference',
     'description':'Long-lived California online community, accessed through official services.',
     'note':'Web reference only. No public Telnet endpoint verified for this release.',
     'url':'https://www.well.com/'},
    {'id':'tilde','name':'Tildeverse','host':'tildeverse.org','port':None,'access':'reference',
     'description':'Directory of independent community UNIX and tilde servers.',
     'note':'Discover a specific member server and consult its access instructions.',
     'url':'https://tildeverse.org/'},
    {'id':'horizons','name':'NASA JPL Horizons','host':'ssd.jpl.nasa.gov','port':None,'access':'reference',
     'description':'Solar-system ephemeris terminal. The old plaintext Telnet connection was replaced by TLS.',
     'note':'From October 2026, follow the NASA TLS wrapper instructions. Direct Telnet to remote port 6775 may no longer work.',
     'url':'https://ssd.jpl.nasa.gov/horizons/horizons_tls_access.html'},
)


def get_entry(entry_id):
    return next((entry for entry in HISTORIC_SERVERS if entry['id']==entry_id), None)


def catalog_groups(kind):
    if kind=='telnet':
        return tuple(item for item in HISTORIC_SERVERS if item['access']=='telnet')
    if kind=='ssh':
        return tuple(item for item in HISTORIC_SERVERS if item['access']=='ssh')
    if kind=='reference':
        return tuple(item for item in HISTORIC_SERVERS if item['access']=='reference')
    return ()


def connection_fields(entry):
    if not entry or entry['access'] not in ('ssh','telnet'):
        return None
    return ('SSH' if entry['access']=='ssh' else 'Telnet',entry['host'],
            int(entry['port']),entry.get('username',''))


def access_label(entry):
    """Display only access that the service actually documents."""
    access=entry.get('access','reference')
    return {'ssh':'SSH', 'telnet':'Telnet', 'reference':'Web / TLS'}.get(access,'Reference')


def protocol_endpoint(entry, page):
    """Choose appropriate host and port without inventing documented support.

    Both protocols can be manually attempted, but unsupported options must
    be explicitly flagged to the UI.
    """
    if page not in ('SSH','Telnet'):
        raise ValueError('Choose SSH or Telnet')
    documented=entry.get('access')==page.lower()
    port=int(entry['port']) if documented and entry.get('port') else (22 if page=='SSH' else 23)
    user=entry.get('username','') if documented and page=='SSH' else ''
    return entry['host'],port,user,documented
