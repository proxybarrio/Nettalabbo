"""Check independent modern UI and lack of bundled historic software."""
from pathlib import Path
import unittest
import nettalabbo
ROOT=Path(__file__).parent

class InterfaceTests(unittest.TestCase):
    def test_workspace_structure(self):
        self.assertEqual(nettalabbo.SECTIONS['Start'], ['Overview'])
        self.assertIn('Domain Inspector', nettalabbo.SECTIONS['Domain research'])
        self.assertIn('Mail Inspector', nettalabbo.TABS)
        self.assertIn('SSH', nettalabbo.SECTIONS['Remote access'])
        self.assertIn('Overview', nettalabbo.TABS)
        source=(ROOT/'nettalabbo.py').read_text()
        self.assertIn('self.nav_buttons', source)
        self.assertIn('make_overview_page', source)
        self.assertNotIn('ttk.Notebook(', source.split('    def historic_servers_dialog')[0])

    def test_provenance(self):
        self.assertTrue((ROOT/'PROVENANCE.md').is_file())
        self.assertFalse((ROOT/'ANALISI_ORIGINALE.md').exists())
        self.assertFalse(any(f.suffix.lower() in ('.exe', '.dll', '.hlp', '.ico') for f in ROOT.rglob('*') if f.is_file()))

if __name__=='__main__': unittest.main()
