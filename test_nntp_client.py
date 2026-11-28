import socketserver
import threading
import unittest

import nntp_client
from nntp_client import (NNTPError, build_article, build_threads, parse_article,
                         parse_overview, quote_body, reply_subject)


def make_article(number, msgid, subject, sender, date, refs='', body='Hello\n'):
    head = ('From: {}\r\nNewsgroups: test.one\r\nSubject: {}\r\nDate: {}\r\n'
            'Message-ID: {}\r\n'.format(sender, subject, date, msgid))
    if refs:
        head += 'References: {}\r\n'.format(refs)
    return {'number': number, 'id': msgid, 'subject': subject, 'from': sender, 'date': date,
            'refs': refs, 'raw': (head + '\r\n' + body.replace('\n', '\r\n')).encode('utf-8')}


class FakeNewsServer(socketserver.ThreadingTCPServer):
    """Minimal RFC 3977 server: groups, overview, articles, AUTHINFO, POST."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address=('127.0.0.1', 0), require_auth=False, allow_post=True,
                 users=None, ssl_context=None, greeting=200):
        socketserver.ThreadingTCPServer.__init__(self, address, NewsHandler)
        self.require_auth = require_auth
        self.allow_post = allow_post
        self.users = users or {'reader': 'secret'}
        self.ssl_context = ssl_context
        self.greeting = greeting
        self.posted = []
        self.groups = {
            'test.one': [
                make_article(1, '<a1@x>', 'First topic', 'Ann <ann@example.org>',
                             'Mon, 02 Nov 2026 10:00:00 +0000'),
                make_article(2, '<a2@x>', 'Re: First topic', 'Bob <bob@example.org>',
                             'Mon, 02 Nov 2026 11:00:00 +0000', '<a1@x>',
                             'Ann wrote:\n> Hello\n\nHi Ann\n.dot line\n-- \nBob\n'),
                make_article(3, '<a3@x>', '=?UTF-8?Q?Caff=C3=A8?=', '=?UTF-8?Q?Lucr=C3=A8zia?= <l@example.org>',
                             'Tue, 03 Nov 2026 09:00:00 +0000'),
                make_article(4, '<a4@x>', 'Re: First topic', 'Cy <cy@example.org>',
                             'Wed, 04 Nov 2026 09:00:00 +0000', '<a1@x> <a2@x>'),
            ],
            'alt.empty': [],
        }

    def serve_in_thread(self):
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        return self.server_address[1]

    def get_request(self):
        sock, address = socketserver.ThreadingTCPServer.get_request(self)
        if self.ssl_context is not None:
            sock = self.ssl_context.wrap_socket(sock, server_side=True)
        return sock, address


class NewsHandler(socketserver.StreamRequestHandler):
    def send(self, text):
        self.wfile.write(text.encode('utf-8') + b'\r\n')

    def send_block(self, lines):
        for line in lines:
            if line.startswith(b'.'):
                line = b'.' + line
            self.wfile.write(line + b'\r\n')
        self.wfile.write(b'.\r\n')

    def handle(self):
        server = self.server
        user, authed, group = None, False, None
        posting = 'posting allowed' if server.greeting == 200 else 'no posting'
        self.send('{} Fake news server ready ({})'.format(server.greeting, posting))
        while True:
            line = self.rfile.readline()
            if not line:
                return
            words = line.decode('utf-8').strip().split(' ')
            verb, args = words[0].upper(), words[1:]
            if verb == 'QUIT':
                self.send('205 bye')
                return
            if verb == 'MODE':
                self.send('{} reader mode'.format(server.greeting))
            elif verb == 'AUTHINFO' and args and args[0].upper() == 'USER':
                user = args[1]
                self.send('381 password please')
            elif verb == 'AUTHINFO' and args and args[0].upper() == 'PASS':
                if server.users.get(user) == ' '.join(args[1:]):
                    authed = True
                    self.send('281 welcome')
                else:
                    self.send('481 rejected')
            elif server.require_auth and not authed:
                self.send('480 authentication required')
            elif verb == 'LIST':
                self.send('215 list follows')
                self.send_block(['{} {} {} y'.format(name, len(items), 1).encode()
                                 for name, items in server.groups.items()])
            elif verb == 'GROUP':
                if args[0] not in server.groups:
                    self.send('411 no such group')
                    continue
                group = server.groups[args[0]]
                self.send('211 {} {} {} {}'.format(len(group), 1 if group else 0, len(group), args[0]))
            elif verb in ('OVER', 'XOVER'):
                if verb == 'OVER' and getattr(server, 'xover_only', False):
                    self.send('500 unknown command')
                    continue
                first, _, last = args[0].partition('-')
                chosen = [a for a in group if int(first) <= a['number'] <= int(last)]
                if not chosen:
                    self.send('423 no articles')
                    continue
                self.send('224 overview')
                self.send_block(['\t'.join([str(a['number']), a['subject'], a['from'], a['date'],
                                            a['id'], a['refs'], str(len(a['raw'])), '3']).encode('utf-8')
                                 for a in chosen])
            elif verb == 'ARTICLE':
                found = [a for a in group if a['number'] == int(args[0])]
                if not found:
                    self.send('423 no such article')
                    continue
                self.send('220 {} {}'.format(args[0], found[0]['id']))
                self.send_block(found[0]['raw'].split(b'\r\n'))
            elif verb == 'POST':
                if not server.allow_post:
                    self.send('440 posting not permitted')
                    continue
                self.send('340 send article')
                lines = []
                while True:
                    data = self.rfile.readline()
                    if data in (b'.\r\n', b''):
                        break
                    lines.append(data[1:] if data.startswith(b'..') else data)
                server.posted.append(b''.join(lines))
                self.send('240 article received <new@x>')
            else:
                self.send('500 what?')


class ClientTest(unittest.TestCase):
    def start_server(self, **kw):
        server = FakeNewsServer(**kw)
        port = server.serve_in_thread()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, port

    def test_list_overview_article(self):
        _server, port = self.start_server()
        with nntp_client.Connection('127.0.0.1', port) as nntp:
            self.assertTrue(nntp.posting_allowed)
            groups, truncated = nntp.list_groups()
            self.assertFalse(truncated)
            self.assertEqual([g[0] for g in groups], ['alt.empty', 'test.one'])
            count, first, last = nntp.group('test.one')
            self.assertEqual((count, first, last), (4, 1, 4))
            records = nntp.overview(first, last)
            self.assertEqual(records[2]['subject'], 'Caffè')
            self.assertEqual(records[2]['from'], 'Lucrèzia')
            raw, truncated = nntp.article(2)
        article = parse_article(raw, truncated)
        self.assertIn('.dot line', article['body'])
        self.assertEqual(article['headers']['From'], 'Bob <bob@example.org>')

    def test_xover_fallback_and_missing_group(self):
        server, port = self.start_server()
        server.xover_only = True
        with nntp_client.Connection('127.0.0.1', port) as nntp:
            nntp.group('test.one')
            self.assertEqual(len(nntp.overview(1, 4)), 4)
            with self.assertRaises(NNTPError) as caught:
                nntp.group('no.such')
            self.assertIn('does not exist', str(caught.exception))

    def test_account_required(self):
        _server, port = self.start_server(require_auth=True)
        with nntp_client.Connection('127.0.0.1', port) as nntp:
            with self.assertRaises(NNTPError) as caught:
                nntp.list_groups()
            self.assertIn('needs an account', str(caught.exception))
        with self.assertRaises(NNTPError) as caught:
            nntp_client.Connection('127.0.0.1', port, username='reader', password='wrong').open()
        self.assertIn('not accepted', str(caught.exception))
        with nntp_client.Connection('127.0.0.1', port, username='reader', password='secret') as nntp:
            self.assertTrue(nntp.authenticated)
            self.assertEqual(len(nntp.list_groups()[0]), 2)

    def test_post_with_dot_stuffing_and_refusal(self):
        server, port = self.start_server(greeting=201)
        article = build_article('Lele Test <t@example.org>', 'test.one', 'Ciao è',
                                'Line one\n.starts with dot\n', ['<a1@x>'])
        with nntp_client.Connection('127.0.0.1', port) as nntp:
            self.assertFalse(nntp.posting_allowed)
            self.assertIn('received', nntp.post(article))
        posted = server.posted[0]
        self.assertIn(b'\r\n.starts with dot\r\n', posted)
        self.assertIn(b'Subject: =?utf-8?', posted)
        self.assertIn(b'References: <a1@x>', posted)
        server.allow_post = False
        with nntp_client.Connection('127.0.0.1', port) as nntp:
            with self.assertRaises(NNTPError) as caught:
                nntp.post(article)
        self.assertIn('does not allow posting without an account', str(caught.exception))

    def test_tls(self):
        import ssl, subprocess, tempfile, os
        directory = tempfile.mkdtemp()
        key, cert = os.path.join(directory, 'k.pem'), os.path.join(directory, 'c.pem')
        try:
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                            '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
                            '-keyout', key, '-out', cert], check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest('openssl not available')
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert, key)
        _server, port = self.start_server(ssl_context=server_context)
        with self.assertRaises(NNTPError) as caught:
            nntp_client.Connection('localhost', port, tls=True).open()
        self.assertIn('not trusted', str(caught.exception))
        client_context = ssl.create_default_context(cafile=cert)
        with nntp_client.Connection('localhost', port, tls=True, context=client_context) as nntp:
            self.assertEqual(nntp.group('test.one')[0], 4)

    def test_cancel_and_bad_input(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaises(nntp_client.Cancelled):
            nntp_client.Connection('127.0.0.1', 1, stop=stop).open()
        for host in ('', 'a b', 'x\r\nQUIT'):
            with self.assertRaises(NNTPError):
                nntp_client.Connection(host)
        _server, port = self.start_server()
        with nntp_client.Connection('127.0.0.1', port) as nntp:
            with self.assertRaises(NNTPError):
                nntp.group('bad\r\nQUIT')


class HelperTest(unittest.TestCase):
    def records(self):
        rows = [
            b'1\tFirst\tAnn <a@x>\tMon, 02 Nov 2026 10:00:00 +0000\t<a1@x>\t\t100\t3',
            b'2\tRe: First\tBob <b@x>\tMon, 02 Nov 2026 11:00:00 +0000\t<a2@x>\t<a1@x>\t100\t3',
            b'3\tOther\tCy <c@x>\tTue, 03 Nov 2026 09:00:00 +0000\t<a3@x>\t\t100\t3',
            b'4\tRe: First\tDi <d@x>\tWed, 04 Nov 2026 09:00:00 +0000\t<a4@x>\t<a1@x> <a2@x>\t100\t3',
            b'5\tRe: lost\tEd <e@x>\tbad date\t<a5@x>\t<gone@x>\t100\t3',
            b'broken line',
        ]
        return [r for r in (parse_overview(row) for row in rows) if r]

    def test_threads(self):
        order = [(parent, r['number']) for parent, r in build_threads(self.records())]
        # Thread of message 1 has the newest reply (4 Nov), so it comes first.
        self.assertEqual(order, [('', 1), ('<a1@x>', 2), ('<a2@x>', 4), ('', 3), ('', 5)])

    def test_reference_loop_keeps_every_message(self):
        records = self.records()[:2]
        records[0]['references'] = ['<a2@x>']
        self.assertEqual(len(build_threads(records)), 2)

    def test_reply_helpers(self):
        self.assertEqual(reply_subject('Hello'), 'Re: Hello')
        self.assertEqual(reply_subject('RE: Hello'), 'RE: Hello')
        article = {'headers': {'From': 'Bob <b@x>'}, 'body': 'Hi\n> old\n\nbye\n-- \nsig\n'}
        self.assertEqual(quote_body(article), 'Bob wrote:\n> Hi\n>> old\n>\n> bye\n\n')

    def test_build_article_validation(self):
        for sender, groups, subject, body in (
                ('nobody', 'a.b', 's', 'b'), ('A <a@x>', '', 's', 'b'),
                ('A <a@x>', 'a b;c', 's', 'b'), ('A <a@x>', 'a.b', ' ', 'b'),
                ('A <a@x>', 'a.b', 's', '  '), ('A <a@x>\r\nBcc: x', 'a.b', 's', 'b')):
            with self.assertRaises(NNTPError):
                build_article(sender, groups, subject, body)
        article = build_article('a@x', 'a.b, c.d', 'Hi', 'text')
        self.assertIn(b'Newsgroups: a.b,c.d\r\n', article)

    def test_binary_posts_are_summarised(self):
        raw = (b'From: a@x\r\nSubject: pics\r\n\r\nLook:\r\n=ybegin line=128 size=3 name=cat.jpg\r\n'
               b'\x01\x02\x03\r\n=yend size=3\r\nbye\r\n')
        article = parse_article(raw)
        self.assertEqual(article['attachments'], ['cat.jpg (yEnc)'])
        self.assertIn('[binary file not shown]', article['body'])
        self.assertIn('bye', article['body'])

    def test_public_servers_are_well_formed(self):
        for name, host, port, tls, account, note in nntp_client.PUBLIC_SERVERS:
            self.assertTrue(name and note)
            self.assertNotIn(' ', host)
            self.assertIn(port, (119, 563))
            self.assertEqual(tls, port == 563)
            self.assertIn(account, nntp_client.ACCOUNT_NOTES)


if __name__ == '__main__':
    unittest.main()
