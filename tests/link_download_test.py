"""Regression: clicking a file link must download it, not navigate or get cancelled.

Bale serves attachments by navigating the view to the file URL, so a policy that
ignores unknown navigation actions silently turns every download into a no-op.
"""
from pathlib import Path
import os
import sys
import tempfile
import threading
import http.server
import socketserver

ROOT = Path(__file__).resolve().parents[1]
work = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='link-test-', ignore_cleanup_errors=True)
work_path = Path(work.name)
downloads = work_path / 'Downloads'
downloads.mkdir()
config = work_path / 'config'
config.mkdir()
(config / 'user-dirs.dirs').write_text('XDG_DOWNLOAD_DIR="%s"\n' % downloads)
os.environ['XDG_DATA_HOME'] = str(work_path / 'data')
os.environ['XDG_CACHE_HOME'] = str(work_path / 'cache')
os.environ['XDG_CONFIG_HOME'] = str(config)

sys.path.insert(0, str(ROOT))
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib, Gtk, WebKit2
from bale_desktop import app as app_module
from bale_desktop.app import BaleApplication

payload = b'bale attachment fixture\n' * 1000
errors = []
opened = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/file.bin':
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition', 'attachment; filename="report.bin"')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == '/page':
            body = b'<html><body>external page</body></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


server = socketserver.TCPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_address[1]

# External links must still be handed to the user's browser, not followed in-app.
app_module.Gio.AppInfo.launch_default_for_uri = staticmethod(
    lambda uri, context=None: (opened.append(uri), True)[-1])


class LinkApp(BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.LinkTest')
        self.notes = []
        self.completed = []

    def send_notification(self, key, notification):
        self.notes.append(key)

    def withdraw_notification(self, key):
        pass

    def show_download_error(self, message):
        errors.append('dialog: ' + message)

    def show_download_done(self, path):
        self.completed.append(str(path))
        super().show_download_done(path)

    def do_activate(self):
        super().do_activate()
        GLib.timeout_add(300, self.go)

    def go(self):
        html = ('<html><body>'
                '<a id="file" href="http://127.0.0.1:%d/file.bin">file</a>'
                '<a id="page" href="http://127.0.0.1:%d/page">page</a>'
                '</body></html>') % (port, port)
        self.view.load_html(html, 'https://web.bale.ai/')
        GLib.timeout_add_seconds(3, self.click_file)
        return False

    def click_file(self):
        self.view.evaluate_javascript('document.getElementById("file").click()',
                                      -1, None, None, None, None, None)
        GLib.timeout_add_seconds(3, self.click_page)
        return False

    def click_page(self):
        self.view.evaluate_javascript('document.getElementById("page").click()',
                                      -1, None, None, None, None, None)
        GLib.timeout_add_seconds(4, self.inspect)
        return False

    def inspect(self):
        try:
            folder = downloads / 'bale'
            names = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
            assert names == ['report.bin'], 'Attachment must be saved: %s' % names
            assert (folder / 'report.bin').read_bytes() == payload, 'Content must match'
            assert self.completed == [str(folder / 'report.bin')], self.completed
            assert self.notes == ['download-complete'], self.notes
            assert self.view.get_uri() == 'https://web.bale.ai/', self.view.get_uri()
            assert opened == ['http://127.0.0.1:%d/page' % port], opened
            print('PASS: clicked attachment saved; external page opened in browser')
            self.quit()
        except Exception as error:
            errors.append(str(error))
            self.quit()
        return False


app = LinkApp()
GLib.timeout_add_seconds(40, lambda: (errors.append('policy test timed out'), app.quit(), False)[-1])
app.run([sys.argv[0]])
server.shutdown()
work.cleanup()
if errors:
    print('FAIL: ' + '; '.join(errors))
sys.exit(bool(errors))
