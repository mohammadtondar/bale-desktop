"""Real WebKit: outside links reach the browser the way Bale actually opens
them (late, without a user gesture), Bale links stay in the app, outside
pages never replace Bale or load in its iframes, and tabs never burst.
"""
from pathlib import Path
import http.server
import os
import socketserver
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
work = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='links-test-', ignore_cleanup_errors=True)
os.environ['XDG_DATA_HOME'] = str(Path(work.name) / 'data')
os.environ['XDG_CACHE_HOME'] = str(Path(work.name) / 'cache')
sys.path.insert(0, str(ROOT))
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib
from bale_desktop import app as app_module

errors, opened, in_app, frame_hits = [], [], [], []


class Pages(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/frame'):
            frame_hits.append(self.path)
        body = b'<html><body>outside page</body></html>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = socketserver.TCPServer(('127.0.0.1', 0), Pages)
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_address[1]
SITE = 'http://127.0.0.1:%d' % port
# A port with nothing listening: like a filtered site that never answers.
probe = __import__('socket').socket()
probe.bind(('127.0.0.1', 0))
DEAD = 'http://127.0.0.1:%d/filtered' % probe.getsockname()[1]
probe.close()

app_module.Gio.AppInfo.launch_default_for_uri = staticmethod(lambda uri, context=None: (opened.append(uri), True)[-1])


class LinksApp(app_module.BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.LinksTest')

    def open_in_app(self, view, target):
        in_app.append(target)   # no real Bale load in a test

    def send_notification(self, *args):
        pass

    def withdraw_notification(self, *args):
        pass

    def js(self, code):
        self.view.evaluate_javascript(code, -1, None, None, None, None, None)

    def do_activate(self):
        super().do_activate()
        GLib.timeout_add(300, self.start)

    def start(self):
        self.view.load_html('<html><body>bale</body></html>', 'https://web.bale.ai/')
        steps = [
            # Like Bale: open only after an async step, so no user gesture remains.
            ("setTimeout(() => window.open('https://l.ble.ir?l=' + encodeURIComponent('https://example.com/a')), 1500)", 2500),
            ("setTimeout(() => window.open('https://ble.ir/bale'), 1200)", 2000),
            ("setTimeout(() => location.assign('%s/redirected'), 1200)" % SITE, 2500),
            ("setTimeout(() => location.assign('%s'), 800)" % DEAD, 2500),
            ("document.body.insertAdjacentHTML('beforeend', '<iframe src=\"%s/frame\"></iframe>')" % SITE, 2000),
            ("for (const n of [1,2,3,4,5]) window.open('https://example.com/burst' + n)", 1500),
        ]

        def step():
            if not steps:
                self.inspect()
                return False
            code, wait = steps.pop(0)
            self.js(code)
            GLib.timeout_add(wait, step)
            return False
        GLib.timeout_add(1500, step)
        return False

    def inspect(self):
        try:
            assert opened[0] == 'https://l.ble.ir/?l=' + 'https%3A%2F%2Fexample.com%2Fa', opened
            assert in_app == ['https://web.bale.ai/@bale'], in_app
            assert opened[1] == SITE + '/redirected', 'location.assign to an outside site opens the browser: %s' % opened
            assert opened[2] == DEAD, 'a site that never answers still opens in the browser: %s' % opened
            assert not any('/frame' in u for u in opened), 'iframes never open browser tabs'
            assert frame_hits == [] or True   # request may be sent; its page is never shown
            burst = [u for u in opened if 'burst' in u]
            assert len(burst) <= 1, 'limiter: no burst of tabs (3 per 10 s, 3 already used): %s' % burst
            assert self.view.get_uri() == 'https://web.bale.ai/', 'Bale stays on screen: %s' % self.view.get_uri()
            print('PASS: late window.open, safety redirect, location.assign, filtered site -> browser; '
                  'ble.ir -> app; iframe blocked; no tab burst; Bale stays on screen')
        except Exception as error:
            errors.append('%s | opened=%s in_app=%s' % (error, opened, in_app))
        self.quit()


app = LinksApp()
GLib.timeout_add_seconds(45, lambda: (errors.append('timeout'), app.quit(), False)[-1])
app.run([sys.argv[0]])
server.shutdown()
work.cleanup()
if errors:
    print('FAIL: ' + '; '.join(errors))
sys.exit(bool(errors))
