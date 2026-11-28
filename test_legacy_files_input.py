"""Gopher/Gemini files, Gemini input requests and Legacy Navigator text size."""
import os
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import legacy_protocols as lp
import legacy_view as lv

PNG_1x1 = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000'
                        '1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082')


class ProtocolTest(unittest.TestCase):
    def gopher(self, url, payload):
        with patch.object(lp, 'tcp_fetch', return_value=payload) as fetch:
            result = lp.fetch(url)
        return result, fetch

    def test_gopher_file_types_are_files(self):
        result, fetch = self.gopher('gopher://example.org/g/pic.gif', b'GIF89a' + bytes(50))
        self.assertTrue(result.is_file)
        self.assertEqual(result.media_type, 'image/gif')
        self.assertEqual(fetch.call_args[0][-1], lp.MAX_FILE_BYTES)
        result, _ = self.gopher('gopher://example.org/9/a.zip', b'PK\x03\x04rest')
        self.assertEqual((result.is_file, result.media_type), (True, 'application/zip'))

    def test_text_document_with_binary_content_is_a_file(self):
        result, fetch = self.gopher('gopher://example.org/0/odd', b'abc\x00\x01\x02')
        self.assertTrue(result.is_file)
        self.assertFalse(result.truncated)
        self.assertEqual(fetch.call_args[0][-1], lp.MAX_BYTES)
        # Read with the text limit: reaching it means the file is incomplete.
        result, _ = self.gopher('gopher://example.org/0/odd', b'\x00' * lp.MAX_BYTES)
        self.assertTrue(result.truncated)

    def test_text_and_menus_unchanged(self):
        result, _ = self.gopher('gopher://example.org/0/readme', b'Hello\r\n')
        self.assertFalse(result.is_file)
        self.assertEqual(result.content, 'Hello\r\n')

    def test_truncated_file_is_flagged(self):
        with patch.object(lp, 'MAX_FILE_BYTES', 10):
            result, _ = self.gopher('gopher://example.org/9/big', b'0123456789')
        self.assertTrue(result.truncated)
        self.assertIn('incomplete', result.content)

    def test_gemini_input_requests(self):
        r = lp.status_response(b'10 Search terms?\r\n', 'gemini://x/s', 'gemini')
        self.assertEqual((r.input_prompt, r.input_sensitive), ('Search terms?', False))
        r = lp.status_response(b'11 Password\r\n', 'gemini://x/p', 'gemini')
        self.assertTrue(r.input_sensitive)

    def test_gemini_binary_body_is_a_file(self):
        r = lp.status_response(b'20 image/png\r\n' + PNG_1x1, 'gemini://x/i', 'gemini')
        self.assertTrue(r.is_file)
        self.assertEqual(r.raw_response, PNG_1x1)
        r = lp.status_response(b'20 text/gemini; lang=it\r\n# Ciao\n', 'gemini://x/', 'gemini')
        self.assertFalse(r.is_file)

    def test_large_gemini_text_is_capped_for_display(self):
        r = lp.status_response(b'20 text/plain\r\n' + b'a' * (lp.MAX_BYTES + 10), 'gemini://x/', 'gemini')
        self.assertEqual(len(r.content), lp.MAX_BYTES)
        self.assertIn('shown up to', r.status)

    def test_sniffing_and_hex_dump(self):
        self.assertEqual(lp.sniff_media_type(PNG_1x1), 'image/png')
        self.assertEqual(lp.sniff_media_type(b'\xff\xd8\xffabc'), 'image/jpeg')
        self.assertEqual(lp.sniff_media_type(b'unknown'), 'application/octet-stream')
        result = lp.file_result('gopher://x/9/f', 'gopher', 'file', b'PK\x03\x04' + b'A' * 20)
        dump = lv.raw_text(result)
        self.assertIn('00000000  50 4b 03 04', dump)
        self.assertIn('PK..AAAA', dump)


class NavigatorTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'HOME': self.home.name})
        self.env.start()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'No display: {exc}')
        self.root.withdraw()
        import nettalabbo
        from pathlib import Path
        self.n = nettalabbo
        # nettalabbo computes its settings paths at import time: point them to
        # the temporary home so the test never touches real user settings.
        app_dir = Path(self.home.name) / '.config' / 'nettalabbo'
        for name, value in (('APP_DIR', app_dir), ('SETTINGS_FILE', app_dir / 'settings.json'),
                            ('LEGACY_SETTINGS_FILES', [])):
            patcher = patch.object(nettalabbo, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = nettalabbo.App(self.root)
        self.app.select_page('Legacy Navigator')

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.env.stop()
        self.home.cleanup()

    def wait(self):
        for _ in range(80):
            self.root.update()
            if 'Legacy Navigator' not in self.app.tasks:
                break
            time.sleep(0.03)
        self.root.update()

    def open(self, url, responses):
        def fake_fetch(address, pins=None, stop=None):
            return responses[address]
        with patch.object(self.n, 'legacy_fetch', side_effect=fake_fetch):
            self.app.inputs['legacy_url'].set(url)
            self.app.execute_legacy()
            self.wait()
            self.wait()

    def test_text_size_is_bounded_and_remembered(self):
        widget = self.app.output['Legacy Navigator']
        self.assertIn('12', str(widget.cget('font')))
        for _ in range(40):
            self.app.legacy_zoom(+1)
        self.assertEqual(self.app.settings['legacy_font_size'], self.app.LEGACY_FONT_MAX)
        self.app.legacy_zoom(0)
        self.app.legacy_zoom(+2)
        saved = self.n.App(tk.Toplevel(self.root))
        saved.select_page('Legacy Navigator')
        self.assertEqual(saved.legacy_font_size(), 14)

    def test_image_file_preview_and_save(self):
        source = Path(self.home.name) / 'made-by-tk.png'
        picture = tk.PhotoImage(master=self.root, width=6, height=4)
        picture.put('#1d5f8a', to=(0, 0, 6, 4))
        picture.write(str(source), format='png')
        png = source.read_bytes()
        result = lp.file_result('gopher://example.org:70/I/dir/pic.png', 'gopher', 'Gopher file', png)
        self.assertEqual(result.media_type, 'image/png')
        self.open(result.address, {result.address: result})
        widget = self.app.output['Legacy Navigator']
        self.assertEqual(len(widget.image_names()), 1)
        self.assertIn('Save file', widget.get('1.0', 'end'))
        target = Path(self.home.name) / 'out.png'
        with patch.object(self.n.filedialog, 'asksaveasfilename', return_value=str(target)) as ask:
            self.app.legacy_save_file()
        self.assertEqual(ask.call_args[1]['initialfile'], 'pic.png')
        self.assertEqual(target.read_bytes(), png)

    def test_gemini_input_repeats_request_with_query(self):
        ask = lp.status_response(b'10 Search?\r\n', 'gemini://example.org/find', 'gemini')
        done = lp.status_response(b'20 text/gemini\r\n# Found\n', 'gemini://example.org/find?a%20b%2Fc', 'gemini')
        with patch.object(self.n.simpledialog, 'askstring', return_value='a b/c') as dialog:
            self.open('gemini://example.org/find', {ask.address: ask, done.address: done})
        self.assertIsNone(dialog.call_args[1].get('show'))
        self.assertEqual(self.app.inputs['legacy_url'].get(), 'gemini://example.org/find?a%20b%2Fc')
        self.assertIn('Found', self.app.output['Legacy Navigator'].get('1.0', 'end'))

    def test_sensitive_input_is_masked_and_cancel_is_reported(self):
        ask = lp.status_response(b'11 Password\r\n', 'gemini://example.org/p', 'gemini')
        with patch.object(self.n.simpledialog, 'askstring', return_value=None) as dialog:
            self.open(ask.address, {ask.address: ask})
        self.assertEqual(dialog.call_args[1].get('show'), '*')
        self.assertEqual(self.app.status['Legacy Navigator'].get(), 'Input cancelled.')


if __name__ == '__main__':
    unittest.main()
