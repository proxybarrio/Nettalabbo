"""Suggested servers for the classic WhoIs and Quote of the Day tools.

Current servers come first; historic ones, which may no longer answer, follow.
"""

WHOIS_SERVERS = [
    ('whois.iana.org', 'IANA: root of the WHOIS tree; Nettalabbo follows its referral.'),
    ('whois.nic.it', 'Registro .it (IIT-CNR).'),
    ('whois.verisign-grs.com', 'Verisign: .com and .net registry.'),
    ('whois.ripe.net', 'RIPE NCC: IP addresses for Europe, Middle East, Central Asia.'),
    ('whois.arin.net', 'ARIN: IP addresses for North America.'),
    ('whois.apnic.net', 'APNIC: IP addresses for Asia Pacific.'),
    ('whois.lacnic.net', 'LACNIC: IP addresses for Latin America.'),
    ('whois.afrinic.net', 'AFRINIC: IP addresses for Africa.'),
    ('rs.internic.net', 'Historic WhoIs server (InterNIC). It may no longer answer.'),
    ('nic.ddn.mil', 'Historic WhoIs server (DDN NIC). Long retired.'),
]

QUOTE_SERVERS = [
    ('djxmmx.net', 'Public QOTD server, TCP and UDP port 17.'),
    ('um.imstillthinking.net', 'Public QOTD server, TCP port 17.'),
    ('alpha.mike-r.com', 'Public QOTD server, TCP port 17.'),
    ('quotes.ipswitch.com', 'Historic QOTD server. It may no longer answer.'),
    ('www.ipctech.com', 'Historic QOTD server. It may no longer answer.'),
    ('www.rmm.com', 'Historic QOTD server. It may no longer answer.'),
]

CATALOGS = {'WhoIs_server': WHOIS_SERVERS, 'Quote_host': QUOTE_SERVERS}


def suggestions(key):
    return [host for host, _note in CATALOGS.get(key, [])]


def note(host):
    host = (host or '').strip().lower()
    for catalog in CATALOGS.values():
        for name, text in catalog:
            if name == host:
                return text
    return ''


def whois_referral(response):
    """Server named by an IANA reply ('refer:' or 'whois:' line), or ''."""
    for line in response.splitlines():
        field, _, value = line.partition(':')
        if field.strip().lower() in ('refer', 'whois') and value.strip():
            candidate = value.strip().split()[0].lower()
            if all(part and all(c.isalnum() or c == '-' for c in part)
                   for part in candidate.split('.')) and '.' in candidate:
                return candidate
    return ''
