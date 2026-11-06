"""GTK app: background/manual update checks reach the right prompt or message."""
from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
work = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='update-flow-', ignore_cleanup_errors=True)
os.environ['XDG_DATA_HOME'] = str(Path(work.name) / 'data')
os.environ['XDG_CACHE_HOME'] = str(Path(work.name) / 'cache')
sys.path.insert(0, str(ROOT))
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib
from bale_desktop import app as app_module, updater

errors, prompts, messages, notes = [], [], [], []
LATEST = {'version': '9.9.9'}


def fake_latest(timeout=20):
    return updater.Release({'tag_name': 'v' + LATEST['version'], 'html_url': 'https://example.invalid/r', 'assets': []})


updater.fetch_latest = fake_latest


class FlowApp(app_module.BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.UpdateFlowTest')

    def update_prompt(self, release):
        prompts.append(release.version)

    def show_message(self, text, kind=None):
        messages.append(text)

    def send_notification(self, key, notification):
        notes.append(key)

    def withdraw_notification(self, key):
        pass

    def do_activate(self):
        super().do_activate()
        steps = [
            lambda: self.check_updates(True),                               # manual, newer -> prompt
            lambda: self.save_settings(skipped_version='9.9.9'),
            lambda: self.check_updates(False),                              # skipped -> silent
            lambda: self.check_updates(True),                               # manual ignores skip
            lambda: LATEST.update(version=app_module.__version__),
            lambda: self.check_updates(True),                               # up to date -> message
            lambda: (LATEST.update(version='10.0.0'), self.hide_main()),
            lambda: self.check_updates(False),                              # hidden -> notification
            lambda: self.save_settings(auto_update=False),
            lambda: self.check_updates(False),                              # auto off -> nothing
            self.inspect,
        ]

        def run():
            if steps:
                steps.pop(0)()
                return True
            return False
        GLib.timeout_add(400, run)

    def inspect(self):
        try:
            assert prompts == ['9.9.9', '9.9.9'], prompts
            assert messages == ['آخرین نسخه را دارید (%s).' % app_module.__version__], messages
            assert notes == ['update-available'], notes
            assert self.available_release.version == '10.0.0'
            print('PASS: update prompt, skip, up-to-date message, background notification, auto-check off')
        except Exception as error:
            errors.append(str(error))
        self.quit()


app = FlowApp()
GLib.timeout_add_seconds(30, lambda: (errors.append('timeout'), app.quit(), False)[-1])
app.run([sys.argv[0]])
work.cleanup()
if errors:
    print('FAIL: ' + '; '.join(errors))
sys.exit(bool(errors))
