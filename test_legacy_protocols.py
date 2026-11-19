"""Protocol transport tests use loopback servers and mocks, never live third-party traffic."""
import socket
import threading
import unittest
from unittest.mock import patch
import legacy_protocols as legacy


def one_shot(response):
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    listener.bind(('127.0.0.1',0));listener.listen(1)
    port=listener.getsockname()[1]
    requests=[]
    def serve():
        try:
            client, _=listener.accept()
            with client:
                client.settimeout(2)
                try: requests.append(client.recv(4096))
                except socket.timeout: requests.append(b'')
                client.sendall(response)
        finally:
            listener.close()
    t=threading.Thread(target=serve,daemon=True);t.start()
    return port,requests,t

class LegacyTests(unittest.TestCase):
    def test_catalog_contains_user_protocols(self):
        expected={'gopher','gophers','gemini','spartan','nex','titan','scroll','finger',
                  'news','nntp','telnet','ssh','ftp','dict','scorpion','guppy','text',
                  'molerat','mercury','terse'}
        self.assertTrue(expected.issubset(set(legacy.SCHEMES)))
        self.assertEqual(legacy.SCHEMES['guppy']['port'],6775)
        self.assertEqual(legacy.SCHEMES['mercury']['port'],1958)
        self.assertEqual(legacy.SCHEMES['text']['port'],1961)
        self.assertEqual(legacy.SCHEMES['scroll']['port'],5699)

    def test_remote_and_upload_not_faked_as_get(self):
        for url in ('ssh://localhost','telnet://localhost','titan://localhost/','terse://localhost/'):
            with self.assertRaises(legacy.LegacyError):legacy.fetch(url)

    def test_rejects_bad_request_line(self):
        with self.assertRaises(legacy.LegacyError):legacy.parse_url('gemini://host/x\r\nBAD')
        with self.assertRaises(legacy.LegacyError):legacy.parse_url('dict://u:password@host/word')

    def test_gopher_menu(self):
        port,req,thread=one_shot(b'1Links\t/menu\t127.0.0.1\t70\r\nihi\t\t\t\r\n.\r\n')
        out=legacy.fetch('gopher://127.0.0.1:{}/1'.format(port))
        thread.join(2)
        self.assertEqual(req,[b'\r\n'])
        self.assertEqual(len(out.links),1)
        self.assertEqual(out.links[0][1],'gopher://127.0.0.1:70/1/menu')

    def test_nex_request(self):
        port,req,thread=one_shot(b'=> nex://elsewhere.test/ Next\nHello\n')
        out=legacy.fetch('nex://127.0.0.1:{}/hello'.format(port))
        thread.join(2)
        self.assertEqual(req,[b'/hello\r\n'])
        self.assertEqual(len(out.links),1)

    def test_spartan_request(self):
        port,req,thread=one_shot(b'2 text/gemini\r\n# Page\n=> /next Link\n')
        out=legacy.fetch('spartan://127.0.0.1:{}/index'.format(port))
        thread.join(2)
        self.assertEqual(req,[b'127.0.0.1 /index 0\r\n'])
        self.assertEqual(out.links[0][1],'spartan://127.0.0.1:{}/next'.format(port))

    def test_mercury_server_initiated(self):
        port,req,thread=one_shot(b'Hello Mercury!\n')
        out=legacy.fetch('mercury://127.0.0.1:{}/'.format(port))
        thread.join(2)
        self.assertEqual(req,[] if not req else [b''])
        self.assertIn('Hello Mercury',out.content)

    def test_finger(self):
        port,req,thread=one_shot(b'Finger user profile\r\n')
        out=legacy.fetch('finger://bob@127.0.0.1:{}'.format(port))
        thread.join(2)
        self.assertEqual(req,[b'bob\r\n'])
        self.assertIn('profile',out.content)

    def test_dict(self):
        port,req,thread=one_shot(b'220 DICT ready\r\n150 1 definitions\r\n151 test\r\nA definition\r\n.\r\n250 done\r\n')
        out=legacy.fetch('dict://127.0.0.1:{}/test'.format(port))
        thread.join(2)
        self.assertIn(b'DEFINE * "test"\r\n',req[0])
        self.assertIn('A definition',out.content)

    def test_gemini_tls_exchange_with_mock(self):
        with patch.object(legacy,'tcp_fetch',return_value=b'20 text/gemini\r\n# Hello\n=> /two Page two\n') as mocked:
            out=legacy.fetch('gemini://sample.test/')
        self.assertEqual(len(out.links),1)
        self.assertTrue(mocked.call_args[0][3])

    def test_text_protocol_mock(self):
        with patch.object(legacy,'tcp_fetch',return_value=b'20 text/plain;charset=utf-8\r\nTEXT protocol\n') as mocked:
            out=legacy.fetch('text://sample.test/')
        self.assertFalse(mocked.call_args[0][3])
        self.assertIn('TEXT protocol',out.content)

    def test_scroll_metadata(self):
        with patch.object(legacy,'tcp_fetch',return_value=b'20 text/scroll\r\nAlice\r\n2024-01-01\r\n2024-02-02\r\n# Body\n') as mocked:
            out=legacy.fetch('scroll://sample.test/a')
        self.assertIn('Alice',out.status)
        self.assertIn('Body',out.content)
        self.assertTrue(mocked.call_args[0][3])

    def test_guppy_metadata_and_ack(self):
        listener=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1];observed=[]
        def serve():
            try:
                listener.settimeout(3)
                r,source=listener.recvfrom(2048);observed.append(r)
                listener.sendto(b'6 text/plain\r\nHELLO',source)
                r,_=listener.recvfrom(2048);observed.append(r)
                listener.sendto(b'7\r\n',source)
                r,_=listener.recvfrom(2048);observed.append(r)
            finally:listener.close()
        t=threading.Thread(target=serve,daemon=True);t.start()
        out=legacy.fetch('guppy://127.0.0.1:{}/'.format(port))
        t.join(2)
        self.assertEqual(out.content,'HELLO')
        self.assertEqual(observed[1],b'6\r\n')
        self.assertEqual(observed[2],b'7\r\n')

    def test_trust_required_explicit(self):
        e=legacy.TrustRequired('gemini://example:1965','a'*64)
        self.assertIn('fingerprint',str(e))

if __name__=='__main__':unittest.main()

class ExperimentalProtocolTests(unittest.TestCase):
    def test_scorpion_read(self):
        port, req, t = one_shot(b'20 text/plain\r\nScorpion hello!\n')
        value = legacy.fetch('scorpion://127.0.0.1:{}/some#local'.format(port))
        t.join(2)
        self.assertIn('Scorpion hello', value.content)
        self.assertEqual(req[0], ('R scorpion://127.0.0.1:{}/some\r\n'.format(port)).encode())

    def test_molerat_read_format(self):
        with patch.object(legacy,'tcp_fetch',return_value=(
                b'10\r\nmessage:Success\r\ntype:text/plain\r\nlength:5\r\n\r\nHello')) as mock:
            value=legacy.fetch('molerat://sample.test/hello')
        self.assertEqual(value.content,'Hello')
        self.assertTrue(mock.call_args[0][3])
        self.assertIn(b'get sample.test/hello\r\n\r\n',mock.call_args[0][2])

    def test_titan_requires_separate_explicit_upload(self):
        with self.assertRaises(legacy.LegacyError):
            legacy.fetch('titan://example.org/a')
        with self.assertRaises(legacy.LegacyError):
            legacy.titan_upload('titan://example.org/a', b'')
        with patch.object(legacy,'tcp_fetch',return_value=b'20 text/gemini\r\nThanks!') as mock:
            value=legacy.titan_upload('titan://example.org/file',b'TEST')
        self.assertIn('Thanks!',value.content)
        wire=mock.call_args[0][2]
        self.assertIn(b';size=4;mime=application/octet-stream\r\nTEST',wire)
        self.assertTrue(mock.call_args[0][3])

    def test_terse_future_only(self):
        self.assertEqual(legacy.SCHEMES['terse']['mode'],'reference')
        with self.assertRaises(legacy.LegacyError):
            legacy.fetch('terse://localhost:1234/')
