"""Domain Inspector: standards-based IANA bootstrap and public RDAP discovery.

Independent implementation. No third-party API keys or libraries required.
Network access is initiated only by the user pressing Look up.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BOOTSTRAP_URL = 'https://data.iana.org/rdap/dns.json'
TLD_REGISTRY_URL = 'https://data.iana.org/TLD/v1/tlds.json'
TLD_CACHE_SECONDS = 86400
MAX_TLD_BYTES = 16 * 1024 * 1024
MAX_WHOIS_BYTES = 512 * 1024
MAX_JSON_BYTES = 3 * 1024 * 1024
HEADERS = {'Accept': 'application/rdap+json, application/json;q=0.9',
           'User-Agent': 'Nettalabbo/0.3.6 (independent registry discovery client)'}


class LookupError(Exception):
    """A user-readable discovery or lookup error."""


def normalise_domain(value: str) -> str:
    """Accept a domain or pasted URL and return ASCII IDNA domain."""
    s = value.strip()
    if '://' in s:
        parsed = urllib.parse.urlsplit(s)
        s = parsed.hostname or ''
    else:
        s = s.split('/')[0].split('?')[0].split('#')[0]
    s = s.strip().strip('.').lower()
    if not s or ':' in s or '@' in s or '\\' in s:
        raise LookupError('Enter a domain such as example.org, not an IP address or email.')
    try:
        labels = [label.encode('idna').decode('ascii') for label in s.split('.')]
    except UnicodeError as e:
        raise LookupError('Invalid internationalised domain name.') from e
    if len(labels) < 2 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', x) for x in labels):
        raise LookupError('The domain name is invalid. Example: example.org')
    domain = '.'.join(labels)
    if len(domain) > 253 or labels[-1].isdigit():
        raise LookupError('The domain name is invalid or too long.')
    return domain


def _fetch_json(url: str, timeout=12, max_bytes=MAX_JSON_BYTES) -> dict:
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise LookupError('Only encrypted HTTPS RDAP services are allowed.')
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if urllib.parse.urlsplit(resp.geturl()).scheme != 'https':
                raise LookupError('RDAP service redirected to unencrypted HTTP.')
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise LookupError('The RDAP response is too large.')
            obj = json.loads(data.decode('utf-8'))
            if not isinstance(obj, dict):
                raise LookupError('The RDAP service returned an unexpected format.')
            return obj
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LookupError('Domain not found by this RDAP server (HTTP 404). This does not prove availability.') from e
        if e.code == 429:
            raise LookupError('The RDAP server is rate limiting requests. Try again later.') from e
        raise LookupError(f'RDAP server responded with HTTP {e.code}.') from e
    except urllib.error.URLError as e:
        raise LookupError(f'Unable to contact the RDAP server: {e.reason}') from e
    except (TimeoutError, UnicodeDecodeError, ValueError) as e:
        raise LookupError(f'Could not decode the RDAP response: {e}') from e


def bootstrap_services(domain: str, bootstrap: dict) -> tuple[str, list[str]]:
    """RFC 9224: select the longest matching DNS suffix in the IANA bootstrap file."""
    best = None
    for entry in bootstrap.get('services', []):
        if len(entry) != 2:
            continue
        suffixes, servers = entry
        for suffix in suffixes:
            suffix = str(suffix).lower().strip('.')
            if domain == suffix or domain.endswith('.' + suffix):
                if best is None or len(suffix) > len(best[0]):
                    best = (suffix, [x for x in servers if isinstance(x, str) and x.startswith('https://')])
    if not best or not best[1]:
        raise LookupError('IANA lists no public RDAP server for this domain extension. Try Raw WHOIS manually.')
    return best


def load_bootstrap(cache_file: Path) -> tuple[dict, str]:
    """Fetch IANA over HTTPS. Use a local cache (up to 24h old) when possible."""
    if cache_file.is_file():
        try:
            age = dt.datetime.now().timestamp() - cache_file.stat().st_mtime
            if age < 86400:
                data = json.loads(cache_file.read_text(encoding='utf-8'))
                if data.get('services'):
                    return data, 'IANA bootstrap (local cache)'
        except (OSError, ValueError):
            pass
    try:
        data = _fetch_json(BOOTSTRAP_URL)
        if not isinstance(data.get('services'), list):
            raise LookupError('Invalid IANA bootstrap registry.')
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data), encoding='utf-8')
        except OSError:
            pass
        return data, 'IANA bootstrap (online)'
    except LookupError:
        if cache_file.is_file():
            try:
                data = json.loads(cache_file.read_text(encoding='utf-8'))
                if data.get('services'):
                    return data, 'IANA bootstrap (older offline cache)'
            except (OSError, ValueError):
                pass
        raise


def _card_values(entity: dict, keys: tuple[str, ...]) -> list[str]:
    values = []
    card = entity.get('vcardArray')
    if isinstance(card, list) and len(card) > 1 and isinstance(card[1], list):
        for item in card[1]:
            if isinstance(item, list) and len(item) >= 4 and item[0].lower() in keys:
                val = item[3]
                if isinstance(val, str) and val.strip():
                    values.append(val.strip())
    jscard = entity.get('jscard')
    if isinstance(jscard, dict):
        for key in ('fullName', 'name', 'organisation', 'organization'):
            value = jscard.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    return list(dict.fromkeys(values))


def _entities_for(data: dict, role: str) -> list[dict]:
    found = []
    def visit(entity):
        if not isinstance(entity, dict):
            return
        if role in entity.get('roles', []):
            found.append(entity)
        for child in entity.get('entities', []):
            visit(child)
    for item in data.get('entities', []):
        visit(item)
    return found


def _entity_names(entities: list[dict]) -> list[str]:
    names = []
    for ent in entities:
        names += _card_values(ent, ('fn', 'org'))
        if not names:
            handle = ent.get('handle')
            if handle:
                names.append(str(handle) + ' (identifier only)')
    return list(dict.fromkeys(names))


def summarise_rdap(domain: str, matched_suffix: str, service: str, bootstrap_source: str, data: dict) -> tuple[list[tuple[str, str]], str]:
    registrar = _entity_names(_entities_for(data, 'registrar'))
    registrant = _entity_names(_entities_for(data, 'registrant'))
    registry = _entity_names(_entities_for(data, 'registry'))
    events = {}
    for event in data.get('events', []):
        if not isinstance(event, dict):
            continue
        event_type = event.get('eventAction', '')
        event_date = event.get('eventDate', '')
        if event_type and event_date:
            events.setdefault(event_type, event_date)
    servers = []
    for ns in data.get('nameservers', []):
        value = ns.get('ldhName') or ns.get('unicodeName') if isinstance(ns, dict) else None
        if value:
            servers.append(value)
    statuses = [str(x) for x in data.get('status', [])]
    dnssec = data.get('secureDNS', {})
    dnssec_status = 'Signed' if dnssec.get('delegationSigned') is True else ('Not signed' if dnssec.get('delegationSigned') is False else 'Not disclosed')
    # Missing public registrant details do not establish that a domain is unowned.
    owner = ', '.join(registrant) if registrant else 'Not disclosed in the public RDAP response'
    rows = [
        ('Domain', data.get('ldhName') or domain),
        ('Domain extension', '.' + matched_suffix),
        ('Registry RDAP server', service),
        ('Registry operator', ', '.join(registry) if registry else 'Not identified in this response'),
        ('Registrar', ', '.join(registrar) if registrar else 'Not disclosed'),
        ('Registrant / public holder', owner),
        ('Registered', events.get('registration', 'Not published')),
        ('Expires', events.get('expiration', 'Not published')),
        ('Last changed', events.get('last changed', 'Not published')),
        ('Domain status', ', '.join(statuses) if statuses else 'Not published'),
        ('DNSSEC', dnssec_status),
        ('Nameservers', ', '.join(servers) if servers else 'Not published'),
        ('Source', bootstrap_source),
    ]
    lines = ['DOMAIN INSPECTOR', '=' * 68, '',
             f'The authoritative lookup endpoint was identified from {bootstrap_source}.',
             'Registry = manager of the extension. Registrar = registration provider.',
             'Registrant = domain holder, when publicly disclosed.', '',
             'PUBLIC REGISTRATION DATA', '-' * 68]
    lines += [f'{key}: {value}' for key, value in rows]
    notices = [n.get('title', '') for n in data.get('notices', []) if isinstance(n, dict)]
    if notices:
        lines += ['', 'RDAP NOTICES', '-' * 68] + [str(x) for x in notices if x]
    if data.get('redacted'):
        lines += ['', 'The RDAP response marks some fields as redacted.']
    lines += ['', 'Privacy note: public RDAP may conceal registrant details.',
              'The absence of a name does not establish who owns the domain.',
              'Status and expiration dates are published by the registry and may vary.',
              '']
    return rows, '\n'.join(lines)


# Nettalabbo 0.3.6: IANA publishes a full machine-readable TLD registry,
# including brand TLDs, country-code TLDs, operator names, RDAP and WHOIS.
# https://www.iana.org/domains/root/files

def _load_tld_registry(cache_file: Path) -> tuple[dict, str]:
    """Read current official root registry (all public TLDs) with offline cache."""
    if cache_file.exists():
        try:
            if time.time() - cache_file.stat().st_mtime < TLD_CACHE_SECONDS:
                document = json.loads(cache_file.read_text(encoding='utf-8'))
                if isinstance(document.get('domains'), list):
                    return document, 'IANA TLD registry (cached)'
        except (OSError, ValueError):
            pass
    try:
        document = _fetch_json(TLD_REGISTRY_URL, timeout=20, max_bytes=MAX_TLD_BYTES)
        if not isinstance(document.get('domains'), list):
            raise LookupError('IANA returned an invalid TLD registry document.')
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(document), encoding='utf-8')
        except OSError:
            pass
        return document, 'IANA TLD registry (online)'
    except LookupError:
        if cache_file.exists():
            try:
                document = json.loads(cache_file.read_text(encoding='utf-8'))
                if isinstance(document.get('domains'), list):
                    return document, 'IANA TLD registry (older cached copy)'
            except (OSError, ValueError):
                pass
        raise


def tld_record(domain: str, root: dict) -> dict | None:
    """Find the exact TLD in IANA's record, including IDN and brand TLDs."""
    extension = domain.rsplit('.', 1)[-1].lower()
    for item in root.get('domains', []):
        if isinstance(item, dict) and item.get('name', '').lower() == extension:
            return item
    return None


def _whois_query(domain: str, server: str, timeout=10) -> str:
    """Query the authoritative WHOIS server selected from IANA (port 43)."""
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', server) or '..' in server:
        raise LookupError('IANA returned an invalid WHOIS server hostname.')
    parts = []
    total = 0
    try:
        with socket.create_connection((server, 43), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall((domain + '\r\n').encode('ascii'))
            while total < MAX_WHOIS_BYTES:
                block = connection.recv(min(32768, MAX_WHOIS_BYTES - total))
                if not block:
                    break
                parts.append(block)
                total += len(block)
    except (OSError, socket.timeout) as e:
        raise LookupError(f'Cannot contact WHOIS server {server}: {e}') from e
    text = b''.join(parts).decode('utf-8', errors='replace').strip()
    if not text:
        raise LookupError(f'The WHOIS server {server} returned no data.')
    if total >= MAX_WHOIS_BYTES:
        text += '\n[Response truncated at 512 KiB]'
    return text


def parse_whois(text: str) -> dict:
    """Best effort: labels differ by registry; never guess a private owner."""
    fields = {}
    section = ''
    for line in text.splitlines():
        item = line.strip()
        if not item or item.startswith(('%', '#', '>>>', 'NOTICE:', 'TERMS OF USE:')):
            continue
        # Registries such as .it group registrant and registrar fields under headings.
        if item.lower().rstrip(':') in ('registrant', 'registrar', 'admin contact', 'tech contact'):
            section = item.lower().rstrip(':')
            continue
        match = re.match(r'^([A-Za-z][A-Za-z0-9 _./-]{1,55}):\s*(.*)$', item)
        if not match:
            continue
        key = re.sub(r'[^a-z0-9]', '', match.group(1).lower())
        value = match.group(2).strip()
        if not value or value in ('-', 'N/A'):
            continue
        if section in ('registrant', 'registrar') and key in ('name', 'organization', 'organisation', 'org', 'contact'):
            key = section + key
        fields.setdefault(key, []).append(value)
    return fields


def _first_whois(fields: dict, *names: str) -> str:
    for name in names:
        values = fields.get(name, [])
        for value in values:
            if value and not re.search(r'(redact|privacy protected|not disclosed|withheld|data protected)', value, re.I):
                return value
    return ''


def summarise_whois(domain: str, record: dict, server: str, raw: str, source: str) -> tuple[list[tuple[str, str]], str]:
    """Expose source and raw output; parsers are approximate and non-authoritative."""
    f = parse_whois(raw)
    manager = (record.get('manager') or {}).get('organization', '')
    registrar = _first_whois(f, 'registrarorganization', 'registrar', 'registrarname', 'sponsoringregistrar', 'registrarorg', 'registrarid')
    registrant = _first_whois(f, 'registrantorganization', 'registrantorganisation', 'registrantname', 'registrantorg', 'ownerorganization', 'ownername', 'owner', 'holder')
    rows = [
        ('Domain', domain),
        ('Domain extension', '.' + domain.rsplit('.', 1)[-1]),
        ('Registry operator', manager or 'Not listed by IANA'),
        ('Registration data protocol', 'WHOIS (port 43)'),
        ('WHOIS server', server),
        ('Registrar', registrar or 'Not disclosed or not recognisable'),
        ('Registrant / public holder', registrant or 'Not disclosed or not recognisable'),
        ('Registered', _first_whois(f, 'created', 'createddate', 'creationdate', 'registered', 'registrationtime') or 'Not published'),
        ('Expires', _first_whois(f, 'expire', 'expirydate', 'expirationdate', 'registryexpirydate', 'paidtill', 'renewaldate') or 'Not published'),
        ('Last changed', _first_whois(f, 'updated', 'updateddate', 'lastupdated', 'changed', 'lastmodified') or 'Not published'),
        ('Domain status', _first_whois(f, 'status', 'domainstatus') or 'Not published'),
        ('Source', source),
    ]
    text = ('DOMAIN INSPECTOR\n' + '=' * 68 + '\n'
            + 'Lookup service: WHOIS selected from IANA or your custom registry setting.\n'
            + 'WHOIS fields differ between registries; check the raw response below.\n'
            + 'No value labelled as a holder proves legal ownership.\n\n'
            + '\n'.join(f'{key}: {val}' for key, val in rows)
            + '\n\nRAW WHOIS RESPONSE\n' + '-' * 68 + '\n' + raw + '\n')
    return rows, text


def _custom_match(domain: str, custom: list[dict]) -> dict | None:
    candidates = []
    for item in custom:
        if not isinstance(item, dict):
            continue
        suffix = str(item.get('suffix', '')).lower().strip().strip('.')
        if suffix and (domain == suffix or domain.endswith('.' + suffix)):
            candidates.append((len(suffix), item))
    return max(candidates, key=lambda c: c[0])[1] if candidates else None


def _result_for_rdap(domain: str, source: str, root_record: dict, url_base: str) -> tuple[list[tuple[str, str]], str, dict]:
    url = url_base.rstrip('/') + '/domain/' + urllib.parse.quote(domain, safe='.-')
    data = _fetch_json(url)
    matched = domain.rsplit('.', 1)[-1]
    rows, report = summarise_rdap(domain, matched, url_base, source, data)
    manager = (root_record.get('manager') or {}).get('organization')
    if manager:
        rows = [(key, manager if key == 'Registry operator' else val) for key, val in rows]
        report = report.replace('Registry operator: Not identified in this response', f'Registry operator: {manager}')
    return rows, report + f'RDAP query: {url}\n', data


def lookup_domain(value: str, cache_file: Path, custom_services: list[dict] | None = None) -> tuple[list[tuple[str, str]], str, dict]:
    """Automatic discovery: custom private services, IANA RDAP, then IANA WHOIS.

    All public root TLDs are read from IANA's maintained machine-readable
    registry, not a hard-coded list. A private suffix requires explicit configuration.
    """
    domain = normalise_domain(value)
    custom = _custom_match(domain, custom_services or [])
    if custom:
        protocol = str(custom.get('protocol', '')).lower()
        server = str(custom.get('endpoint', '')).strip()
        if protocol == 'rdap':
            if not server.startswith('https://'):
                raise LookupError('A custom RDAP endpoint must use HTTPS.')
            return _result_for_rdap(domain, 'User configured RDAP server (not IANA)', {}, server)
        if protocol == 'whois':
            raw = _whois_query(domain, server)
            rows, report = summarise_whois(domain, {}, server, raw, 'User configured WHOIS server (not IANA)')
            return rows, report, {'whois_raw': raw}
        raise LookupError('Invalid custom registry protocol; choose RDAP or WHOIS.')

    root, source = _load_tld_registry(cache_file.with_name('tld_registry.json'))
    record = tld_record(domain, root)
    if not record:
        raise LookupError('The extension is not found in the public IANA root. '
                          'It may be an internal or alternative-root domain. '
                          'Choose Custom registries to configure a private RDAP or WHOIS service.')
    if record.get('status') != 'active':
        raise LookupError(f'The extension .{domain.rsplit(".", 1)[-1]} is listed by IANA as '
                          f'{record.get("status", "not active")}; public registration lookup is not available.')
    endpoints = [url for url in record.get('rdap_base_urls', []) if isinstance(url, str) and url.startswith('https://')]
    whois_server = record.get('whois_server')
    errors = []
    for base in endpoints:
        try:
            return _result_for_rdap(domain, source, record, base)
        except LookupError as exc:
            errors.append(str(exc))
    if whois_server:
        try:
            raw = _whois_query(domain, whois_server)
            rows, report = summarise_whois(domain, record, whois_server, raw, source)
            if errors:
                report += '\nRDAP attempts failed: ' + '; '.join(errors) + '\n'
            return rows, report, {'whois_raw': raw}
        except LookupError as exc:
            errors.append(str(exc))
    # Even when no domain-level registration service exists, IANA's TLD
    # operator is still useful: distinguish registry discovery from ownership.
    manager = (record.get('manager') or {}).get('organization') or 'Not listed by IANA'
    rows = [('Domain', domain), ('Domain extension', '.' + domain.rsplit('.', 1)[-1]),
            ('Registry operator', manager), ('TLD category', record.get('type', 'Not listed')),
            ('Registration data', 'Unavailable from the advertised public services'),
            ('IANA RDAP servers', ', '.join(endpoints) or 'None published'),
            ('IANA WHOIS server', whois_server or 'None published'), ('Source', source)]
    details = '\n'.join(f'{key}: {val}' for key, val in rows)
    report = 'DOMAIN INSPECTOR\n' + '=' * 68 + '\n' + details + '\n'
    if errors:
        report += '\nService errors: ' + '; '.join(errors) + '\n'
    report += '\nRegistry discovered. Registrant information could not be retrieved.\n'
    return rows, report, {'tld_record': record, 'errors': errors}
