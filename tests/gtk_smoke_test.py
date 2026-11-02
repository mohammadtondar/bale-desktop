"""Exercise real WebKit storage separation and GTK profile routing, offline."""
from pathlib import Path
import os
import sys
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
profile_dir = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='profile-test-', ignore_cleanup_errors=True)
os.environ['XDG_DATA_HOME'] = str(Path(profile_dir.name) / 'data')
os.environ['XDG_CACHE_HOME'] = str(Path(profile_dir.name) / 'cache')
# Reproduce the installed, oversized raster icon instead of testing a missing icon.
theme = Path(os.environ['XDG_DATA_HOME']) / 'icons/hicolor'
icons = theme / '512x512/apps'
icons.mkdir(parents=True)
(theme / 'index.theme').write_text('[Icon Theme]\nName=Hicolor\nDirectories=512x512/apps\n\n[512x512/apps]\nSize=512\nType=Fixed\nContext=Applications\n')
shutil.copy2(ROOT / 'packaging/io.github.baledesktop.App.png', icons)
from bale_desktop.app import BaleApplication, GLib, WebKit2

errors = []


class SmokeApplication(BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.Smoke')
        self.notes = []

    def send_notification(self, key, notification):
        self.notes.append((key, notification))

    def withdraw_notification(self, key):
        pass

    def do_activate(self):
        super().do_activate()
        self.work = self.add_profile('کاری')
        self.personal = self.add_profile('شخصی')
        self.loaded = set()
        for key, session in self.sessions.items():
            session['view'].connect('load-changed', self.loaded_page, key)
            session['view'].load_html('<html><body>Offline storage fixture</body></html>', 'https://web.bale.ai/')

    def loaded_page(self, view, event, key):
        if event == WebKit2.LoadEvent.FINISHED:
            self.loaded.add(key)
            if len(self.loaded) == 3:
                GLib.idle_add(self.check_profiles)

    def check_profiles(self):
        try:
            assert self.window.get_visible()
            assert len(self.sessions) == 3
            assert self.header.get_subtitle() is None
            logo = self.header_logo.get_pixbuf()
            assert logo and logo.get_width() == 22 and logo.get_height() == 22, 'Installed logo must be scaled to 22px'
            assert self.header.get_allocated_height() <= 44, 'Header height: ' + str(self.header.get_allocated_height()) + '; children: ' + str([(type(w).__name__, w.get_allocated_height(), w.get_preferred_height()) for w in self.header.get_children()])
            assert isinstance(self.window.get_child(), __import__('gi.repository', fromlist=['Gtk']).Gtk.Overlay), 'Overlay hosts the compact toast'
            assert self.window.get_child().get_child() == self.stack, 'No extra status strip'
            assert not self.lookup_action('reply'), 'Reply action completely removed'
            managers = [s['data'] for s in self.sessions.values()]
            paths = [m.get_base_data_directory() for m in managers]
            assert len(set(paths)) == 3, 'Profiles use different storage directories'
            self.original_work = self.sessions[self.work]['view']
            self.switch_profile('default')
            assert self.view == self.sessions['default']['view']
            self.switch_profile(self.work)
            assert self.view == self.original_work, 'Switch reuses session without logout'
            assert self.stack.get_visible_child_name() == self.work
            self.hide_main()
            assert not self.window.get_visible() and self.held, 'Closing keeps all accounts running'
            self.add_notification(self.personal, {'id': 'same', 'title': 'Message', 'body': 'Hello'})
            self.add_notification(self.work, {'id': 'same', 'title': 'Message', 'body': 'Hello'})
            assert len(self.notes) == 2, 'Notification IDs are scoped to account'
            self.notification_action(None, GLib.Variant('s', self.personal))
            assert self.profiles.active == self.personal and self.window.get_visible()
            self.results = {}
            self.evaluations = 0
            for key, session in self.sessions.items():
                value = 'account_' + key
                script = "localStorage.setItem('account', '%s'); document.cookie='account=%s; path=/; secure'; 'ok'" % (value, value)
                session['view'].evaluate_javascript(script, -1, None, None, None, self.written, key)
        except Exception as error:
            errors.append(str(error))
            self.quit()
        return False

    def written(self, view, result, key):
        try:
            view.evaluate_javascript_finish(result)
            self.evaluations += 1
            if self.evaluations == 3:
                for key, session in self.sessions.items():
                    session['view'].evaluate_javascript("JSON.stringify([localStorage.getItem('account'),document.cookie])", -1,
                                                       None, None, None, self.read_storage, key)
        except Exception as error:
            errors.append(str(error))
            self.quit()

    def read_storage(self, view, result, key):
        import json
        try:
            value = json.loads(view.evaluate_javascript_finish(result).to_string())
            assert value[0] == 'account_' + key, 'Local storage must not leak between accounts'
            assert value[1] == 'account=account_' + key, 'Cookies must not leak between accounts'
            self.results[key] = value
            if len(self.results) == 3:
                assert len({v[0] for v in self.results.values()}) == 3
                print('PASS: header %spx with 22px installed logo; three isolated sessions, profile switch, background and notifications' % self.header.get_allocated_height())
                self.quit()
        except Exception as error:
            errors.append(str(error))
            self.quit()


app = SmokeApplication()
GLib.timeout_add_seconds(20, lambda: (errors.append('App test timed out'), app.quit(), False)[-1])
app.run([sys.argv[0]])
if errors:
    print('FAIL: ' + '; '.join(errors))
profile_dir.cleanup()
sys.exit(bool(errors))
