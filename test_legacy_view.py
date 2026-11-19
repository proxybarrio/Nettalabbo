"""Test visual link semantics without contacting third-party servers."""
import threading
import socket
import unittest
from unittest.mock import patch
from legacy_protocols import LegacyResult, fetch
from legacy_view import segments, raw_text, link_color


class HyperlinkRenderingTests(unittest.TestCase):
    def test_gopher_menu_links_are_underlying_targets_and_info_is_plain(self):
        raw = (b'1Directories\t/menu\tserver.test\t70\r\n'
               b'0Read me\t/readme\tserver.test\t70\r\n'
               b'iInformation\t\t\t\r\n.\r\n')
        result = LegacyResult('gopher://server.test/1', 'gopher', 'Gopher menu',
                raw.decode(), [('Directories','gopher://server.test/1/menu'),
                               ('Read me','gopher://server.test/0/readme')], len(raw), raw)
        seg = segments(result)
        self.assertEqual([x[0] for x in seg if x[2]], ['folder','document'])
        self.assertEqual([x[2] for x in seg if x[2]], [x[1] for x in result.links])
        self.assertIn(('info','Information\n',None), seg)
        self.assertNotIn('/readme', ''.join(x[1] for x in seg))

    def test_gemtext_link_is_in_place_and_heading_is_distinct(self):
        content = '# Welcome\nSee below\n=> gemini://example.net/a Read the article\n'
        result = LegacyResult('gemini://example.net/', 'gemini', '20 text/gemini',
                              content, [('Read the article','gemini://example.net/a')], 90)
        seg = segments(result)
        self.assertIn(('heading','Welcome\n',None), seg)
        self.assertIn(('document','▸ Read the article\n','gemini://example.net/a'), seg)
        self.assertEqual(len([x for x in seg if x[2]]), 1)

    def test_raw_response_is_not_fabricated(self):
        res = LegacyResult('gemini://localhost/', 'gemini','20 text/gemini',
                           '# Example', [], 24, b'20 text/gemini\r\n# Example')
        self.assertEqual(raw_text(res), '20 text/gemini\r\n# Example')
        res.raw_response = b''
        self.assertIn('not retained', raw_text(res))

    def test_link_colors_are_different(self):
        self.assertEqual(len({link_color(x) for x in ('folder','document','external')}), 3)

    def test_gopher_html_link_and_telnet_link_correctly_classified(self):
        raw = (b'hHTTP\tURL:https://example.org/\ttest.local\t70\r\n'
               b'8Telnet service\t\ttelnet.test\t2323\r\n.\r\n')
        with patch('legacy_protocols.tcp_fetch', return_value=raw):
            result = fetch('gopher://test.local/1')
        self.assertEqual(result.links[0][1], 'https://example.org/')
        self.assertEqual(result.links[1][1], 'telnet://telnet.test:2323')
        self.assertEqual([s[0] for s in segments(result) if s[2]], ['external', 'external'])

    def test_cancelled_gopher_socket_closes_instead_of_waiting_for_timeout(self):
        ready=threading.Event(); accepted=threading.Event(); shutdown=threading.Event()
        listener=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1',0));listener.listen(1)
        port=listener.getsockname()[1]
        def server():
            ready.set()
            conn,_=listener.accept()
            with conn:
                accepted.set()
                conn.recv(128)
                try: conn.recv(128)
                except OSError: pass
            shutdown.set();listener.close()
        t=threading.Thread(target=server,daemon=True);t.start();ready.wait(2)
        stop=threading.Event();errors=[]
        def client():
            try: fetch('gopher://127.0.0.1:{}/1'.format(port),stop=stop)
            except Exception as exc: errors.append(exc)
        ct=threading.Thread(target=client,daemon=True);ct.start()
        self.assertTrue(accepted.wait(2))
        stop.set();ct.join(3);t.join(3)
        self.assertFalse(ct.is_alive(), 'cancellation must close the socket promptly')
        self.assertTrue(shutdown.is_set())

if __name__ == '__main__':
    unittest.main()
