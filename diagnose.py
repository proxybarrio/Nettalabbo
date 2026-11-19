"""Read-only domain and mail diagnostics for Nettalabbo.

DNSBL checks are strictly opt-in: they disclose queried domain/IP identifiers
to third-party DNSBL operators. No SMTP RCPT/DATA commands are sent.
Unknown or refused queries must never be reported as a clean reputation.
"""
from __future__ import annotations
import ipaddress
import re
import shutil
import socket
import ssl
import subprocess
from dataclasses import dataclass, field
from mail_policy import spf_review, dmarc_review, dkim_review, txt_value

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
        lines = []
        for x in self.checks:
            detail = x.detail.strip().replace('\n', '\n    ')
            lines.append(f'[{x.status.upper()}] {x.name}: {detail}')
        return 'Domain diagnostics: ' + self.domain + '\n\n' + '\n'.join(lines)


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


def _is_public_ipv4(address):
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return parsed.version == 4 and parsed.is_global


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
    # An empty response does not prove the DNSBL is accessible or clear.
    if not answers:
        report.add(label, 'unknown',
                   'No listing returned; resolver access and DNSBL eligibility not established')
        return
    try:
        parsed = [ipaddress.ip_address(x) for x in answers]
    except ValueError:
        report.add(label, 'unknown', 'Invalid provider response: ' + ', '.join(answers[:4]))
        return
    if not all(ip.version == 4 and ip.is_loopback for ip in parsed):
        report.add(label, 'unknown', 'Unexpected provider response: ' + ', '.join(answers[:4]))
        return
    # 127.255.255.x signals policy/errors from several DNSBL services.
    if any(x.startswith('127.255.255.') for x in answers):
        report.add(label, 'unknown',
                   'Provider policy or access error: ' + ', '.join(answers[:4]))
    elif zone == 'dbl.spamhaus.org' and '127.0.1.255' in answers:
        report.add(label, 'unknown', 'Provider rejected this query')
    else:
        report.add(label, 'warn', 'Provider returned listing code(s): ' + ', '.join(answers[:4]))


def diagnose(domain, resolver=None, *, check_blacklists=False, dkim_selector='',
             check_smtp=False, mail_probe=None):
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
        status, detail = spf_review(spf)
        report.add('SPF', status, detail)

    dmarc = _query(report, resolver, '_dmarc.' + domain, 'TXT', 'DMARC')
    if dmarc is not None:
        status, detail = dmarc_review(dmarc)
        report.add('DMARC', status, detail)

    if dkim_selector.strip():
        selector = dkim_selector.strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,62}', selector):
            report.add('DKIM', 'unknown', 'Invalid DKIM selector')
        else:
            txt = _query(report, resolver, selector + '._domainkey.' + domain, 'TXT', 'DKIM')
            if txt is not None:
                status, detail = dkim_review(txt)
                report.add('DKIM', status, detail)
    else:
        report.add('DKIM', 'skipped', 'Selector required; DKIM cannot be reliably discovered automatically')

    for name, record, version in (
        ('MTA STS', '_mta-sts.' + domain, 'v=STSv1'),
        ('TLS RPT', '_smtp._tls.' + domain, 'v=TLSRPTv1')
    ):
        txt = _query(report, resolver, record, 'TXT', name)
        if txt is None:
            continue
        policies = [txt_value(x) for x in txt]
        valid = [x for x in policies if x.replace(' ', '').lower().startswith(version.lower() + ';')
                 or x.strip().lower() == version.lower()]
        if not policies:
            report.add(name, 'warn', 'No policy record found')
        elif len(valid) == 1:
            report.add(name, 'pass', valid[0][:250])
        elif len(valid) > 1:
            report.add(name, 'fail', 'More than one ' + version + ' record')
        else:
            report.add(name, 'warn', 'Record does not start with ' + version + ': ' + policies[0][:120])

    if check_smtp:
        if mx_hosts:
            # Explicit single MX test. No mail delivery, auth or recipient check.
            if mail_probe is None:
                from mail_inspector import test_mail_service
                mail_probe = test_mail_service
            try:
                greeting = mail_probe('SMTP', mx_hosts[0], 25)
                secure = 'TLS negotiated: yes' in greeting
                report.add('SMTP connectivity', 'pass' if secure else 'warn',
                           greeting[:500])
            except ssl.SSLCertVerificationError as exc:
                report.add('SMTP connectivity', 'warn',
                           'STARTTLS is offered but the certificate could not be verified '
                           '(' + str(getattr(exc, 'verify_message', '') or exc)[:160] + '). '
                           'Many senders still deliver with unverified TLS.')
            except (ConnectionRefusedError, socket.timeout, TimeoutError) as exc:
                report.add('SMTP connectivity', 'unknown',
                           'No connection to ' + mx_hosts[0] + ':25 (' + str(exc)[:80] + '). '
                           'Many home and mobile providers block outgoing port 25, so this '
                           'does not prove that the server is down.')
            except Exception as exc:
                report.add('SMTP connectivity', 'unknown', str(exc)[:300])
        else:
            report.add('SMTP connectivity', 'skipped', 'No usable MX hostname found')
    else:
        report.add('SMTP connectivity', 'skipped',
                   'Direct mail-server connection disabled by default')

    if not check_blacklists:
        report.add('DNSBL', 'skipped', 'Third-party reputation queries disabled by default')
        return report

    # Explicit opt-in; DNSBL queries disclose target names/IP addresses.
    for zone in DOMAIN_DNSBL:
        _dnsbl_lookup(report, resolver, domain, zone, 'Domain DNSBL: ' + zone)
    found = set()
    if not any(_is_public_ipv4(a) for a in mail_addresses):
        report.add('IP DNSBL', 'skipped',
                   'No public IPv4 address found for the MX servers' if mail_addresses
                   else 'No MX server address to check')
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