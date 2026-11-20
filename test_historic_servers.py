import unittest
import historic_servers as hs

class HistoricServersTests(unittest.TestCase):
    def test_catalog_unique(self):
        ids=[e['id'] for e in hs.HISTORIC_SERVERS]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertGreaterEqual(len(ids),11)
    def test_telnet_endpoint(self):
        self.assertEqual(hs.connection_fields(hs.get_entry('fics')), ('Telnet','freechess.org',5000,''))
    def test_ssh_endpoint(self):
        self.assertEqual(hs.connection_fields(hs.get_entry('sdf')), ('SSH','tty.sdf.org',22,'new'))
    def test_horizons_is_not_telnet(self):
        self.assertIsNone(hs.connection_fields(hs.get_entry('horizons')))
    def test_groups(self):
        self.assertEqual(len(hs.catalog_groups('telnet')),19)
        for item in hs.catalog_groups('telnet'):
            self.assertTrue(item['url'].startswith('https://'), item['id'])
            self.assertTrue(1 <= int(item['port']) <= 65535, item['id'])
        self.assertEqual(len(hs.catalog_groups('ssh')),4)
        self.assertEqual(len(hs.catalog_groups('reference')),3)
    def test_dual_connect_choices(self):
        nyx=hs.get_entry('nyx')
        self.assertEqual(nyx['host'],'nyx.nyx.net')
        self.assertEqual(hs.protocol_endpoint(nyx,'SSH'),('nyx.nyx.net',22,'',True))
        self.assertEqual(hs.protocol_endpoint(nyx,'Telnet'),('nyx.nyx.net',23,'',False))
        fics=hs.get_entry('fics')
        self.assertEqual(hs.protocol_endpoint(fics,'Telnet'),('freechess.org',5000,'',True))
        self.assertEqual(hs.protocol_endpoint(fics,'SSH'),('freechess.org',22,'',False))
        self.assertFalse(hs.protocol_endpoint(hs.get_entry('horizons'),'SSH')[3])
        self.assertFalse(hs.protocol_endpoint(hs.get_entry('horizons'),'Telnet')[3])
        with self.assertRaises(ValueError): hs.protocol_endpoint(nyx,'FTP')

    def test_source_integration(self):
        from pathlib import Path
        src=(Path(__file__).parent/'nettalabbo.py').read_text()
        self.assertIn('historic_servers_dialog',src)
        self.assertIn("text='Historic servers...'",src)
        self.assertIn("text='Connect via SSH'",src)
        self.assertIn("text='Connect via Telnet'",src)

if __name__=='__main__': unittest.main()
