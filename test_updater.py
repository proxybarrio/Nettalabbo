"""Offline tests for the GitHub Releases updater (no network, no root)."""
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nettalabbo
import updater

HERE = Path(__file__).resolve().parent


class FakeResponse(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url


def release_json(version='0.5.3-10', size=1000, **extra):
    name = f'nettalabbo_{version}_all.deb'
    base = 'https://github.com/proxybarrio/nettalabbo/releases/download/v' + version
    doc = {'tag_name': 'v' + version, 'draft': False, 'prerelease': False, 'body': 'Notes',
           'html_url': base, 'assets': [
               {'name': name, 'size': size, 'browser_download_url': f'{base}/{name}'},
               {'name': 'SHA256SUMS', 'size': 100, 'browser_download_url': f'{base}/SHA256SUMS'}]}
    doc.update(extra)
    return doc


def build_deb(folder, version, package='nettalabbo'):
    root = Path(folder) / 'root'
    (root / 'DEBIAN').mkdir(parents=True)
    (root / 'DEBIAN' / 'control').write_text(
        f'Package: {package}\nVersion: {version}\nArchitecture: all\n'
        'Maintainer: Test <test@example.org>\nDescription: test\n')
    target = Path(folder) / f'nettalabbo_{version}_all.deb'
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(root), str(target)],
                   check=True, capture_output=True)
    return target.read_bytes()


class VersionTest(unittest.TestCase):
    def test_debian_ordering(self):
        cases = [('0.5.3-9', '0.5.3-8', 1), ('0.5.3-10', '0.5.3-9', 1), ('0.5.4-1', '0.5.3-10', 1),
                 ('0.5.3-9', '0.5.3-9', 0), ('0.6~rc1-1', '0.6-1', -1), ('1:0.1-1', '0.9-1', 1)]
        for a, b, sign in cases:
            result = updater.compare_versions(a, b)
            self.assertEqual((result > 0) - (result < 0), sign, (a, b))

    @unittest.skipUnless(shutil.which('dpkg'), 'dpkg not installed')
    def test_matches_dpkg(self):
        for a, b in [('0.5.3-9', '0.5.3-10'), ('0.5.3a-1', '0.5.3-1'), ('0.5.3+1-1', '0.5.3-2')]:
            ours = updater.compare_versions(a, b) > 0
            theirs = subprocess.run(['dpkg', '--compare-versions', a, 'gt', b]).returncode == 0
            self.assertEqual(ours, theirs, (a, b))


class ReleaseTest(unittest.TestCase):
    def test_parse(self):
        release = updater.parse_release(release_json())
        self.assertEqual(release['version'], '0.5.3-10')
        self.assertTrue(release['package_url'].endswith('nettalabbo_0.5.3-10_all.deb'))

    def test_rejects_missing_assets_and_prerelease(self):
        doc = release_json()
        doc['assets'] = doc['assets'][:1]
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(doc)
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(release_json(prerelease=True))
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(release_json(version='0.5.3-10; rm -rf'))

    def test_check_newer_or_none(self):
        def opener(url, timeout, accept='x'):
            return FakeResponse(json.dumps(release_json()).encode(), url)
        self.assertIsNotNone(updater.check('0.5.3-9', opener=opener))
        self.assertIsNone(updater.check('0.5.3-10', opener=opener))

    def test_only_github_https(self):
        with self.assertRaises(updater.UpdateError):
            updater._check_url('http://github.com/x')
        with self.assertRaises(updater.UpdateError):
            updater._check_url('https://evil.example/nettalabbo.deb')
        updater._check_url('https://objects.githubusercontent.com/abc')


@unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb not installed')
class DownloadTest(unittest.TestCase):
    def fetch(self, payload, sums, version='0.5.3-10'):
        release = updater.parse_release(release_json(version, size=len(payload)))

        def opener(url, timeout, accept='x'):
            return FakeResponse(sums.encode() if url.endswith('SHA256SUMS') else payload, url)
        return updater.download(release, opener=opener)

    def test_verified_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_deb(tmp, '0.5.3-10')
        sums = f'{hashlib.sha256(payload).hexdigest()}  nettalabbo_0.5.3-10_all.deb\n'
        path = self.fetch(payload, sums)
        try:
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        finally:
            updater.discard(path)
        self.assertFalse(path.parent.exists())

    def test_checksum_mismatch_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_deb(tmp, '0.5.3-10')
        sums = f'{"0" * 64}  nettalabbo_0.5.3-10_all.deb\n'
        before = set(Path(tempfile.gettempdir()).glob('nettalabbo-update-*'))
        with self.assertRaisesRegex(updater.UpdateError, 'Checksum'):
            self.fetch(payload, sums)
        self.assertEqual(set(Path(tempfile.gettempdir()).glob('nettalabbo-update-*')), before)

    def test_wrong_package_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_deb(tmp, '0.5.3-10', package='something-else')
        sums = f'{hashlib.sha256(payload).hexdigest()}  nettalabbo_0.5.3-10_all.deb\n'
        with self.assertRaisesRegex(updater.UpdateError, 'metadata'):
            self.fetch(payload, sums)


class InstallTest(unittest.TestCase):
    def test_command_uses_pkexec_apt(self):
        with tempfile.TemporaryDirectory() as tmp:
            deb = Path(tmp) / 'nettalabbo_0.5.3-10_all.deb'
            deb.write_bytes(b'x')
            with patch('updater.shutil.which', return_value='/usr/bin/pkexec'):
                command = updater.install_command(deb)
            self.assertEqual(command[:4], ['pkexec', 'apt-get', 'install', '-y'])
            self.assertTrue(command[4].startswith('/'))

    def test_refuses_other_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / 'evil.deb'
            other.write_bytes(b'x')
            with self.assertRaises(updater.UpdateError):
                updater.install_command(other)

    def test_cancelled_authorisation(self):
        with tempfile.TemporaryDirectory() as tmp:
            deb = Path(tmp) / 'nettalabbo_0.5.3-10_all.deb'
            deb.write_bytes(b'x')
            denied = subprocess.CompletedProcess([], 126, '', '')
            with patch('updater.shutil.which', return_value='/usr/bin/pkexec'):
                with self.assertRaisesRegex(updater.UpdateError, 'not authorised'):
                    updater.install(deb, runner=lambda *a, **k: denied)
            self.assertTrue(deb.exists())


class PackagingTest(unittest.TestCase):
    def test_version_matches_control(self):
        control = (HERE / 'packaging' / 'control').read_text()
        self.assertIn(f'Version: {nettalabbo.PACKAGE_VERSION}\n', control)

    def test_every_local_module_is_packaged(self):
        build = (HERE / 'packaging' / 'build_deb.sh').read_text()
        source = (HERE / 'nettalabbo.py').read_text()
        imported = set(re.findall(r'^(?:from|import) (\w+)', source, re.M))
        local = {name for name in imported if (HERE / f'{name}.py').exists()}
        self.assertTrue(local)
        for name in local:
            self.assertIn(f'{name}.py', build, name)


if __name__ == '__main__':
    unittest.main()
