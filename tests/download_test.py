"""Exercise the real WebKit download path against a local HTTP server."""
from pathlib import Path
import os
import sys
import tempfile
import threading
import http.server
import socketserver

ROOT = Path(__file__).resolve().parents[1]
work = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='download-test-', ignore_cleanup_errors=True)
work_path = Path(work.name)
downloads = work_path / 'Downloads'
downloads.mkdir()
os.environ['XDG_DATA_HOME'] = str(work_path / 'data')
os.environ['XDG_CACHE_HOME'] = str(work_path / 'cache')
config = work_path / 'config'
config.mkdir()
(config / 'user-dirs.dirs').write_text('XDG_DOWNLOAD_DIR="%s"\n' % downloads)
os.environ['XDG_CONFIG_HOME'] = str(config)

sys.path.insert(0, str(ROOT))
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib, Gtk, WebKit2
from bale_desktop.app import BaleApplication

payload = b'bale download fixture\n' * 2000

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/sample.txt':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Disposition', 'attachment; filename="bale-sample.txt"')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_error(404)
    def log_message(self, *args):
        pass

server = socketserver.TCPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_address[1]
errors = []

class DownloadApp(BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.DownloadTest')
        self.notes = []
        self.completed = []
        self.toast_shown = []

    def send_notification(self, key, notification):
        self.notes.append((key, notification))

    def withdraw_notification(self, key):
        pass

    def do_activate(self):
        super().do_activate()
        GLib.timeout_add(300, self.start_download)

    def start_download(self):
        self.view.download_uri('http://127.0.0.1:%d/sample.txt' % port)
        GLib.timeout_add_seconds(10, self.inspect)
        return False

    def inspect(self):
        try:
            target = downloads / 'bale' / 'bale-sample.txt'
            self.target = target
            files = sorted(str(p.relative_to(work_path)) for p in work_path.rglob('*') if p.is_file())
            assert target.exists(), 'File must land in Downloads/bale: %s | files=%s | notes=%s' % (target, files, self.notes)
            assert target.read_bytes() == payload, 'Downloaded content must match'
            assert set(k for k, _ in self.notes) == {'download-complete'}, self.notes
            assert not self.downloads, 'Download state must be cleaned up'
            assert self.completed == [str(target)], self.completed
            assert self.toast_shown, 'Completion toast must be shown'
            assert self.toast_shown[0] == 'ذخیره شد · bale-sample.txt', self.toast_shown
            # Second download must not overwrite; it gets a numeric suffix.
            self.again = False
            self.view.download_uri('http://127.0.0.1:%d/sample.txt' % port)
            GLib.timeout_add_seconds(6, self.inspect_second)
        except Exception as error:
            errors.append(str(error))
            self.quit()
        return False

    def inspect_second(self):
        try:
            names = sorted(p.name for p in (downloads / 'bale').iterdir())
            assert names == ['bale-sample (1).txt', 'bale-sample.txt'], names
            assert (downloads / 'bale' / 'bale-sample.txt').read_bytes() == payload
            assert self.completed == [str(self.target), str(downloads / 'bale' / 'bale-sample (1).txt')], self.completed
            print('PASS: real WebKit download to', downloads / 'bale', '| no overwrite | completion notification')
            self.quit()
        except Exception as error:
            errors.append(str(error))
            self.quit()
        return False

    def show_download_error(self, message):
        errors.append('unexpected dialog: ' + message)

    def show_download_done(self, path):
        self.completed.append(str(path))
        super().show_download_done(path)
        if self.toast.get_visible():
            self.toast_shown.append(self.toast_label.get_text())

app = DownloadApp()
GLib.timeout_add_seconds(30, lambda: (errors.append('download timed out'), app.quit(), False)[-1])
app.run([sys.argv[0]])
server.shutdown()
work.cleanup()
if errors:
    print('FAIL: ' + '; '.join(errors))
sys.exit(bool(errors))
