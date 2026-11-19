"""Read-only domain and mail diagnostics for Nettalabbo.

DNSBL checks are strictly opt-in: they disclose queried domain/IP identifiers
to third-party DNSBL operators. No SMTP RCPT/DATA commands are sent.
Unknown or refused queries must never be reported as a clean reputation.
"""
from __future__ import annotations
import ipaddress
import re
import shutil
import subprocess
from dataclasses import dataclass, field

DOMAIN_DNSBL = ('dbl.spamhaus.org',)
IP_DNSBL = ('zen.spamhaus.org', 'bl.spamcop.net')
MAX_MX_HOSTS = 8


@dataclass
class Check:
    name: str
    status: str  # pass, warn, fail, unknown, skipped
    detail: str


@dataclass
class Report:
    domain: str
    checks: list[Check] = field(default_factory=list)

    def add(self, name, status, detail):
        self.checks.append(Check(name, status, str(detail)))

    def as_text(self):
        return ('Domain diagnostics: ' + self.domain + '\n\n' +
                '\n'.join(f'[{x.status.upper()}] {x.name}: {x.detail}'
                          for x in self.checks))


def domain_name(raw):
    raw = raw.strip().rstrip('.')
    if not raw or len(raw) > 253:
        raise ValueError('Enter a valid domain name.')
    try:
        name = raw.encode('idna').decode('ascii').lower()
    except UnicodeError as exc:
        raise ValueError('Invalid internationalised domain name.') from exc
    if len(name) > 253 or '.' not in name:
        raise ValueError('Enter a fully qualified domain name.')
    labels = name.split('.')
    if any(not 1 <= len(part) <= 63 or
           not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', part)
           for part in labels):
        raise ValueError('Invalid domain label.')
    if labels[-1].isdigit():
        raise ValueError('A domain must end in a non-numeric label.')
    return name


class Dig:
    """Queries one name and type using a bounded process, never a shell."""

    def __init__(self, runner=None):
        self.runner = runner or subprocess.run

    def query(self, name, rtype):
        if not shutil.which('dig'):
            raise RuntimeError('dig is unavailable; install bind9-dnsutils.')
        if rtype not in ('A', 'AAAA', 'MX', 'TXT', 'CNAME', 'NS', 'SOA', 'CAA'):
            raise ValueError('Unsupported query type.')
        # Domain input is validated at the public entry point; DNSBL names
        # are constructed only from validated domains and IP addresses.
        command = ['dig', '+time=3', '+tries=1', '+noall', '+answer',
                   '+comments', name, rtype]
        result = self.runner(command, capture_output=True, text=True,
                             timeout=6, check=False)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or
                                'DNS server did not answer').strip()[:300])
        raw = result.stdout
        status = re.search(r'\bstatus:\s*(\w+)', raw)
        code = status.group(1) if status else None
        if code and code not in ('NOERROR', 'NXDOMAIN'):
            raise RuntimeError('DNS resolver returned ' + code)
        if code is None:
            raise RuntimeError('DNS response did not include a status.')
        answers = []
        for line in raw.splitlines():
            if not line or line.startswith(';'):
                continue
            parts = line.split(None, 4)
            if len(parts) >= 5 and parts[3] == rtype and parts[2] == 'IN':
                answers.append(parts[4].strip())
        return answers


def _query(report, resolver, name, rtype, label):
    try:
        return resolver.query(name, rtype)
    except Exception as exc:
        report.add(label, 'unknown', str(exc))
        return None


def _dnsbl_lookup(report, resolver, entry, zone, label):
    try:
        answers = resolver.query(entry + '.' + zone, 'A')
    except Exception as exc:
        report.add(label, 'unknown', 'Cannot determine listing: ' + str(exc))
        return
    if not answers:
        report.add(label, 'pass', 'No listing returned by ' + zone)
    elif all(ipaddress.ip_address(x).is_loopback for x in answers):
        # DNSBL providers commonly use 127/8 for positive listings, but
        # may also signal policy/rate-limit errors in that same space.
        if any(x.startswith('127.255.') for x in answers):
            report.add(label, 'unknown',
                       'Provider returned a policy/error code: ' + ', '.join(answers))
        else:
            report.add(label, 'warn', 'Listing code(s): ' + ', '.join(answers))
    else:
        report.add(label, 'unknown', 'Unexpected DNSBL response: ' + ', '.join(answers))


def diagnose(domain, resolver=None, *, check_blacklists=False, dkim_selector=''):
    """Perform bounded, read-only public DNS checks.

    Returns a structured report. Every skipped or indeterminate check is
    clearly labelled. Network access occurs only when diagnose is called.
    """
    domain = domain_name(domain)
    resolver = resolver or Dig()
    report = Report(domain)

    mail_addresses = []
    for kind in ('A', 'AAAA'):
        result = _query(report, resolver, domain, kind, kind + ' records')
        if result is not None:
            report.add(kind + ' records', 'pass' if result else 'warn',
                       ', '.join(result[:8]) if result else 'No records found')

    mx = _query(report, resolver, domain, 'MX', 'MX records')
    mx_hosts = []
    if mx is not None:
        if mx == ['0 .']:
            report.add('MX records', 'warn', 'Null MX: domain does not accept mail')
        elif not mx:
            report.add('MX records', 'warn',
                       'No MX: some senders may attempt address fallback')
        else:
            for item in mx[:MAX_MX_HOSTS]:
                parts = item.split()
                if len(parts) != 2:
                    continue
                host = parts[1].rstrip('.')
                try:
                    domain_name(host)
                except ValueError:
                    continue
                mx_hosts.append(host)
            report.add('MX records', 'pass' if mx_hosts else 'warn',
                       '; '.join(mx[:MAX_MX_HOSTS]))
            for host in mx_hosts:
                for kind in ('A', 'AAAA'):
                    target = _query(report, resolver, host, kind, host + ' ' + kind)
                    if target is not None:
                        if not target:
                            report.add(host + ' ' + kind, 'warn', 'No address returned')
                        else:
                            report.add(host + ' ' + kind, 'pass', ', '.join(target[:4]))
                            mail_addresses.extend(target[:4])

    spf = _query(report, resolver, domain, 'TXT', 'SPF')
    if spf is not None:
        entries = [x for x in spf if x.strip('"').lower().startswith('v=spf1')]
        if len(entries) > 1:
            report.add('SPF', 'fail', 'Multiple SPF records detected')
        elif entries:
            report.add('SPF', 'pass', entries[0][:250] +
                       ' (syntax and DNS lookup limits not fully validated)')
        else:
            report.add('SPF', 'warn', 'No SPF record detected')

    dmarc = _query(report, resolver, '_dmarc.' + domain, 'TXT', 'DMARC')
    if dmarc is not None:
        entries = [x for x in dmarc if x.strip('"').lower().startswith('v=dmarc1')]
        if len(entries) > 1:
            report.add('DMARC', 'fail', 'Multiple DMARC records detected')
        elif entries:
            policy = re.search(r'\bp=(none|quarantine|reject)\b', entries[0], re.I)
            report.add('DMARC', 'pass' if policy else 'warn',
                       entries[0][:250] if policy else 'Policy p= not detected')
        else:
            report.add('DMARC', 'warn', 'No DMARC record detected')

    if dkim_selector.strip():
        selector = dkim_selector.strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,62}', selector):
            report.add('DKIM', 'unknown', 'Invalid DKIM selector')
        else:
            txt = _query(report, resolver, selector + '._domainkey.' + domain, 'TXT', 'DKIM')
            if txt is not None:
                report.add('DKIM', 'pass' if any('V=DKIM1' in x.upper() for x in txt) else 'warn',
                           '; '.join(txt[:2])[:250] if txt else 'No DKIM key for this selector')
    else:
        report.add('DKIM', 'skipped', 'Selector required; DKIM cannot be reliably discovered automatically')

    for name, record, kind in (
        ('MTA STS', '_mta-sts.' + domain, 'TXT'),
        ('TLS RPT', '_smtp._tls.' + domain, 'TXT')
    ):
        txt = _query(report, resolver, record, kind, name)
        if txt is not None:
            report.add(name, 'pass' if txt else 'warn',
                       '; '.join(txt[:2])[:250] if txt else 'No policy record found')

    if not check_blacklists:
        report.add('DNSBL', 'skipped', 'Third-party reputation queries disabled by default')
        return report

    # Explicit opt-in; DNSBL queries disclose target names/IP addresses.
    for zone in DOMAIN_DNSBL:
        _dnsbl_lookup(report, resolver, domain, zone, 'Domain DNSBL: ' + zone)
    found = set()
    for address in mail_addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not parsed.is_global or parsed.version != 4 or address in found:
            continue
        found.add(address)
        if len(found) > 12:
            report.add('IP DNSBL', 'skipped', 'Additional IPs excluded by query limit')
            break
        reverse = '.'.join(reversed(address.split('.')))
        for zone in IP_DNSBL:
            _dnsbl_lookup(report, resolver, reverse, zone, address + ' DNSBL: ' + zone)
    return report