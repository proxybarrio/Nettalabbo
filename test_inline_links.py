"""Inline URL integration and safe links across text-based legacy protocols."""
import unittest
from legacy_protocols import LegacyResult
from legacy_view import segments, distinct_links, raw_text


class InlineHyperlinksTests(unittest.TestCase):
    def test_floodgap_type_zero_document_from_user_example(self):
        body = ('make inadequate gopher clients; see our related document:\n'
                '    gopher://gopher.floodgap.com/0/gopher/wbgopher\n'
                'See also http://gopher.floodgap.com/gopher/.\n'
                'A plain address is not an explicit Gopher menu item.\n')
        result = LegacyResult('gopher://gopher.floodgap.com/0/gopher/proxy', 'gopher',
                              'Document', body, [], len(body), body.encode())
        output = segments(result)
        self.assertEqual([x[2] for x in output if x[2]], [
            'gopher://gopher.floodgap.com/0/gopher/wbgopher',
            'http://gopher.floodgap.com/gopher/'])
        self.assertEqual(len(distinct_links(output)), 2)
        self.assertEqual([kind for kind,text,url in output if url], ['document', 'external'])
        self.assertEqual(raw_text(result), body)
        self.assertEqual(''.join(x[1] for x in output), body)

    def test_across_all_text_legacy_services(self):
        for scheme in ('gopher','gophers','gemini','spartan','nex','scroll','finger',
                       'news','nntp','ftp','dict','scorpion','scorpions', 'guppy',
                       'text','molerat','mercury'):
            with self.subTest(scheme=scheme):
                body = 'New community here: gemini://geminiprotocol.net/ and https://example.org/docs\n'
                result = LegacyResult(scheme + '://example.org/', scheme, 'Document', body, [], len(body))
                links = distinct_links(segments(result))
                self.assertEqual(len(links), 2)
                self.assertEqual(links[0][1], 'gemini://geminiprotocol.net/')

    def test_menu_items_stay_canonical_links(self):
        raw = '1Documents\t/docs\tserver.example\t70\n' \
              'iHelpful address: gopher://other.example/1.\t\t\t\n.\n'
        result = LegacyResult('gopher://server.example/1','gopher','Gopher menu',raw,
                              [('Documents','gopher://server.example/1/docs')],len(raw))
        links = distinct_links(segments(result))
        self.assertEqual([url for label,url in links],
                         ['gopher://server.example/1/docs','gopher://other.example/1'])

    def test_inline_gopher_menu_is_blue_folder(self):
        body = 'Look here: gopher://gopher.floodgap.com/1'
        result = LegacyResult('gopher://gopher.floodgap.com/0/intro','gopher','Document',body,[],len(body))
        self.assertEqual([kind for kind,text,url in segments(result) if url], ['folder'])

    def test_existing_gemtext_and_plain_text_link_coexist(self):
        body = '=> gemini://example.org/first First page\nMore here: gopher://example.org/1\n'
        result = LegacyResult('gemini://example.org/','gemini','Gemtext',body,
                              [('First page','gemini://example.org/first')],len(body))
        links = distinct_links(segments(result))
        self.assertEqual(len(links), 2)

    def test_untrusted_schemes_and_broken_ports_are_not_clickable(self):
        body = ('javascript://bad.test/ file://etc/passwd data://bad.test/ '
                'gopher://example.org:99999/1 https://user:pw@example.com/ '
                'https://good.example/(documentation).')
        result = LegacyResult('finger://example.org/','finger','Document',body,[],len(body))
        urls = [x[2] for x in segments(result) if x[2]]
        self.assertEqual(urls, ['https://good.example/(documentation)'])

    def test_duplicate_urls_are_single_menu_item_but_both_are_clickable(self):
        body = 'gopher://foo.example/1 then gopher://foo.example/1\n'
        result = LegacyResult('finger://foo.example/','finger','Document',body,[],len(body))
        self.assertEqual(sum(bool(s[2]) for s in segments(result)), 2)
        self.assertEqual(len(distinct_links(segments(result))), 1)

    def test_www_addresses_are_supported_with_https(self):
        result = LegacyResult('dict://dictionary.example/hi','dict','Document',
                              'See www.example.org/page, then return.',[],15)
        self.assertEqual(distinct_links(segments(result))[0][1], 'https://www.example.org/page')


if __name__ == '__main__':
    unittest.main()
