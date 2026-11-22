"""Check package-builder safeguards for compatible, readable Debian archives."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent
class DebianArchiveTests(unittest.TestCase):
    def test_staging_root_world_traversable(self):
        script = (ROOT / 'packaging/build_deb.sh').read_text()
        self.assertIn('chmod 0755 "$BUILD_DIR"', script)
        self.assertIn('find "$BUILD_DIR/usr" -type d -exec chmod 0755', script)
    def test_md5_checksums_and_gzip_archive(self):
        script = (ROOT / 'packaging/build_deb.sh').read_text()
        self.assertIn('DEBIAN/md5sums', script)
        self.assertIn('-Zgzip', script)
    def test_version_and_install_guidance(self):
        self.assertIn('Version: 0.5.4-5', (ROOT / 'packaging/control').read_text())
        self.assertIn('sudo apt install ./nettalabbo_0.5.4-5_all.deb', (ROOT / 'INSTALL_XUBUNTU.md').read_text())
if __name__ == '__main__': unittest.main()
