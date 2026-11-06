"""Check GitHub Releases for a newer version and fetch it safely.

Only release metadata is requested; nothing about the user or their
accounts is sent. Downloads are verified against the SHA-256 digest GitHub
publishes for each release file before they replace anything.
"""
import hashlib
import json
import os
from pathlib import Path
import urllib.request

from . import __version__

REPO = 'mohammadtondar/bale-desktop'
LATEST_API = 'https://api.github.com/repos/%s/releases/latest' % REPO
CHECK_INTERVAL = 6 * 3600


def parse_version(text):
    """'v0.2.7' -> (0, 2, 7); raises ValueError for anything else."""
    core = text.strip().lstrip('vV').split('-')[0].split('+')[0]
    parts = core.split('.')
    if not 1 <= len(parts) <= 4 or not all(p.isdigit() for p in parts):
        raise ValueError('not a version: %r' % text)
    return tuple(int(p) for p in parts) + (0,) * (4 - len(parts))


def is_newer(latest, current=__version__):
    try:
        return parse_version(latest) > parse_version(current)
    except ValueError:
        return False


class Release:
    def __init__(self, data):
        self.tag = data['tag_name']
        self.version = self.tag.lstrip('vV')
        self.page = data['html_url']
        self.notes = data.get('body') or ''
        self.assets = {a['name']: a for a in data.get('assets', [])
                       if isinstance(a, dict) and a.get('name') and a.get('browser_download_url')}

    def asset(self, suffix):
        """The release file whose name ends with suffix, e.g. '_x86_64.AppImage'."""
        return next((a for name, a in self.assets.items() if name.endswith(suffix)), None)


def fetch_latest(timeout=20):
    request = urllib.request.Request(LATEST_API, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'bale-desktop/%s' % __version__,
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return Release(json.load(response))


def download(asset, target, progress=None, timeout=30):
    """Download a release file to target, verifying its SHA-256 digest."""
    digest = asset.get('digest') or ''
    if not digest.startswith('sha256:'):
        raise ValueError('release file has no SHA-256 digest; not installing it')
    target = Path(target)
    partial = target.with_name(target.name + '.part')
    request = urllib.request.Request(asset['browser_download_url'],
                                     headers={'User-Agent': 'bale-desktop/%s' % __version__})
    sha = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(partial, 'wb') as output:
            total = int(response.headers.get('Content-Length') or asset.get('size') or 0)
            done = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                output.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
        if sha.hexdigest() != digest.split(':', 1)[1].lower():
            raise ValueError('downloaded file does not match its published SHA-256')
        return partial
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def running_appimage():
    """Path of the AppImage this process runs from, if any and replaceable."""
    path = os.environ.get('APPIMAGE')
    if not path:
        return None
    path = Path(path)
    if path.is_file() and os.access(path.parent, os.W_OK) and os.access(path, os.W_OK):
        return path
    return None


def install_appimage(release, progress=None):
    """Replace the running AppImage with the new release; returns its path."""
    current = running_appimage()
    asset = release.asset('_x86_64.AppImage')
    if current is None or asset is None:
        raise ValueError('no AppImage to update')
    partial = download(asset, current, progress)
    partial.chmod(0o755)
    os.replace(partial, current)   # the running copy stays mapped until restart
    return current
