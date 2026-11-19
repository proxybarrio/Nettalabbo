"""DNS record lookups for the DNS page, using the system's dig.

dig comes from bind9-dnsutils (or dnsutils), already a dependency of the
package. Names and servers are validated before they reach the command line,
which is passed as an argument list, never through a shell.
"""
import ipaddress
import re
import shutil
import subprocess

SYSTEM_ADDRESSES = 'Addresses (system)'
ALL_COMMON = 'All common records'
RECORD_TYPES = [SYSTEM_ADDRESSES, 'A', 'AAAA', 'CNAME', 'MX', 'NS', 'TXT', 'SOA',
                'SRV', 'CAA', 'PTR', ALL_COMMON]
COMMON_TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'NS', 'TXT', 'SOA', 'CAA']
SUGGESTED_SERVERS = ['1.1.1.1', '8.8.8.8', '9.9.9.9', '208.67.222.222']

_LABEL = re.compile(r'[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9])?')
_STATUS = re.compile(r'status:\s*([A-Z]+)')


class DnsLookupError(Exception):
    pass


def _ascii_name(name):
    name = (name or '').strip().rstrip('.')
    if not name:
        raise DnsLookupError('Enter a domain name or an IP address.')
    try:
        ascii_name = name.encode('idna').decode('ascii') if not name.isascii() else name
    except UnicodeError as exc:
        raise DnsLookupError(f'Invalid international domain name: {exc}') from exc
    labels = ascii_name.split('.')
    if len(ascii_name) > 253 or not all(_LABEL.fullmatch(label) for label in labels):
        raise DnsLookupError(f'Not a valid domain name: {name}')
    return ascii_name


def validate_query(name, record):
    """Return (dig arguments for the name, display name); raise on bad input."""
    if record not in RECORD_TYPES:
        raise DnsLookupError(f'Unsupported record type: {record}')
    text = (name or '').strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        address = None
    if address is not None:
        if record not in ('PTR', SYSTEM_ADDRESSES):
            raise DnsLookupError('For an IP address choose PTR (reverse lookup).')
        return ['-x', str(address)], str(address)
    if record == 'PTR':
        raise DnsLookupError('PTR lookups need an IP address.')
    ascii_name = _ascii_name(text)
    return [ascii_name], ascii_name


def validate_server(server):
    server = (server or '').strip()
    if not server:
        return ''
    try:
        return str(ipaddress.ip_address(server))
    except ValueError:
        return _ascii_name(server)


def dig_available():
    return shutil.which('dig') is not None


def query(name, record, server='', timeout=3, runner=subprocess.run):
    """Look up one record type; returns a dict with status, answers and the command used."""
    name_args, display = validate_query(name, record)
    server = validate_server(server)
    if not dig_available():
        raise DnsLookupError('The dig command is missing. Reinstall Nettalabbo with APT '
                             '(it installs bind9-dnsutils or dnsutils).')
    command = ['dig', f'+time={int(timeout)}', '+tries=1', '+noall', '+answer', '+comments']
    if server:
        command.append('@' + server)
    if name_args[0] == '-x':
        command += name_args
    else:
        command += [record] + name_args
    try:
        proc = runner(command, capture_output=True, text=True, timeout=timeout * 3 + 3, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DnsLookupError(f'DNS query failed: {exc}') from exc
    if proc.returncode != 0:
        detail = (proc.stderr.strip() or proc.stdout.strip() or f'dig exit code {proc.returncode}')
        raise DnsLookupError('DNS query failed: ' + detail.splitlines()[-1][:200])
    status_match = _STATUS.search(proc.stdout)
    answers = []
    for line in proc.stdout.splitlines():
        if not line.strip() or line.startswith(';'):
            continue
        parts = line.split(None, 4)
        if len(parts) == 5:
            owner, ttl, _klass, rtype, data = parts
            answers.append({'name': owner, 'ttl': ttl, 'type': rtype, 'data': data})
    return {'name': display, 'record': 'PTR' if name_args[0] == '-x' else record,
            'server': server or 'system resolver',
            'status': status_match.group(1) if status_match else 'UNKNOWN', 'answers': answers}


STATUS_TEXT = {
    'NOERROR': 'OK',
    'NXDOMAIN': 'the name does not exist',
    'SERVFAIL': 'the server could not answer (often a DNSSEC or delegation problem)',
    'REFUSED': 'the server refused the query',
}


def format_result(result):
    header = f"{result['record']} records for {result['name']} (server: {result['server']})"
    status = result['status']
    if status != 'NOERROR':
        return f"{header}\n    {status}: {STATUS_TEXT.get(status, 'unexpected reply')}\n"
    if not result['answers']:
        return f"{header}\n    no {result['record']} records\n"
    width = max(len(a['name']) for a in result['answers'])
    lines = [header]
    for a in result['answers']:
        lines.append(f"    {a['name']:<{width}}  {a['type']:<5}  TTL {a['ttl']:>6}  {a['data']}")
    return '\n'.join(lines) + '\n'
