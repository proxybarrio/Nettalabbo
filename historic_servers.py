"""Hand-curated historic remote-system directory for Nettalabbo.

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
