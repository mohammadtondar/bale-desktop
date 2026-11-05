"""Real WebKit: with «اینترنت ملی» on, pages resolve through Iranian DNS via the
local proxy; switching it off returns to the system route at once.

The host name below exists only in the fake DNS server, so it loads only if
WebKit's traffic really goes through the national proxy.
"""
from pathlib import Path
import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
work = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='national-test-', ignore_cleanup_errors=True)
work_path = Path(work.name)
os.environ['XDG_DATA_HOME'] = str(work_path / 'data')
os.environ['XDG_CACHE_HOME'] = str(work_path / 'cache')
(work_path / 'data' / 'bale-desktop').mkdir(parents=True)
(work_path / 'data' / 'bale-desktop' / 'settings.json').write_text('{"national": true}')

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib
from bale_desktop.app import BaleApplication
from bale_desktop.national import NationalProxy, Resolver
from fake_dns import FakeDNS

errors, hits = [], []


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        hits.append(self.headers['Host'])
        body = b'<html><head><title>national-ok</title></head><body>ok</body></html>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


web = socketserver.TCPServer(('127.0.0.1', 0), Page)
threading.Thread(target=web.serve_forever, daemon=True).start()
port = web.server_address[1]
dns = FakeDNS({'web.bale.test': '127.0.0.1'})
URL = 'http://web.bale.test:%d/page' % port


class NationalApp(BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.NationalTest')
        self.national = NationalProxy(Resolver(['127.0.0.1'], port=dns.port, timeout=0.5), allowed_ports=[port])
        self.failed = []

    def navigation_policy(self, *args):
        return False   # this test is about the network route, not the link policy

    def send_notification(self, *args):
        pass

    def withdraw_notification(self, *args):
        pass

    def do_activate(self):
        super().do_activate()
        self.view.connect('load-failed', lambda view, event, uri, error: self.failed.append(uri) and False)
        GLib.timeout_add(500, self.load_on)

    def load_on(self):
        assert self.national_button.get_active(), 'saved setting must turn the button on'
        self.view.load_uri(URL)
        GLib.timeout_add_seconds(4, self.check_on)
        return False

    def check_on(self):
        try:
            assert hits == ['web.bale.test:%d' % port], 'page must load via Iranian DNS proxy: %s' % hits
            assert self.view.get_title() == 'national-ok', self.view.get_title()
            assert 'web.bale.test' in dns.queries, dns.queries
            self.national_button.set_active(False)   # user turns it off
            settings = json.loads((work_path / 'data' / 'bale-desktop' / 'settings.json').read_text())
            assert settings == {'national': False}, settings
            assert self.toast.get_visible() and 'خاموش' in self.toast_label.get_text()
            assert not self.toast_button.get_visible(), 'no downloads button on this toast'
            self.view.load_uri(URL + '?off')
            GLib.timeout_add_seconds(5, self.check_off)
        except Exception as error:
            errors.append(str(error))
            self.quit()
        return False

    def check_off(self):
        try:
            assert len(hits) == 1, 'off: system route cannot resolve the fake name: %s' % hits
            assert any(u.endswith('?off') for u in self.failed), self.failed
            print('PASS: national proxy routes WebKit through Iranian DNS; off restores system route')
        except Exception as error:
            errors.append(str(error))
        self.quit()
        return False


app = NationalApp()
GLib.timeout_add_seconds(30, lambda: (errors.append('timeout'), app.quit(), False)[-1])
app.run([sys.argv[0]])
web.shutdown()
dns.close()
work.cleanup()
if errors:
    print('FAIL: ' + '; '.join(errors))
sys.exit(bool(errors))
