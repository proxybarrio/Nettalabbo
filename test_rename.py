import unittest, ast, tempfile, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
class RenameTests(unittest.TestCase):
 def test_old_brand_migration(self):
  source=(ROOT/'nettalabbo.py').read_text()
  self.assertIn("Path.home() / '.config' / 'netlabbo' / 'settings.json'",source)
  self.assertIn("APP_DIR = Path.home() / '.config' / 'nettalabbo'",source)
 def test_new_identity_and_launcher(self):
  script=(ROOT/'packaging'/'build_deb.sh').read_text()
  for piece in ('usr/bin/nettalabbo','usr/share/nettalabbo','nettalabbo.desktop'):
   self.assertIn(piece,script)
  d=(ROOT/'packaging'/'nettalabbo.desktop').read_text()
  for piece in ('Name=Nettalabbo','Exec=nettalabbo','Icon=nettalabbo'):
   self.assertIn(piece,d)
 def test_prior_package_replaced(self):
  control=(ROOT/'packaging'/'control').read_text()
  self.assertIn('Conflicts: netlabbo',control)
  self.assertIn('Replaces: netlabbo',control)
  self.assertRegex(control, r'(?m)^Version: 0\.5\.[4-9]-[0-9]+$')
 def test_image_unmodified(self):
  import hashlib
  old=Path('/mnt/data/netlabbo-source-0.5.0-rev2/assets/netlabbo_original.png')
  new=ROOT/'assets/nettalabbo_original.png'
  if old.exists(): self.assertEqual(hashlib.sha256(old.read_bytes()).digest(),hashlib.sha256(new.read_bytes()).digest())
 def test_no_obsolete_names_in_public_files(self):
  # Legacy label must exist only for migration, old executable history or historical credits.
  self.assertEqual((ROOT/'packaging'/'nettalabbo.desktop').read_text().count('Netlabbo'),0)
if __name__=='__main__': unittest.main()
