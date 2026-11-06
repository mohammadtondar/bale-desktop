"""Update checks: version comparison, release parsing and verified downloads."""
import hashlib
import http.server
import os
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from bale_desktop import updater

PAYLOAD = b'#!/bin/sh\necho new bale\n' * 200


class Files(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', str(len(PAYLOAD)))
        self.end_headers()
        self.wfile.write(PAYLOAD)

    def log_message(self, *args):
        pass


def release(digest):
    return updater.Release({
        'tag_name': 'v9.0.0', 'html_url': 'https://github.com/x/y/releases/tag/v9.0.0', 'body': 'notes',
        'assets': [
            {'name': 'bale-desktop_9.0.0_all.deb', 'browser_download_url': 'http://unused/deb'},
            {'name': 'bale-desktop_9.0.0_x86_64.AppImage', 'browser_download_url': URL, 'digest': digest},
            {'name': 'bale-desktop_9.0.0_x86_64.AppImage.zsync', 'browser_download_url': 'http://unused/zsync'},
        ]})


class UpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global URL
        cls.server = socketserver.TCPServer(('127.0.0.1', 0), Files)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        URL = 'http://127.0.0.1:%d/new.AppImage' % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.dir = Path(self.work.name)
        self.good = 'sha256:' + hashlib.sha256(PAYLOAD).hexdigest()

    def tearDown(self):
        self.work.cleanup()

    def test_versions(self):
        self.assertEqual(updater.parse_version('v0.2.7'), (0, 2, 7, 0))
        self.assertTrue(updater.is_newer('v0.2.10', '0.2.9'))
        self.assertTrue(updater.is_newer('1.0', '0.9.9'))
        self.assertFalse(updater.is_newer('v0.2.7', '0.2.7'))
        self.assertFalse(updater.is_newer('v0.2.6', '0.2.7'))
        self.assertFalse(updater.is_newer('nightly', '0.2.7'), 'garbage tags never count as updates')

    def test_picks_the_appimage_not_the_zsync(self):
        asset = release(self.good).asset('_x86_64.AppImage')
        self.assertEqual(asset['name'], 'bale-desktop_9.0.0_x86_64.AppImage')
        self.assertIsNone(release(self.good).asset('_windows-setup.exe'))

    def test_download_verifies_sha256(self):
        seen = []
        part = updater.download(release(self.good).asset('_x86_64.AppImage'), self.dir / 'app', seen.append)
        self.assertEqual(part.read_bytes(), PAYLOAD)
        self.assertAlmostEqual(seen[-1], 1.0)

    def test_tampered_or_unsigned_download_is_refused(self):
        bad = release('sha256:' + '0' * 64).asset('_x86_64.AppImage')
        with self.assertRaises(ValueError):
            updater.download(bad, self.dir / 'app')
        self.assertEqual(list(self.dir.iterdir()), [], 'no partial file is left behind')
        with self.assertRaises(ValueError):
            updater.download(release(None).asset('_x86_64.AppImage'), self.dir / 'app')

    def test_appimage_replaced_in_place(self):
        current = self.dir / 'bale-desktop_0.2.7_x86_64.AppImage'
        current.write_bytes(b'old')
        with mock.patch.dict(os.environ, {'APPIMAGE': str(current)}):
            self.assertEqual(updater.running_appimage(), current)
            path = updater.install_appimage(release(self.good))
        self.assertEqual(path, current)
        self.assertEqual(current.read_bytes(), PAYLOAD)
        self.assertTrue(os.access(current, os.X_OK))
        with mock.patch.dict(os.environ, {'APPIMAGE': str(current)}):
            with self.assertRaises(ValueError):
                updater.install_appimage(release('sha256:' + '0' * 64))
        self.assertEqual(current.read_bytes(), PAYLOAD, 'a failed update keeps the working copy')

    def test_not_an_appimage(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(updater.running_appimage())

    def test_live_github_release_is_readable(self):
        if os.environ.get('BALE_OFFLINE'):
            self.skipTest('offline')
        try:
            latest = updater.fetch_latest(timeout=10)
        except OSError:
            self.skipTest('GitHub unreachable')
        self.assertTrue(updater.parse_version(latest.version))
        self.assertTrue(latest.asset('_x86_64.AppImage')['digest'].startswith('sha256:'))


if __name__ == '__main__':
    unittest.main()
