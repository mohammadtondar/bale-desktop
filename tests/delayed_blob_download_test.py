"""Regression: a Bale file that takes longer than ~1 s to fetch must still be saved.

Mirrors Bale's saveToDisk: a click starts the fetch, and only once it finishes
is the blob saved -- and only if navigator.userActivation.isActive is still
true. WebKit expires user activation after ~1 s, so slower files were dropped
without any error.
"""
from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
work = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='delayed-blob-test-', ignore_cleanup_errors=True)
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
from gi.repository import GLib
from bale_desktop.app import BaleApplication

errors = []
CLICK = """
const blob = new Blob(['slow bale payload\\n'.repeat(500)], {type: 'application/octet-stream'});
setTimeout(() => {
  if (!(navigator.userActivation?.isActive ?? true)) return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'slow-file.pdf'; a.style.display = 'none';
  document.body.appendChild(a); a.click();
}, 2500);
"""


class DelayedBlobApp(BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.DelayedBlobTest')
        self.notes = []

    def send_notification(self, key, notification):
        self.notes.append(key)

    def withdraw_notification(self, key):
        pass

    def show_download_error(self, message):
        errors.append('dialog: ' + message)

    def do_activate(self):
        super().do_activate()
        GLib.timeout_add(300, self.load)

    def load(self):
        self.view.load_html('<html><body>bale</body></html>', 'https://web.bale.ai/')
        GLib.timeout_add_seconds(2, self.press)
        return False

    def press(self):
        # evaluate_javascript runs as a user gesture, like the user's click.
        self.view.evaluate_javascript(CLICK, -1, None, None, None, None, None)
        GLib.timeout_add_seconds(7, self.inspect)
        return False

    def inspect(self):
        try:
            folder = downloads / 'bale'
            names = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
            assert names == ['slow-file.pdf'], 'slow download must be saved with its name: %s' % names
            assert set(self.notes) == {'download-complete'}, self.notes
            print('PASS: download finishing after activation expiry saved as', names)
        except Exception as error:
            errors.append(str(error))
        self.quit()
        return False


app = DelayedBlobApp()
GLib.timeout_add_seconds(25, lambda: (errors.append('timeout'), app.quit(), False)[-1])
app.run([sys.argv[0]])
work.cleanup()
if errors:
    print('FAIL: ' + '; '.join(errors))
sys.exit(bool(errors))
