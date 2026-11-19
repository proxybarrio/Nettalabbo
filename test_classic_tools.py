"""Ensure all ten classic capabilities are accessible and built as real pages."""
import unittest
import nettalabbo
from unittest.mock import patch

CLASSIC = ('Finger','WhoIs','Time','Quote','Ping','Trace','DNS','Scanner','Info','Options')

class ClassicToolTests(unittest.TestCase):
    def test_all_tools_in_navigation(self):
        self.assertEqual(len(CLASSIC), 10)
        for page in CLASSIC:
            self.assertIn(page, nettalabbo.TABS)
            self.assertIn(page, nettalabbo.PAGE_LABELS if page in ('WhoIs','Trace','Scanner','Info','Options') else nettalabbo.PAGE_DESCRIPTIONS)
    def test_obvious_classic_names(self):
        self.assertEqual(nettalabbo.PAGE_LABELS['Scanner'],'Port Scan')
        self.assertEqual(nettalabbo.PAGE_LABELS['Trace'],'Trace')
        self.assertEqual(nettalabbo.PAGE_LABELS['WhoIs'],'WhoIs')
    def test_all_buttons_on_overview(self):
        import inspect
        source=inspect.getsource(nettalabbo.App.make_overview_page)
        for title in ('Finger','WhoIs','Time','Quote','Ping','Trace','DNS','Port Scan','Info','Options'):
            self.assertIn("('"+title+"',", source)
    def test_network_adapters_present(self):
        for method in ('run_text_query','run_probe','execute_scan','query_daytime','query_clock','refresh_info','make_options_page'):
            self.assertTrue(callable(getattr(nettalabbo.App, method)))

if __name__=='__main__': unittest.main()
