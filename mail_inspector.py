"""Manual, single-address mail routing and protocol diagnostics.

No emails are delivered. A user must explicitly authorise a one-address
SMTP RCPT probe; no bulk lookups, address guessing or catch-all probing.
Compatible with Python 3.8 and uses only Python stdlib plus the Ubuntu dig
utility installed via the mandatory dnsutils Debian dependency.
"""
import re
import shutil
import smtplib
import socket
import ssl
import subprocess
from dataclasses import dataclass, field

TIMEOUT = 7


class MailInspectionError(ValueError):
    pass


@dataclass
class MailReport:
    address: str
    domain: str
    mx: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    smtp_code: int = 0
    smtp_reply: str = ''
    verdict: str = 'Indeterminate'

    def text(self):
        lines = [
            'Email address: ' + self.address,
            'Mail domain: ' + self.domain,
            'Result: ' + self.verdict,
            '',
            'MX routing records:',
        ]
        lines.extend('  Priority {:>3}   {}'.format(p, h) for p, h in self.mx)
        if not self.mx:
            lines.append('  No published MX host identified.')
        if self.smtp_code:
            lines.extend(['', 'SMTP recipient response: {} {}'.format(
                self.smtp_code, self.smtp_reply[:300])])
        lines.extend(['', 'Observations:'] + ['  • ' + x for x in self.notes])
        lines.extend([
            '',
            'IMPORTANT: SMTP acceptance does not establish mailbox existence.',
            'Servers may accept all recipients, forward messages, defer checks',
            'until later, reject probes for policy reasons, or conceal users.',
            'No message was sent. No DATA command was issued.',
        ])
        return '\n'.join(lines) + '\n'


def normalise_email(value):
    value = value.strip()
    if len(value) > 254 or value.count('@') != 1 or any(c.isspace() for c in value):
        raise MailInspectionError('Enter one valid email address, not a list.')
    local, domain = value.rsplit('@', 1)
    if not (1 <= len(local.encode('utf-8')) <= 64):
        raise MailInspectionError('Invalid email local part.')
    # Conservative syntax; no SMTPUTF8 transport or quoted addresses yet.
    if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+", local):
        raise MailInspectionError('This version accepts conventional ASCII mailboxes only.')
    if local.startswith('.') or local.endswith('.') or '..' in local:
        raise MailInspectionError('Invalid mailbox dot placement.')
    try:
        ascii_domain = domain.rstrip('.').encode('idna').decode('ascii').lower()
    except UnicodeError as exc:
        raise MailInspectionError('Invalid domain name.') from exc
    if len(ascii_domain) > 253 or '.' not in ascii_domain or not all(
            re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
            for label in ascii_domain.split('.')):
        raise MailInspectionError('Invalid mail domain.')
    return local + '@' + ascii_domain, ascii_domain


def dig_records(domain, record):
    if shutil.which('dig') is None:
        raise MailInspectionError('DNS utility dig is missing. Reinstall Nettalabbo with APT to install dnsutils.')
    try:
        proc = subprocess.run(
            ['dig', '+time=3', '+tries=1', '+short', record, domain],
            capture_output=True, text=True, timeout=6, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MailInspectionError('DNS query timed out or failed: {}'.format(exc)) from exc
    if proc.returncode != 0:
        raise MailInspectionError('DNS query failed: ' + (proc.stderr.strip() or str(proc.returncode))[:180])
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()][:32]


def find_mx(domain):
    records = dig_records(domain, 'MX')
    answers = []
    for record in records:
        m = re.match(r'^(\d+)\s+(\S+)\s*$', record)
        if m:
            answers.append((int(m.group(1)), m.group(2).lower().rstrip('.') or '.'))
    answers.sort(key=lambda record: (record[0], record[1]))
    return answers[:16]


def _text_reply(reply):
    if isinstance(reply, bytes):
        return reply.decode('utf-8', 'replace').replace('\r', ' ').replace('\n', ' ')[:300]
    return str(reply).replace('\r', ' ').replace('\n', ' ')[:300]


def smtp_recipient_probe(host, address, port=25):
    """One explicitly requested envelope check: no VRFY, EXPN or DATA."""
    with smtplib.SMTP(timeout=TIMEOUT) as smtp:
        smtp.connect(host, port)
        smtp.ehlo('nettalabbo.local')
        if smtp.has_extn('starttls'):
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo('nettalabbo.local')
        code, response = smtp.mail('')  # RFC-compliant null reverse path
        if code < 200 or code >= 300:
            return code, _text_reply(response), 'MAIL FROM was rejected; recipient not tested.'
        code, response = smtp.rcpt(address)
        # SMTP.__exit__ issues QUIT; no message transmission / DATA.
        return code, _text_reply(response), 'Recipient stage completed; mailbox existence remains uncertain.'


def classify_smtp(code):
    if 200 <= code < 300:
        return 'SMTP accepted recipient (not verified)'
    if 400 <= code < 500:
        return 'Temporary SMTP refusal / indeterminate'
    if 500 <= code < 600:
        return 'SMTP rejected recipient (not conclusive)'
    return 'SMTP response inconclusive'


def inspect_address(value, recipient_probe=False):
    address, domain = normalise_email(value)
    report = MailReport(address, domain)
    report.mx = find_mx(domain)
    if report.mx == [(0, '.')]:
        report.verdict = 'Domain explicitly rejects mail (Null MX)'
        report.notes.append('Published Null MX (RFC 7505) announces no inbound mail service.')
        return report
    if not report.mx:
        try:
            # An SMTP domain without MX may still route by A/AAAA records.
            socket.getaddrinfo(domain, 25, type=socket.SOCK_STREAM)
            report.mx = [(0, domain)]
            report.notes.append('No MX record; implicit A/AAAA fallback under SMTP rules.')
        except socket.gaierror:
            report.verdict = 'No mail route established'
            report.notes.append('No MX and no resolvable host address. DNS could also be transiently unavailable.')
            return report
    report.verdict = 'Mail-routing host found; mailbox unknown'
    report.notes.append('MX records describe mail routing, not individual account existence.')
    if not recipient_probe:
        report.notes.append('Recipient probe not performed; enable it explicitly if authorised.')
        return report
    # One recipient, at most one SMTP server reached successfully. No enumeration.
    for _, host in report.mx[:3]:
        try:
            code, reply, observation = smtp_recipient_probe(host, address)
            report.smtp_code, report.smtp_reply = code, reply
            report.verdict = ('SMTP envelope refused before recipient check'
                              if observation.startswith('MAIL FROM was rejected')
                              else classify_smtp(code))
            report.notes.append('Queried SMTP server: {}:25'.format(host))
            report.notes.append(observation)
            break
        except (socket.timeout, OSError, smtplib.SMTPException) as exc:
            report.notes.append('Could not query {}:25: {}'.format(host, str(exc)[:150]))
    else:
        report.verdict = 'Mail routes found; SMTP probe unavailable'
    return report


def _read_greeting(sock):
    sock.settimeout(TIMEOUT)
    try:
        data = sock.recv(2048)
    except socket.timeout:
        return '(no unsolicited greeting)'
    return _text_reply(data) or '(connection closed without greeting)'


def test_mail_service(kind, host, port):
    """Single host connection test without credentials, authentication or mailbox listing."""
    kind = kind.upper().strip()
    if kind not in {'SMTP', 'IMAP', 'POP3'}:
        raise MailInspectionError('Choose SMTP, IMAP or POP3.')
    host = host.strip()
    if not host or len(host) > 253 or any(x in host for x in '/@\r\n\x00 '):
        raise MailInspectionError('Enter a single valid server hostname.')
    try:
        port = int(port)
    except (ValueError, TypeError):
        raise MailInspectionError('Invalid TCP port.')
    if not 1 <= port <= 65535:
        raise MailInspectionError('Invalid TCP port.')
    if kind == 'SMTP':
        cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        kwargs = {'timeout': TIMEOUT}
        if cls is smtplib.SMTP_SSL:
            kwargs['context'] = ssl.create_default_context()
        with cls(host, port, **kwargs) as smtp:
            code, response = smtp.ehlo('nettalabbo.local')
            starttls = smtp.has_extn('starttls')
            protected = (port == 465)
            if not protected and starttls:
                smtp.starttls(context=ssl.create_default_context())
                protected = True
                code, response = smtp.ehlo('nettalabbo.local')
            return ('SMTP connection: {}:{}\nEHLO: {} {}\nTLS negotiated: {}\n'
                    'No authentication attempted; no email was sent.\n').format(
                    host, port, code, _text_reply(response), 'yes' if protected else 'no')
    # IMAP greeting + CAPABILITY, POP3 greeting + CAPA; no login.
    with socket.create_connection((host, port), timeout=TIMEOUT) as raw:
        raw.settimeout(TIMEOUT)
        if (kind == 'IMAP' and port == 993) or (kind == 'POP3' and port == 995):
            with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as conn:
                greeting = _read_greeting(conn)
                return ('{} connection: {}:{}\nTLS verified: yes\nGreeting: {}\n'
                        'Authentication not attempted; individual mailbox existence cannot be checked.\n').format(
                        kind, host, port, greeting)
        greeting = _read_greeting(raw)
        return ('{} connection: {}:{}\nTLS verified: no\nGreeting: {}\n'
                'Unencrypted connection. No login credentials sent.\n'
                'Authentication not attempted; individual mailbox existence cannot be checked.\n').format(
                kind, host, port, greeting)
