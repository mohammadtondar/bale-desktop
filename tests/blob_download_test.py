"""Prove blob: downloads from the Bale web app are not blocked by the policy."""
from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
work = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='blob-test-', ignore_cleanup_errors=True)
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

errors = []
# Simulate the previous, too-strict policy for one run.
STRICT = os.environ.get('STRICT_POLICY') == '1'
if STRICT:
    app_module.navigation_allowed = lambda uri: app_module._url_is(uri, {'web.bale.ai'})

PAGE = """
<html><body><script>
const blob = new Blob(['bale blob payload\\n'.repeat(500)], {type: 'application/octet-stream'});
const url = URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url; a.download = 'bale-blob.txt';
document.body.appendChild(a); a.click();
</script></body></html>
"""

class BlobApp(BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.BlobTest')
        self.notes = []

    def send_notification(self, key, notification):
        self.notes.append(key)

    def withdraw_notification(self, key):
        pass

    def show_download_error(self, message):
        errors.append('dialog: ' + message)

    def do_activate(self):
        super().do_activate()
        GLib.timeout_add(300, self.click)

    def click(self):
        self.view.load_html(PAGE, 'https://web.bale.ai/')
        GLib.timeout_add_seconds(8, self.inspect)
        return False

    def inspect(self):
        try:
            folder = downloads / 'bale'
            names = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
            assert names, 'blob download produced no file'
            assert self.notes and set(self.notes) == {'download-complete'}, self.notes
            print('PASS: blob download saved as', names)
            self.quit()
        except Exception as error:
            errors.append(str(error))
            self.quit()
        return False

app = BlobApp()
GLib.timeout_add_seconds(25, lambda: (errors.append('timeout'), app.quit(), False)[-1])
app.run([sys.argv[0]])
work.cleanup()
if errors:
    print('FAIL: ' + '; '.join(errors))
sys.exit(bool(errors))
