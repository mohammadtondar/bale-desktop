"""bale:// and ble.ir links handed to the app by the OS open inside it."""
from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
work = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='open-link-', ignore_cleanup_errors=True)
os.environ['XDG_DATA_HOME'] = str(Path(work.name) / 'data')
os.environ['XDG_CACHE_HOME'] = str(Path(work.name) / 'cache')
sys.path.insert(0, str(ROOT))
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib
from bale_desktop import app as app_module

opened = []


class OpenApp(app_module.BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.OpenLinkTest')

    def open_in_app(self, view, target):
        opened.append(target)

    def send_notification(self, *args):
        pass

    def do_open(self, files, n_files, hint):
        super().do_open(files, n_files, hint)
        GLib.timeout_add(500, self.quit)


app = OpenApp()
GLib.timeout_add_seconds(20, app.quit)
app.run([sys.argv[0], 'bale://join/AbC123', 'https://ble.ir/bale', 'https://example.com/'])
work.cleanup()
expected = ['https://web.bale.ai/join/AbC123', 'https://web.bale.ai/@bale']
ok = opened == expected and app.window is not None and app.window.get_visible()
print(('PASS: OS links open in the app: %s' if ok else 'FAIL: %s') % opened)
sys.exit(not ok)
