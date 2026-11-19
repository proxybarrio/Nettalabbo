"""Self-update from the project's GitHub Releases.

Flow: ask GitHub for the latest published release, compare its Debian version
with the installed one, download the .deb and SHA256SUMS into a private
temporary folder, verify the checksum and the package metadata, then install
with `pkexec apt-get install`, which asks for the administrator password.

Expected release layout (see GITHUB_PUBLISHING.md):
    tag      v<debian version>, e.g. v0.5.3-9
    assets   nettalabbo_<debian version>_all.deb and SHA256SUMS
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

REPOSITORY = 'proxybarrio/nettalabbo'
LATEST_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
PACKAGE = 'nettalabbo'
INSTALL_DIR = Path('/usr/share/nettalabbo')
MAX_PACKAGE_BYTES = 50 * 1024 * 1024
ALLOWED_HOSTS = ('github.com', 'api.github.com', 'objects.githubusercontent.com',
                 'release-assets.githubusercontent.com', 'github-releases.githubusercontent.com')
CHECK_INTERVAL = 24 * 3600
VERSION_RE = re.compile(r'^[0-9][A-Za-z0-9.+~]*(-[A-Za-z0-9.+~]+)?$')


class UpdateError(Exception):
    pass


# --- Debian version comparison (dpkg's verrevcmp), used when dpkg is absent ---

def _order(char):
    if char == '~':
        return -1
    if char.isdigit():
        return 0
    if char.isalpha():
        return ord(char)
    return ord(char) + 256


def _verrevcmp(a, b):
    i = j = 0
    while i < len(a) or j < len(b):
        first_diff = 0
        while (i < len(a) and not a[i].isdigit()) or (j < len(b) and not b[j].isdigit()):
            ac = _order(a[i]) if i < len(a) else 0
            bc = _order(b[j]) if j < len(b) else 0
            if ac != bc:
                return ac - bc
            i += 1
            j += 1
        while i < len(a) and a[i] == '0':
            i += 1
        while j < len(b) and b[j] == '0':
            j += 1
        while i < len(a) and a[i].isdigit() and j < len(b) and b[j].isdigit():
            if not first_diff:
                first_diff = ord(a[i]) - ord(b[j])
            i += 1
            j += 1
        if i < len(a) and a[i].isdigit():
            return 1
        if j < len(b) and b[j].isdigit():
            return -1
        if first_diff:
            return first_diff
    return 0


def _split(version):
    epoch, _, rest = version.rpartition(':') if ':' in version else ('0', '', version)
    upstream, _, revision = rest.rpartition('-') if '-' in rest else (rest, '', '0')
    return int(epoch or 0), upstream, revision


def compare_versions(a, b):
    """Negative, zero or positive, like dpkg --compare-versions."""
    ea, ua, ra = _split(a)
    eb, ub, rb = _split(b)
    if ea != eb:
        return ea - eb
    return _verrevcmp(ua, ub) or _verrevcmp(ra, rb)


# --- What is installed ---

def running_from_package(script_path):
    try:
        return Path(script_path).resolve().parent == INSTALL_DIR
    except OSError:
        return False


def installed_version(fallback):
    """Version recorded by dpkg, or the version compiled into this build."""
    if shutil.which('dpkg-query'):
        try:
            result = subprocess.run(['dpkg-query', '-W', '-f=${Version}', PACKAGE],
                                    capture_output=True, text=True, timeout=5, check=False)
            if result.returncode == 0 and VERSION_RE.match(result.stdout.strip()):
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return fallback


# --- Talking to GitHub ---

def _check_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in ALLOWED_HOSTS:
        raise UpdateError(f'Refusing to download from {parts.scheme}://{parts.hostname}')


def _open(url, timeout, accept='application/octet-stream'):
    _check_url(url)
    request = urllib.request.Request(url, headers={'Accept': accept, 'User-Agent': 'Nettalabbo-updater'})
    response = urllib.request.urlopen(request, timeout=timeout)
    _check_url(response.geturl())  # redirects must stay on GitHub
    return response


def parse_release(document):
    """Extract version and asset URLs from a GitHub release JSON object."""
    if document.get('draft') or document.get('prerelease'):
        raise UpdateError('Latest release is a draft or pre-release')
    version = str(document.get('tag_name', '')).lstrip('vV')
    if not VERSION_RE.match(version):
        raise UpdateError(f'Unexpected release tag {document.get("tag_name")!r}')
    wanted = f'{PACKAGE}_{version}_all.deb'
    assets = {a.get('name'): a for a in document.get('assets', [])}
    if wanted not in assets or 'SHA256SUMS' not in assets:
        raise UpdateError(f'Release {version} lacks {wanted} or SHA256SUMS')
    package = assets[wanted]
    if not 0 < int(package.get('size', 0)) <= MAX_PACKAGE_BYTES:
        raise UpdateError('Release package has an implausible size')
    return {'version': version, 'filename': wanted,
            'package_url': package['browser_download_url'], 'size': int(package['size']),
            'sums_url': assets['SHA256SUMS']['browser_download_url'],
            'notes': str(document.get('body') or '')[:4000],
            'page': document.get('html_url', '')}


def latest_release(timeout=10, opener=None):
    opener = opener or _open
    try:
        with opener(LATEST_URL, timeout, 'application/vnd.github+json') as response:
            document = json.loads(response.read(1024 * 1024).decode('utf-8'))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError('No public release found on GitHub '
                              '(the repository may still be private, or nothing is published yet)') from exc
        raise UpdateError(f'GitHub answered HTTP {exc.code}') from exc
    except (OSError, ValueError) as exc:
        raise UpdateError(f'Cannot reach GitHub: {exc}') from exc
    return parse_release(document)


def check(current_version, timeout=10, opener=None):
    """Return the release dict when it is newer than current_version, else None."""
    release = latest_release(timeout, opener)
    return release if compare_versions(release['version'], current_version) > 0 else None


# --- Download and verification ---

def expected_digest(sums_text, filename):
    for line in sums_text.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1].lstrip('*') == filename and re.fullmatch(r'[0-9a-fA-F]{64}', parts[0]):
            return parts[0].lower()
    raise UpdateError(f'SHA256SUMS has no entry for {filename}')


def download(release, stop=None, progress=None, timeout=30, opener=None):
    """Download and verify; returns the path of a verified .deb in a 0700 folder."""
    opener = opener or _open
    folder = Path(tempfile.mkdtemp(prefix='nettalabbo-update-'))
    os.chmod(folder, 0o700)
    target = folder / release['filename']
    try:
        with opener(release['sums_url'], timeout) as response:
            digest_wanted = expected_digest(response.read(64 * 1024).decode('utf-8', 'replace'),
                                            release['filename'])
        digest = hashlib.sha256()
        received = 0
        with opener(release['package_url'], timeout) as response, open(target, 'wb') as stream:
            while True:
                if stop is not None and stop.is_set():
                    raise UpdateError('Download cancelled')
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_PACKAGE_BYTES:
                    raise UpdateError('Download larger than expected')
                digest.update(chunk)
                stream.write(chunk)
                if progress:
                    progress(received, release['size'])
        if digest.hexdigest() != digest_wanted:
            raise UpdateError('Checksum mismatch: the downloaded package was not installed')
        verify_package(target, release['version'])
        return target
    except Exception:
        discard(target)
        raise


def verify_package(path, version):
    if not shutil.which('dpkg-deb'):
        raise UpdateError('dpkg-deb is required to verify the package')
    result = subprocess.run(['dpkg-deb', '-f', str(path), 'Package', 'Version', 'Architecture'],
                            capture_output=True, text=True, timeout=20, check=False)
    fields = dict(line.split(': ', 1) for line in result.stdout.splitlines() if ': ' in line)
    if result.returncode != 0 or fields.get('Package') != PACKAGE or \
            fields.get('Version') != version or fields.get('Architecture') != 'all':
        raise UpdateError(f'Package metadata does not match release {version}: {fields or result.stderr.strip()}')


def discard(path):
    path = Path(path)
    try:
        path.unlink()
    except OSError:
        pass
    try:
        path.parent.rmdir()
    except OSError:
        pass


# --- Installation ---

def install_command(path):
    path = Path(path).resolve()
    if not path.is_file() or not path.name.startswith(PACKAGE + '_') or path.suffix != '.deb':
        raise UpdateError('Not a downloaded Nettalabbo package')
    if not shutil.which('pkexec'):
        raise UpdateError('pkexec is not available. Install manually with:\n'
                          f'sudo apt-get install {path}')
    # APT resolves dependencies and replaces the older nettalabbo package.
    return ['pkexec', 'apt-get', 'install', '-y', str(path)]


def install(path, runner=subprocess.run):
    command = install_command(path)
    result = runner(command, capture_output=True, text=True, timeout=900, check=False)
    if result.returncode == 126 or result.returncode == 127:
        raise UpdateError('Installation was not authorised')
    if result.returncode != 0:
        raise UpdateError('APT could not install the update:\n' + (result.stderr or result.stdout)[-2000:])
    discard(path)
    return result.stdout
