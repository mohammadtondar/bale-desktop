#!/usr/bin/python3
"""Compact GTK shell with isolated Bale accounts and ordinary notifications."""
import argparse
import json
from pathlib import Path
import signal
import sys
from urllib.parse import urlsplit

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2
from .profiles import ProfileStore

APP_ID = "io.github.baledesktop.App"
HOME_URL = "https://web.bale.ai/"
ROOT = Path(__file__).resolve().parent

CSS = b"""
headerbar.bale-header {
    background-image: none; background-color: #00b698; color: white;
    min-height: 32px; padding: 2px 6px; border: none; box-shadow: none;
}
.bale-header button, .bale-header combobox button {
    background-image: none; background-color: transparent; color: white;
    min-height: 24px; min-width: 24px; padding: 2px 5px;
    margin: 0; border: none; box-shadow: none; text-shadow: none;
}
.bale-header combobox, .bale-header box {
    min-height: 0; margin: 0; padding: 0;
}
.bale-header combobox arrow { min-height: 12px; min-width: 12px; }
.bale-header button:hover, .bale-header button:checked {
    background-color: rgba(255,255,255,0.18);
}
.bale-header .title { font-size: 14px; font-weight: bold; }
.bale-header .subtitle { font-size: 0; }
.bale-toast {
    background-color: rgba(0, 40, 33, 0.92); color: white;
    border-radius: 10px; padding: 6px 10px; margin: 12px;
}
.bale-toast label { color: white; font-size: 12px; }
.bale-toast button {
    background-image: none; background-color: transparent; color: #7ff0d2;
    border: none; box-shadow: none; min-height: 20px; padding: 0 4px;
    font-size: 12px; font-weight: bold;
}
.bale-toast button:hover { color: white; }
"""


def trusted_url(uri):
    try:
        url = urlsplit(uri)
        return (url.scheme == "https" and url.hostname == "web.bale.ai"
                and url.port in (None, 443) and not url.username and not url.password)
    except ValueError:
        return False


class DownloadJob:
    """Track one in-flight download so duplicate signals are ignored."""

    def __init__(self, path):
        self.path = path
        self.finished = False
        self.signals = []


class BaleApplication(Gtk.Application):
    def __init__(self, background=False, demo=False):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.start_background, self.demo = background, demo
        self.window = self.view = None
        self.sessions = {}
        self.notification_ids = {}
        self.downloads = set()
        self.held = False

    def do_startup(self):
        Gtk.Application.do_startup(self)
        GLib.set_application_name("بله دسکتاپ")
        Gtk.Window.set_default_icon_name(APP_ID)
        self.profiles = ProfileStore(Path(GLib.get_user_data_dir()) / 'bale-desktop',
                                     Path(GLib.get_user_cache_dir()) / 'bale-desktop')
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        for name, handler, parameter in [
            ('show', lambda *_: self.show_main(), None),
            ('quit', lambda *_: self.quit(), None),
            ('add-profile', lambda *_: self.profile_dialog(), None),
            ('rename-profile', lambda *_: self.profile_dialog(rename=True), None),
            ('open-profile', self.notification_action, GLib.VariantType.new('s')),
            ('show-downloads', lambda *_: self.open_downloads(), None),
        ]:
            action = Gio.SimpleAction.new(name, parameter)
            action.connect('activate', handler)
            self.add_action(action)
        self.set_accels_for_action('app.quit', ['<Primary>q'])
        self.set_accels_for_action('app.show', ['<Primary>m'])
        self.hold()
        self.held = True
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.quit_signal)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.quit_signal)

    def do_activate(self):
        if self.window:
            self.show_main()
            return
        self.build_window()
        if not self.start_background:
            self.show_main()

    def build_window(self):
        self.window = Gtk.ApplicationWindow(application=self, title='بله دسکتاپ')
        self.window.set_wmclass('bale-desktop', 'BaleDesktop')
        self.window.set_default_size(1120, 780)
        self.window.connect('delete-event', self.hide_main)
        self.header = Gtk.HeaderBar(title='بله', show_close_button=True)
        self.header.set_has_subtitle(False)
        self.header.get_style_context().add_class('bale-header')
        # Fixed-size raster themes may otherwise retain a much larger native icon.
        try:
            logo = Gtk.IconTheme.get_default().load_icon(APP_ID, 22, Gtk.IconLookupFlags.FORCE_SIZE)
            self.header_logo = Gtk.Image.new_from_pixbuf(logo)
        except GLib.Error:
            self.header_logo = Gtk.Image.new_from_icon_name('mail-unread-symbolic', Gtk.IconSize.MENU)
            self.header_logo.set_pixel_size(22)
        self.header_logo.set_valign(Gtk.Align.CENTER)
        self.header.pack_start(self.header_logo)
        reload_button = Gtk.Button.new_from_icon_name('view-refresh-symbolic', Gtk.IconSize.MENU)
        reload_button.set_tooltip_text('تازه‌سازی حساب فعلی')
        reload_button.connect('clicked', lambda *_: self.view.reload())
        self.header.pack_start(reload_button)
        self.status = Gtk.Image.new_from_icon_name('network-transmit-receive-symbolic', Gtk.IconSize.MENU)
        self.header.pack_start(self.status)
        self.profile_picker = Gtk.ComboBoxText()
        self.profile_picker.set_tooltip_text('تغییر پروفایل')
        self.profile_picker.set_direction(Gtk.TextDirection.RTL)
        renderer = self.profile_picker.get_cells()[0]
        renderer.set_property('ellipsize', 3)
        renderer.set_property('max-width-chars', 14)
        self.profile_picker.connect('changed', self.profile_changed)
        self.header.pack_end(self.profile_picker)
        add = Gtk.Button.new_from_icon_name('list-add-symbolic', Gtk.IconSize.MENU)
        add.set_tooltip_text('افزودن حساب')
        add.connect('clicked', lambda *_: self.profile_dialog())
        self.header.pack_end(add)
        menu = Gio.Menu()
        menu.append('افزودن حساب', 'app.add-profile')
        menu.append('تغییر نام پروفایل', 'app.rename-profile')
        menu.append('باز کردن پوشهٔ دانلودها', 'app.show-downloads')
        menu.append('خروج کامل', 'app.quit')
        menu_button = Gtk.MenuButton()
        menu_button.set_image(Gtk.Image.new_from_icon_name('open-menu-symbolic', Gtk.IconSize.MENU))
        menu_button.set_menu_model(menu)
        self.header.pack_end(menu_button)
        self.window.set_titlebar(self.header)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.overlay = Gtk.Overlay()
        self.overlay.add(self.stack)
        self.toast = self.build_toast()
        self.overlay.add_overlay(self.toast)
        self.toast.set_halign(Gtk.Align.END)
        self.toast.set_valign(Gtk.Align.END)
        self.window.add(self.overlay)
        self.toast_revision = 0
        for profile in self.profiles.items:
            self.ensure_session(profile['id'])
        self.refresh_profiles()
        self.switch_profile(self.profiles.active)
        self.create_tray()

    def refresh_profiles(self):
        self.updating_profiles = True
        self.profile_picker.remove_all()
        for item in self.profiles.items:
            self.profile_picker.append(item['id'], item['name'])
        self.profile_picker.set_active_id(self.profiles.active)
        self.updating_profiles = False

    def profile_changed(self, picker):
        if not getattr(self, 'updating_profiles', False) and picker.get_active_id():
            self.switch_profile(picker.get_active_id())

    def profile_dialog(self, rename=False):
        dialog = Gtk.Dialog(title='تغییر نام پروفایل' if rename else 'افزودن حساب',
                            transient_for=self.window, modal=True)
        dialog.add_buttons('انصراف', Gtk.ResponseType.CANCEL, 'ذخیره' if rename else 'ایجاد', Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(16)
        box.set_spacing(10)
        entry = Gtk.Entry()
        entry.set_direction(Gtk.TextDirection.RTL)
        entry.set_placeholder_text('نام پروفایل؛ مثلاً شخصی یا کاری')
        entry.set_max_length(32)
        entry.set_activates_default(True)
        if rename:
            entry.set_text(self.profiles.get(self.profiles.active)['name'])
        box.add(entry)
        error = Gtk.Label()
        error.set_direction(Gtk.TextDirection.RTL)
        box.add(error)
        dialog.show_all()
        entry.grab_focus()
        while dialog.run() == Gtk.ResponseType.OK:
            try:
                if rename:
                    self.profiles.rename(self.profiles.active, entry.get_text())
                    self.refresh_profiles()
                    self.window.set_title('بله — ' + self.profiles.get(self.profiles.active)['name'])
                else:
                    self.add_profile(entry.get_text())
                break
            except (ValueError, OSError) as problem:
                error.set_text(str(problem) if isinstance(problem, ValueError) else 'ذخیره نشد؛ فضای دیسک و دسترسی پوشه را بررسی کنید.')
        dialog.destroy()

    def add_profile(self, name):
        profile_id = self.profiles.add(name)
        self.ensure_session(profile_id)
        self.switch_profile(profile_id)
        self.refresh_profiles()
        return profile_id

    def switch_profile(self, profile_id):
        self.profiles.select(profile_id)
        self.ensure_session(profile_id)
        self.view = self.sessions[profile_id]['view']
        self.stack.set_visible_child_name(profile_id)
        if self.profile_picker.get_active_id() != profile_id:
            self.refresh_profiles()
        self.window.set_title('بله — ' + self.profiles.get(profile_id)['name'])
        self.status.set_tooltip_text(self.sessions[profile_id]['status'])
        self.update_background()

    def ensure_session(self, profile_id):
        if profile_id in self.sessions:
            return
        base, cache = self.profiles.storage(profile_id)
        for directory in (base, cache):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        data = WebKit2.WebsiteDataManager(base_data_directory=str(base), base_cache_directory=str(cache))
        context = WebKit2.WebContext.new_with_website_data_manager(data)
        context.get_cookie_manager().set_persistent_storage(str(base / 'cookies.sqlite'), WebKit2.CookiePersistentStorage.SQLITE)
        manager = WebKit2.UserContentManager()
        manager.register_script_message_handler('bale')
        manager.connect('script-message-received::bale', self.bridge_message, profile_id)
        manager.add_script(WebKit2.UserScript.new((ROOT / 'bridge.js').read_text(),
            WebKit2.UserContentInjectedFrames.TOP_FRAME, WebKit2.UserScriptInjectionTime.START,
            ['https://web.bale.ai/*'], None))
        view = WebKit2.WebView(web_context=context, user_content_manager=manager)
        self.sessions[profile_id] = {'view': view, 'context': context, 'data': data,
                                     'ready': False, 'status': 'در حال اتصال…', 'failed': False}
        view.get_settings().set_enable_media_stream(True)
        view.connect('decide-policy', self.navigation_policy)
        view.connect('permission-request', self.permission_request)
        view.connect('show-notification', self.native_notification)
        view.connect('load-changed', self.load_changed)
        view.connect('load-failed', self.load_failed)
        view.connect('web-process-terminated', self.process_terminated)
        view.connect('create', self.new_web_window)
        context.connect('download-started', self.download_started)
        self.stack.add_named(view, profile_id)
        view.show()
        if self.demo:
            view.load_html("<html lang='fa' dir='rtl'><body style='font-family:sans-serif;padding:48px;background:#effaf5;color:#075e50'><h1>بله</h1><p>پروفایل آزمایشی — بدون اتصال به حساب</p></body></html>", None)
        else:
            view.load_uri(HOME_URL)

    def profile_for_view(self, view):
        return next(key for key, session in self.sessions.items() if session['view'] == view)

    def javascript(self, view, script):
        if trusted_url(view.get_uri() or ''):
            view.evaluate_javascript(script, -1, None, None, None, None, None)

    def update_background(self):
        for key, session in self.sessions.items():
            background = not self.window.get_visible() or key != self.profiles.active
            self.javascript(session['view'], 'window.BaleDesktop?.background(%s)' % str(background).lower())

    def show_main(self):
        self.window.show_all()
        self.window.present()
        self.update_background()

    def hide_main(self, *_):
        self.window.hide()
        self.update_background()
        return True

    def create_tray(self):
        menu = Gtk.Menu()
        for label, action in [('نمایش بله', self.show_main), ('خروج کامل', self.quit)]:
            item = Gtk.MenuItem(label=label)
            item.connect('activate', lambda _, callback=action: callback())
            menu.append(item)
        menu.show_all()
        self.tray_menu = menu
        try:
            gi.require_version('AyatanaAppIndicator3', '0.1')
            from gi.repository import AyatanaAppIndicator3
            self.tray = AyatanaAppIndicator3.Indicator.new(APP_ID, APP_ID, AyatanaAppIndicator3.IndicatorCategory.COMMUNICATIONS)
            self.tray.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
            self.tray.set_menu(menu)
        except (ValueError, ImportError):
            self.tray = Gtk.StatusIcon.new_from_icon_name(APP_ID)
            self.tray.set_tooltip_text('بله • فعال در پس‌زمینه')
            self.tray.connect('activate', lambda *_: self.show_main())
            self.tray.connect('popup-menu', lambda _, button, time: menu.popup(None, None, None, None, button, time))

    def set_status(self, view, text):
        profile_id = self.profile_for_view(view)
        self.sessions[profile_id]['status'] = text
        if profile_id == self.profiles.active:
            self.status.set_tooltip_text(text)

    def bridge_message(self, manager, result, profile_id):
        session = self.sessions[profile_id]
        if not trusted_url(session['view'].get_uri() or ''):
            return
        try:
            item = json.loads(result.get_js_value().to_string())
            if item['kind'] == 'notification':
                if all(isinstance(item.get(k), str) for k in ('id', 'title', 'body')):
                    self.add_notification(profile_id, item)
            elif item['kind'] == 'ready':
                session['ready'] = True
                self.set_status(session['view'], 'متصل')
                self.update_background()
            elif item['kind'] == 'adapter-error':
                session['ready'] = False
                self.set_status(session['view'], item.get('error', 'دریافت اعلان نیاز به بررسی دارد.'))
        except (ValueError, KeyError, TypeError):
            pass

    def add_notification(self, profile_id, item):
        key = profile_id + ':' + item['id']
        if key in self.notification_ids:
            return
        self.notification_ids[key] = profile_id
        while len(self.notification_ids) > 200:
            old = next(iter(self.notification_ids))
            self.withdraw_notification(old)
            del self.notification_ids[old]
        name = self.profiles.get(profile_id)['name']
        note = Gio.Notification.new(name + ' · ' + item['title'][:160])
        note.set_body(item['body'][:500])
        note.set_icon(Gio.ThemedIcon.new(APP_ID))
        note.set_default_action_and_target('app.open-profile', GLib.Variant('s', profile_id))
        self.send_notification(key, note)

    def notification_action(self, action, target):
        profile_id = target.get_string()
        if any(p['id'] == profile_id for p in self.profiles.items):
            self.switch_profile(profile_id)
        self.show_main()

    def native_notification(self, view, notification):
        profile_id = self.profile_for_view(view)
        if not self.sessions[profile_id]['ready']:
            self.add_notification(profile_id, {'id': 'native-' + str(notification.get_id()),
                'title': notification.get_title() or 'بله', 'body': notification.get_body() or 'پیام جدید'})
        notification.close()
        return True

    def load_changed(self, view, event):
        session = self.sessions[self.profile_for_view(view)]
        if event == WebKit2.LoadEvent.STARTED:
            session.update(ready=False, failed=False)
            self.set_status(view, 'در حال اتصال…')
        elif event == WebKit2.LoadEvent.FINISHED and not session['ready'] and not session['failed']:
            self.set_status(view, 'آزمایشی' if self.demo else 'بله وب')

    def load_failed(self, view, event, uri, error):
        if error.matches(WebKit2.network_error_quark(), WebKit2.NetworkError.CANCELLED):
            return False
        self.sessions[self.profile_for_view(view)]['failed'] = True
        self.set_status(view, 'اتصال برقرار نشد؛ دوباره تازه‌سازی کنید.')
        return False

    def process_terminated(self, view, *_):
        self.sessions[self.profile_for_view(view)]['ready'] = False
        self.set_status(view, 'موتور وب متوقف شد؛ تازه‌سازی کنید.')
    def navigation_policy(self, view, decision, kind):
        if kind in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION, WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            action = decision.get_navigation_action()
            uri = action.get_request().get_uri()
            if self.demo and uri == "about:blank":
                return False
            if not trusted_url(uri):
                decision.ignore()
                if action.is_user_gesture() and urlsplit(uri).scheme in ("https", "http", "mailto", "tel"):
                    Gio.AppInfo.launch_default_for_uri(uri, None)
                return True
        return False

    def new_web_window(self, view, action):
        uri = action.get_request().get_uri()
        if action.is_user_gesture() and urlsplit(uri).scheme in ("https", "http"):
            Gio.AppInfo.launch_default_for_uri(uri, None)
        return None

    def permission_request(self, view, request):
        if isinstance(request, WebKit2.NotificationPermissionRequest) and trusted_url(view.get_uri() or ""):
            request.allow()
        elif isinstance(request, WebKit2.UserMediaPermissionRequest) and trusted_url(view.get_uri() or ""):
            dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO, text="بله — %s: اجازهٔ میکروفون / دوربین؟" % self.profiles.get(self.profile_for_view(view))["name"])
            response = dialog.run()
            dialog.destroy()
            request.allow() if response == Gtk.ResponseType.YES else request.deny()
        else:
            request.deny()
        return True

    def build_toast(self):
        toast = Gtk.Box(spacing=8)
        toast.get_style_context().add_class('bale-toast')
        toast.set_direction(Gtk.TextDirection.RTL)
        toast.set_no_show_all(True)
        self.toast_label = Gtk.Label(xalign=0)
        self.toast_label.set_ellipsize(3)
        self.toast_label.set_max_width_chars(40)
        toast.pack_start(self.toast_label, True, True, 0)
        button = Gtk.Button(label='نمایش')
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_tooltip_text('باز کردن پوشهٔ دانلودها')
        button.connect('clicked', lambda *_: self.open_downloads())
        toast.pack_end(button, False, False, 0)
        return toast

    def show_toast(self, message, seconds=6):
        """Small in-window notice; reuses one widget and resets its timer."""
        self.toast_revision += 1
        revision = self.toast_revision
        self.toast_label.set_text(message)
        # no-show-all keeps the toast out of window.show_all(); show it explicitly.
        self.toast.show()
        self.toast.show_all()

        def expire():
            if revision == self.toast_revision:
                self.toast.hide()
            return False

        GLib.timeout_add_seconds(seconds, expire)

    def hide_toast(self):
        self.toast_revision += 1
        self.toast.hide()

    def download_directory(self):
        # Honour XDG_DOWNLOAD_DIR (the user's localized Downloads folder).
        config = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        directory = Path(config) if config else Path.home() / 'Downloads'
        directory = directory / 'bale'
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            self.show_download_error('پوشهٔ دانلود ساخته نشد: %s' % error)
            return directory if directory.is_dir() else Path.home()
        return directory

    def unique_download_path(self, directory, suggested):
        name = Path(suggested).name or 'bale-file'
        path = directory / name
        if not path.exists():
            return path
        stem, suffix = path.stem, path.suffix
        for number in range(1, 10000):
            candidate = directory / f'{stem} ({number}){suffix}'
            if not candidate.exists():
                return candidate
        raise OSError('نام فایل تکراری است')

    def show_download_error(self, message):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text=message)
        dialog.run()
        dialog.destroy()

    def download_started(self, context, download):
        response = download.get_response()
        suggested = response.get_suggested_filename() if response else None
        if not suggested:
            suggested = Path(urlsplit(download.get_request().get_uri()).path).name or 'bale-file'
        directory = self.download_directory()
        try:
            destination = self.unique_download_path(directory, suggested)
        except OSError as error:
            self.show_download_error('نام فایل دانلود معتبر نیست: %s' % error)
            download.cancel()
            return
        state = DownloadJob(destination)

        def decide(download, filename):
            download.set_allow_overwrite(False)
            download.set_destination(destination.as_uri())
            return True

        def finish(download):
            if state.finished:
                return
            state.finished = True
            self.downloads.discard(state)
            for signal_id in state.signals:
                download.disconnect(signal_id)
            self.show_download_done(destination)

        def fail(download, error):
            if state.finished:
                return
            state.finished = True
            self.downloads.discard(state)
            for signal_id in state.signals:
                download.disconnect(signal_id)
            self.show_download_error('دانلود کامل نشد: %s' % error.message)

        state.signals = [download.connect('decide-destination', decide),
                         download.connect('finished', finish),
                         download.connect('failed', fail)]
        self.downloads.add(state)
        self.show_toast('در حال دانلود · %s' % destination.name, 4)

    def show_download_done(self, path):
        self.status.set_tooltip_text('دانلود شد: %s' % path)
        self.show_toast('ذخیره شد · %s' % path.name)
        note = Gio.Notification.new('فایل بله دانلود شد')
        note.set_body(path.name)
        note.set_icon(Gio.ThemedIcon.new('folder-download-symbolic'))
        note.set_default_action('app.show-downloads')
        self.send_notification('download-complete', note)

    def open_downloads(self):
        directory = self.download_directory()
        try:
            Gio.AppInfo.launch_default_for_uri(directory.as_uri(), None)
        except GLib.Error as error:
            self.show_download_error('پوشهٔ دانلود باز نشد: %s' % error)

    def quit_signal(self):
        self.quit()
        return False

    def do_shutdown(self):
        for state in list(self.downloads):
            state.finished = True
        self.downloads.clear()
        for key in self.notification_ids:
            self.withdraw_notification(key)
        if self.held:
            self.release()
        Gtk.Application.do_shutdown(self)


def main():
    parser = argparse.ArgumentParser(description='Bale Desktop for Ubuntu / Linux')
    parser.add_argument('--background', action='store_true', help='Start in the background')
    parser.add_argument('--demo', action='store_true', help='Offline preview; no account connection')
    args = parser.parse_args()
    return BaleApplication(args.background, args.demo).run([sys.argv[0]])


if __name__ == '__main__':
    raise SystemExit(main())
