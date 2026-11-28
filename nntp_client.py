"""Small NNTP (Usenet newsgroups) client for the Newsgroups page.

Implements the reader commands of RFC 3977 and AUTHINFO USER/PASS of
RFC 4643: list groups, read overviews and articles, and post. Every
operation opens its own short connection, so a slow or vanished server
never leaves a socket open in the background. Standard library only,
Python 3.8 compatible.
"""

import email
import email.errors
import email.policy
import email.utils
import re
import socket
import ssl
from email.header import Header, decode_header, make_header

PLAIN_PORT = 119
TLS_PORT = 563
TIMEOUT = 25
MAX_LINE = 16384
MAX_LIST_BYTES = 64_000_000      # full LIST ACTIVE of a large Usenet server
MAX_ARTICLE_BYTES = 2_000_000
MAX_OVERVIEW = 2000
DEFAULT_BATCH = 200
MAX_THREAD_DEPTH = 40           # deeper replies are shown at this indentation

# name, host, port, tls, account, description
PUBLIC_SERVERS = (
    ('Paganini', 'paganini.bofh.team', 119, False, 'none',
     'Real Usenet groups. Anonymous reading; posting where the server allows it.'),
    ('Gmane', 'news.gmane.io', 119, False, 'none',
     'Thousands of open source mailing lists as newsgroups. Anonymous reading; '
     'a post goes to the list and may ask you to confirm by e-mail.'),
    ('Linux kernel lists (lore.kernel.org)', 'nntp.lore.kernel.org', 119, False, 'none',
     'Official archive of the Linux development mailing lists. Read only.'),
    ('Rocksolid (novabbs)', 'news.novabbs.org', 119, False, 'optional',
     'Usenet text groups. Anonymous reading; posting with a free account.'),
    ('Eternal September', 'news.eternal-september.org', 563, True, 'required',
     'Large free text-only Usenet server. Free registration required.'),
    ('NNTP4', 'news.nntp4.net', 119, False, 'required',
     'Private non-commercial server. Free registration required.'),
)

ACCOUNT_NOTES = {
    'none': 'no account needed',
    'optional': 'account optional',
    'required': 'free account required',
}


class NNTPError(Exception):
    """A readable NNTP failure: connection, protocol or server refusal."""

    def __init__(self, message, code=None):
        Exception.__init__(self, message)
        self.code = code


class Cancelled(NNTPError):
    pass


def _check_token(value, what):
    if not value or any(c in value for c in '\r\n\0') or any(c.isspace() for c in value):
        raise NNTPError('Invalid {}.'.format(what))
    return value


class Connection:
    """One NNTP session. Use as a context manager."""

    def __init__(self, host, port=None, tls=False, username='', password='',
                 timeout=TIMEOUT, stop=None, context=None):
        self.host = _check_token((host or '').strip(), 'server name')
        self.port = int(port or (TLS_PORT if tls else PLAIN_PORT))
        if not 0 < self.port < 65536:
            raise NNTPError('Invalid port.')
        self.tls = bool(tls)
        self.username = username or ''
        self.password = password or ''
        self.timeout = timeout
        self.stop = stop
        self.context = context
        self.sock = None
        self.file = None
        self.greeting = ''
        self.posting_allowed = False
        self.authenticated = False

    # -- connection -------------------------------------------------------
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def open(self):
        self._check_stop()
        try:
            raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except socket.gaierror:
            raise NNTPError('Server name {} not found.'.format(self.host))
        except socket.timeout:
            raise NNTPError('No answer from {} port {}.'.format(self.host, self.port))
        except OSError as error:
            raise NNTPError('Cannot connect to {} port {}: {}.'.format(
                self.host, self.port, error.strerror or error))
        try:
            if self.tls:
                context = self.context or ssl.create_default_context()
                try:
                    raw = context.wrap_socket(raw, server_hostname=self.host)
                except ssl.SSLCertVerificationError as error:
                    raise NNTPError('The server certificate is not trusted ({}).'.format(
                        getattr(error, 'verify_message', '') or error))
                except (ssl.SSLError, OSError) as error:
                    raise NNTPError('Encrypted connection failed: {}. '
                                    'Check the port: 563 is the usual one for TLS.'.format(error))
            raw.settimeout(self.timeout)
            self.sock = raw
            self.file = raw.makefile('rb')
            code, text = self._response()
            self.greeting = text
            if code not in (200, 201):
                raise NNTPError('Server refused the connection: {} {}'.format(code, text), code)
            self.posting_allowed = code == 200
            # Some servers only offer reader commands after MODE READER.
            code, text = self.command('MODE READER', expect=None)
            if code in (200, 201):
                self.posting_allowed = code == 200
            if self.username:
                self.login()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.sock is not None:
            try:
                self.sock.sendall(b'QUIT\r\n')
            except OSError:
                pass
        for item in (self.file, self.sock):
            try:
                if item is not None:
                    item.close()
            except OSError:
                pass
        self.file = self.sock = None

    def login(self):
        _check_token(self.username, 'user name')
        if any(c in self.password for c in '\r\n\0'):
            raise NNTPError('Invalid password.')
        code, text = self.command('AUTHINFO USER ' + self.username, expect=None)
        if code == 381:
            code, text = self.command('AUTHINFO PASS ' + self.password, expect=None, secret=True)
        if code == 281:
            self.authenticated = True
            # Accounts usually unlock posting even when the greeting said 201.
            self.posting_allowed = True
            return
        if code == 481:
            raise NNTPError('User name or password not accepted.', code)
        if code == 483:
            raise NNTPError('The server accepts passwords only over an encrypted connection: '
                            'turn on TLS (port 563).', code)
        raise NNTPError('Login failed: {} {}'.format(code, text), code)

    # -- protocol helpers -------------------------------------------------
    def _check_stop(self):
        if self.stop is not None and self.stop.is_set():
            raise Cancelled('Cancelled.')

    def _readline(self):
        self._check_stop()
        try:
            line = self.file.readline(MAX_LINE + 2)
        except socket.timeout:
            raise NNTPError('The server stopped answering.')
        except OSError as error:
            raise NNTPError('Connection lost: {}.'.format(error))
        if not line:
            raise NNTPError('The server closed the connection.')
        return line

    def _response(self):
        line = self._readline().decode('utf-8', 'replace').rstrip('\r\n')
        match = re.match(r'^(\d{3})\s?(.*)$', line)
        if not match:
            raise NNTPError('Unexpected answer from the server: {}'.format(line[:120]))
        return int(match.group(1)), match.group(2)

    def command(self, line, expect=(), secret=False):
        """Send one command; expect is a tuple of accepted codes, or None for any."""
        if any(c in line for c in '\r\n\0'):
            raise NNTPError('Invalid command.')
        self._check_stop()
        try:
            self.sock.sendall(line.encode('utf-8') + b'\r\n')
        except OSError as error:
            raise NNTPError('Connection lost: {}.'.format(error))
        code, text = self._response()
        if expect is not None and code not in expect:
            shown = line.split()[0] if secret else line
            if code == 480:
                raise NNTPError('This server needs an account: add your user name and password.', code)
            if code == 502:
                raise NNTPError('Permission denied by the server for {}.'.format(shown.split()[0]), code)
            raise NNTPError('{} failed: {} {}'.format(shown.split()[0], code, text), code)
        return code, text

    def read_block(self, limit):
        """Read a dot-terminated multi-line block; returns (lines, truncated)."""
        lines, size, truncated = [], 0, False
        while True:
            line = self._readline()
            if line in (b'.\r\n', b'.\n'):
                return lines, truncated
            if line.startswith(b'..'):
                line = line[1:]
            if not truncated:
                size += len(line)
                if size > limit:
                    truncated = True
                else:
                    lines.append(line.rstrip(b'\r\n'))

    # -- reader commands --------------------------------------------------
    def list_groups(self):
        """[(name, first, last, status)] from LIST ACTIVE."""
        self.command('LIST ACTIVE', expect=(215,))
        lines, truncated = self.read_block(MAX_LIST_BYTES)
        groups = []
        for raw in lines:
            parts = raw.decode('utf-8', 'replace').split()
            if len(parts) < 3:
                continue
            try:
                last, first = int(parts[1]), int(parts[2])
            except ValueError:
                continue
            groups.append((parts[0], first, last, parts[3] if len(parts) > 3 else 'y'))
        groups.sort(key=lambda item: item[0].lower())
        return groups, truncated

    def group(self, name):
        """(estimated count, first, last) and selects the group."""
        code, text = self.command('GROUP ' + _check_token(name, 'group name'), expect=(211, 411))
        if code == 411:
            raise NNTPError('The group {} does not exist on this server.'.format(name), code)
        parts = text.split()
        try:
            return int(parts[0]), int(parts[1]), int(parts[2])
        except (IndexError, ValueError):
            raise NNTPError('Unexpected GROUP answer: {}'.format(text))

    def overview(self, first, last):
        """Overview records for article numbers first..last."""
        if last < first:
            return []
        span = '{}-{}'.format(first, last)
        code, text = self.command('OVER ' + span, expect=None)
        if code in (500, 501):
            code, text = self.command('XOVER ' + span, expect=None)
        if code == 423:
            return []
        if code != 224:
            raise NNTPError('Cannot read the message list: {} {}'.format(code, text), code)
        lines, _truncated = self.read_block(MAX_LIST_BYTES)
        return [record for record in (parse_overview(line) for line in lines) if record]

    def article(self, number):
        code, text = self.command('ARTICLE {}'.format(int(number)), expect=(220, 423, 430))
        if code != 220:
            raise NNTPError('The message is no longer on the server.', code)
        lines, truncated = self.read_block(MAX_ARTICLE_BYTES)
        return b'\r\n'.join(lines) + b'\r\n', truncated

    def post(self, article_bytes):
        """Send a prepared article; returns the server confirmation."""
        code, text = self.command('POST', expect=None)
        if code == 440:
            raise NNTPError('This server does not allow posting'
                            + ('' if self.authenticated else ' without an account') + '.', code)
        if code == 480:
            raise NNTPError('This server needs an account to post: add your user name and password.', code)
        if code != 340:
            raise NNTPError('POST refused: {} {}'.format(code, text), code)
        payload = []
        for line in article_bytes.replace(b'\r\n', b'\n').split(b'\n'):
            payload.append(b'.' + line if line.startswith(b'.') else line)
        if payload and payload[-1] == b'':
            payload.pop()
        try:
            self.sock.sendall(b'\r\n'.join(payload) + b'\r\n.\r\n')
        except OSError as error:
            raise NNTPError('Connection lost while sending: {}.'.format(error))
        code, text = self._response()
        if code != 240:
            raise NNTPError('The server rejected the message: {} {}'.format(code, text), code)
        return text


# -- data helpers ---------------------------------------------------------
def header_text(value):
    """Decode RFC 2047 encoded words into readable text."""
    if not value:
        return ''
    try:
        return str(make_header(decode_header(value)))
    except (ValueError, LookupError, UnicodeError, email.errors.HeaderParseError):
        return value


def display_name(address):
    name, mail = email.utils.parseaddr(header_text(address))
    return name or mail or header_text(address)


def parse_overview(raw):
    fields = raw.decode('utf-8', 'replace').split('\t')
    if len(fields) < 8:
        return None
    try:
        number = int(fields[0])
    except ValueError:
        return None

    def number_or_zero(value):
        try:
            return int(value)
        except ValueError:
            return 0

    return {
        'number': number,
        'subject': header_text(fields[1]).replace('\n', ' ').strip() or '(no subject)',
        'from': display_name(fields[2]),
        'date': fields[3],
        'timestamp': timestamp(fields[3]),
        'message_id': fields[4].strip(),
        'references': fields[5].split(),
        'bytes': number_or_zero(fields[6]),
        'lines': number_or_zero(fields[7]),
    }


def timestamp(value):
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed.timestamp() if parsed else 0.0
    except (TypeError, ValueError, OverflowError, IndexError):
        return 0.0


def short_date(value):
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed is None:
            return value
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime('%Y-%m-%d %H:%M')
    except (TypeError, ValueError, OverflowError, IndexError):
        return value[:16]


def build_threads(records):
    """Arrange overview records as threads.

    Returns [(parent message-id or '', record)] ordered so a parent always
    comes before its replies (beyond MAX_THREAD_DEPTH levels a reply is
    attached to the deepest shown ancestor); threads are ordered by their newest message,
    newest first, replies inside a thread by date.
    """
    by_id = {r['message_id']: r for r in records if r['message_id']}
    parent = {}
    for record in records:
        found = ''
        for reference in reversed(record['references']):
            if reference in by_id and reference != record['message_id']:
                found = reference
                break
        parent[record['number']] = found
    children = {}
    roots = []
    for record in records:
        key = parent[record['number']]
        if key:
            children.setdefault(key, []).append(record)
        else:
            roots.append(record)

    # Iterative on purpose: a long chain of replies must not hit Python's
    # recursion limit, and very deep threads stay readable.
    def newest(root):
        best, stack, seen = root['timestamp'], [root], {root['number']}
        while stack:
            record = stack.pop()
            best = max(best, record['timestamp'])
            for child in children.get(record['message_id'], ()):
                if child['number'] not in seen:
                    seen.add(child['number'])
                    stack.append(child)
        return best

    roots.sort(key=newest, reverse=True)
    ordered, placed = [], set()

    def walk(root):
        stack = [(root, '', 0)]
        anchors = {}            # depth -> message-id used as parent at that depth
        while stack:
            record, parent_id, depth = stack.pop()
            if record['number'] in placed:
                continue
            placed.add(record['number'])
            ordered.append((parent_id, record))
            if depth < MAX_THREAD_DEPTH:
                anchors[depth] = record['message_id']
                child_parent, child_depth = record['message_id'], depth + 1
            else:
                child_parent, child_depth = parent_id, depth
            replies = sorted(children.get(record['message_id'], ()), key=lambda r: r['timestamp'])
            for child in reversed(replies):
                stack.append((child, child_parent, child_depth))

    for root in roots:
        walk(root)
    for record in records:          # reference loops: never lose a message
        if record['number'] not in placed:
            walk(record)
    return ordered


UUENCODE = re.compile(r'^begin [0-7]{3,4} (.+)$', re.MULTILINE)


def parse_article(raw, truncated=False):
    """Readable form of an article: headers, text body, attachment notes."""
    message = email.message_from_bytes(raw, policy=email.policy.compat32)
    headers = {}
    for key in ('From', 'Newsgroups', 'Subject', 'Date', 'Message-ID', 'References',
                'Organization', 'Followup-To', 'Reply-To', 'User-Agent', 'X-Newsreader'):
        value = message.get(key)
        if value:
            headers[key] = header_text(str(value)).replace('\n', ' ').strip()
    attachments = []
    text_parts = []
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        ctype = part.get_content_type()
        if filename or (part is not message and not ctype.startswith('text/')):
            attachments.append('{} ({})'.format(header_text(filename) if filename else 'unnamed', ctype))
            continue
        if ctype not in ('text/plain', 'text/x-markdown') and text_parts:
            continue
        try:
            payload = part.get_payload(decode=True) or b''
        except (ValueError, AssertionError):
            payload = b''
        charset = part.get_content_charset() or 'utf-8'
        try:
            text_parts.append(payload.decode(charset, 'replace'))
        except LookupError:
            text_parts.append(payload.decode('latin-1', 'replace'))
    body = '\n'.join(text_parts).replace('\r\n', '\n')
    # Binary posts encoded in the text: show a note, not pages of symbols.
    if '=ybegin ' in body:
        names = re.findall(r'^=ybegin .*name=(.+)$', body, re.MULTILINE)
        attachments.extend('{} (yEnc)'.format(n.strip()) for n in names or ['unnamed'])
        body = re.sub(r'^=ybegin .*?(^=yend.*?$|\Z)', '[binary file not shown]',
                      body, flags=re.MULTILINE | re.DOTALL)
    for name in UUENCODE.findall(body):
        attachments.append('{} (uuencoded)'.format(name.strip()))
    body = re.sub(r'^begin [0-7]{3,4} .+?^end$', '[binary file not shown]',
                  body, flags=re.MULTILINE | re.DOTALL)
    return {'headers': headers, 'body': body, 'attachments': attachments,
            'truncated': truncated, 'raw': raw}


def reply_subject(subject):
    subject = (subject or '').strip()
    return subject if re.match(r'^re:', subject, re.IGNORECASE) else 'Re: ' + subject


def quote_body(article):
    headers = article['headers']
    who = display_name(headers.get('From', '')) or 'someone'
    lines = ['{} wrote:'.format(who)]
    body = article['body'].rstrip('\n')
    # Drop the quoted author's signature, as newsreaders traditionally do.
    signature = body.find('\n-- \n')
    if signature >= 0:
        body = body[:signature]
    for line in body.split('\n'):
        lines.append('>' + line if line.startswith('>') else '> ' + line if line else '>')
    return '\n'.join(lines) + '\n\n'


def build_article(sender, newsgroups, subject, body, references=(), user_agent='Nettalabbo'):
    """Prepare a plain-text UTF-8 article ready for POST."""
    sender = (sender or '').strip()
    name, address = email.utils.parseaddr(sender)
    if not address or '@' not in address or any(c in sender for c in '\r\n'):
        raise NNTPError('Enter a sender like  Name <name@example.org>.')
    groups = [g.strip() for g in re.split(r'[,\s]+', newsgroups or '') if g.strip()]
    if not groups:
        raise NNTPError('Enter at least one newsgroup.')
    for group in groups:
        if not re.match(r'^[A-Za-z0-9][A-Za-z0-9.+_-]*$', group):
            raise NNTPError('Invalid newsgroup name: {}'.format(group))
    subject = ' '.join((subject or '').split())
    if not subject:
        raise NNTPError('Enter a subject.')
    if not (body or '').strip():
        raise NNTPError('The message is empty.')

    def header(value):
        try:
            value.encode('ascii')
            return value
        except UnicodeEncodeError:
            return Header(value, 'utf-8').encode()

    from_value = email.utils.formataddr((name, address), charset='utf-8') if name else address
    lines = [
        'From: ' + from_value,
        'Newsgroups: ' + ','.join(groups),
        'Subject: ' + header(subject),
        'Date: ' + email.utils.formatdate(localtime=False, usegmt=True),
        'User-Agent: ' + user_agent,
        'MIME-Version: 1.0',
        'Content-Type: text/plain; charset=UTF-8',
        'Content-Transfer-Encoding: 8bit',
    ]
    references = [r for r in references if r and not any(c in r for c in '\r\n')]
    if references:
        lines.append('References: ' + ' '.join(references[-20:]))
    text = (body or '').replace('\r\n', '\n').rstrip('\n')
    return ('\r\n'.join(lines) + '\r\n\r\n' + text.replace('\n', '\r\n') + '\r\n').encode('utf-8')
