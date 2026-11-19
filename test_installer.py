"""Offline static packaging checks for the preflight installer."""
import subprocess, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
class InstallerTests(unittest.TestCase):
 def test_bash_syntax(self):
  subprocess.run(['bash','-n',str(ROOT/'install-nettalabbo.sh')],check=True)
 def test_preinstalls_deps(self):
  s=(ROOT/'install-nettalabbo.sh').read_text()
  self.assertLess(s.index('sudo apt-get install "${NEEDED[@]}"'),s.index('sudo apt-get install "$PACKAGE"'))
  self.assertIn('apt-get -s install "${NEEDED[@]}"',s)
  self.assertIn('apt-get -s install "$PACKAGE"',s)
  self.assertNotIn('nntplib',s) # removed from Python 3.13+
  for prog in ('ping','traceroute','ssh','telnet','dig'): self.assertIn(prog,s)
 def test_cross_release_dns(self):
  c=(ROOT/'packaging/control').read_text()
  self.assertIn('bind9-dnsutils | dnsutils',c)
 def test_no_apt_calls_from_deb_maintainer_scripts(self):
  for name in ('preinst','postinst','prerm','postrm'):
   self.assertFalse((ROOT/'packaging'/name).exists())
if __name__=='__main__': unittest.main()
