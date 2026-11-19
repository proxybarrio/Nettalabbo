"""Verify all project and legal notices are shipped and readable offline."""
import tempfile
import unittest
from pathlib import Path
from about_documents import ABOUT_DOCUMENTS, load_about_document

ROOT = Path(__file__).resolve().parent

class AboutDocumentsTests(unittest.TestCase):
    def test_every_link_opens_full_document(self):
        self.assertEqual(set(ABOUT_DOCUMENTS), {'why','credits','warning','licence'})
        for key in ABOUT_DOCUMENTS:
            title, content = load_about_document(key, roots=[ROOT])
            self.assertTrue(title)
            self.assertGreater(len(content), 250)

    def test_story_and_disclaimer(self):
        why = load_about_document('why', roots=[ROOT])[1]
        self.assertIn('Ma che cosa? 🤌🏻', why)
        self.assertIn('Alexander Danileiko', why)
        disclaimer = load_about_document('credits', roots=[ROOT])[1]
        for sentence in ('AS IS','at their own risk','applicable law',
                         'permission to access','proxybar@gmail.com'):
            self.assertIn(sentence, disclaimer)

    def test_no_network_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                load_about_document('why', roots=[folder])

if __name__ == '__main__':
    unittest.main()
