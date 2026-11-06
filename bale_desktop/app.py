#!/usr/bin/python3
"""Compact GTK shell with isolated Bale accounts and ordinary notifications."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
from urllib.parse import urlsplit

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2
from . import __version__, links, updater
from .national import NationalProxy
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
.bale-header button.national { font-size: 12px; font-weight: bold; padding: 2px 7px; }
.bale-header button.national:checked {
    background-color: white; color: #00876f; border-radius: 6px;
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


def _url_is(uri, hosts):
    try:
        url = urlsplit(uri)
        return (url.scheme == "https" and url.hostname in hosts
                and url.port in (None, 443) and not url.username and not url.password)
    except ValueError:
        return False


def trusted_url(uri):
    """Origins allowed to render the app and receive the injected bridge."""
    return _url_is(uri, {"web.bale.ai"})


def navigation_allowed(uri):
    """Origins Bale itself renders or generates without asking the browser."""
    if uri.startswith(("blob:", "data:application/octet-stream")):
        return True
    return _url_is(uri, {"web.bale.ai", "assets.bale.ai"})


RENDERABLE_MIME_PREFIXES = ("text/", "image/", "audio/", "video/")
RENDERABLE_MIME_TYPES = {"application/pdf", "application/xhtml+xml"}


def response_is_download(response):
    """True when a response is a file to save, not a page to render."""
    if response is None:
        return False
    if response.get_suggested_filename():
        return True
    mime = (response.get_mime_type() or "").split(";")[0].strip().lower()
    if not mime:
        return False
    if mime in RENDERABLE_MIME_TYPES or mime.startswith(RENDERABLE_MIME_PREFIXES):
        return False
    return True


def memory_settings():
    """Make each web process release caches early instead of growing freely.

    The limit only sets when WebKit starts cleaning up (at 1/3 and 1/2 of it);
    the kill threshold stays disabled, so a busy chat is never terminated.
    """
    settings = WebKit2.MemoryPressureSettings.new()
    settings.set_memory_limit(512)
    return settings


class DownloadJob:
    """Track one in-flight download so duplicate signals are ignored."""

    def __init__(self, download):
        self.download = download
        self.path = None
        self.finished = False
        self.toasted = False
        self.signals = []


class BaleApplication(Gtk.Application):
    def __init__(self, background=False, demo=False):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.start_background, self.demo = background, demo
        self.window = self.view = None
        self.sessions = {}
        self.notification_ids = {}
        self.downloads = set()
        self.download_names = {}
        self.pending_navigations = set()
        self.open_limiter = links.OpenLimiter()
        self.bridge_source = None
        self.held = False
        self.national = None
        self.update_busy = False
        self.available_release = None
        self.restart_path = None

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
            ('about', lambda *_: self.about_dialog(), None),
            ('update-prompt', lambda *_: self.update_notification_clicked(), None),
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

    def do_open(self, files, n_files, hint):
        """bale://, ble:// and ble.ir links from other apps (or the command line)."""
        if not self.window:
            self.build_window()
        for item in files:
            target = links.bale_link_target(item.get_uri())
            if target:
                self.open_in_app(self.view, target)
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
        self.national_button = Gtk.ToggleButton(label='اینترنت ملی')
        self.national_button.get_style_context().add_class('national')
        self.national_button.set_tooltip_text(
            'اینترنت ملی: اتصال مستقیم بله با DNS ایران، بدون عبور از پروکسی فیلترشکن.\n'
            'وقتی فیلترشکن بله را مختل می‌کند روشن کنید.')
        self.national_button.set_active(self.load_settings().get('national') is True)
        self.national_button.connect('toggled', self.national_toggled)
        self.header.pack_start(self.national_button)
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
        menu.append('درباره بله دسکتاپ و به‌روزرسانی', 'app.about')
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
        self.start_update_checks()

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
        self.apply_network(data)
        context = WebKit2.WebContext(website_data_manager=data, memory_pressure_settings=memory_settings())
        # One single-page app per profile: no browser-sized memory cache needed.
        context.set_cache_model(WebKit2.CacheModel.DOCUMENT_BROWSER)
        context.get_cookie_manager().set_persistent_storage(str(base / 'cookies.sqlite'), WebKit2.CookiePersistentStorage.SQLITE)
        manager = WebKit2.UserContentManager()
        manager.register_script_message_handler('bale')
        manager.connect('script-message-received::bale', self.bridge_message, profile_id)
        if self.bridge_source is None:
            self.bridge_source = (ROOT / 'bridge.js').read_text()
        manager.add_script(WebKit2.UserScript.new(self.bridge_source,
            WebKit2.UserContentInjectedFrames.TOP_FRAME, WebKit2.UserScriptInjectionTime.START,
            ['https://web.bale.ai/*'], None))
        view = WebKit2.WebView(web_context=context, user_content_manager=manager)
        self.sessions[profile_id] = {'view': view, 'context': context, 'data': data,
                                     'ready': False, 'status': 'در حال اتصال…', 'failed': False}
        settings = view.get_settings()
        settings.set_enable_media_stream(True)
        settings.set_enable_page_cache(False)  # no back/forward history in a web app
        # Bale calls window.open after its async link check; let that reach the
        # policy above (which never creates a window) instead of being dropped.
        settings.set_javascript_can_open_windows_automatically(True)
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
            elif item['kind'] == 'download-name':
                uri, name = item.get('uri'), item.get('name')
                if isinstance(uri, str) and isinstance(name, str) and name.strip():
                    self.download_names[uri] = Path(name).name
                    if len(self.download_names) > 100:
                        del self.download_names[next(iter(self.download_names))]
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
        if uri in self.pending_navigations:
            # An outside link whose site did not answer (filtered, offline):
            # still hand it to the browser and keep Bale on screen.
            self.pending_navigations.discard(uri)
            self.open_external(view, uri)
            return True
        if error.matches(WebKit2.network_error_quark(), WebKit2.NetworkError.CANCELLED):
            return False
        self.sessions[self.profile_for_view(view)]['failed'] = True
        self.set_status(view, 'اتصال برقرار نشد؛ دوباره تازه‌سازی کنید.')
        return False

    def process_terminated(self, view, *_):
        self.sessions[self.profile_for_view(view)]['ready'] = False
        self.set_status(view, 'موتور وب متوقف شد؛ تازه‌سازی کنید.')

    def open_external(self, view, uri):
        """Hand a non-Bale link to the user's browser (or mail/phone app).

        Bale opens outside links only after its server-side link-safety check,
        long after the click, so there is no user gesture to require; only a
        Bale page may do it, and never as a burst of tabs."""
        if trusted_url(view.get_uri() or '') and links.external(uri) and self.open_limiter.allow(uri):
            try:
                Gio.AppInfo.launch_default_for_uri(uri, None)
            except GLib.Error as error:
                self.show_toast('لینک باز نشد: %s' % error.message, 5, downloads=False)

    def open_in_app(self, view, target):
        """Show a Bale link (ble.ir/…, bale://…) inside the app."""
        if view.get_uri() != target:
            view.load_uri(target)

    def navigation_policy(self, view, decision, kind):
        if kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri()
            scheme = urlsplit(uri).scheme
            if self.demo and uri == "about:blank":
                return False
            if navigation_allowed(uri) or scheme == "about":
                return False
            target = links.bale_link_target(uri)
            if target:
                decision.ignore()
                self.open_in_app(view, target)
                return True
            if scheme in ("mailto", "tel"):
                decision.ignore()
                self.open_external(view, uri)
                return True
            if scheme in ("https", "http"):
                # Main frame or iframe is only known once the server answers;
                # decide at the response (or at the failure, if it never does).
                self.pending_navigations.add(uri)
                return False
            decision.ignore()
            return True
        if kind == WebKit2.PolicyDecisionType.RESPONSE:
            uri = decision.get_request().get_uri()
            response = decision.get_response() if hasattr(decision, 'get_response') else None
            if trusted_url(uri) or uri.startswith(("blob:", "data:")):
                return False
            self.pending_navigations.discard(uri)
            main_frame = decision.is_main_frame_main_resource()
            # A Bale file opened in the main frame (even an image or PDF) must be
            # saved, not rendered in place of the app or silently dropped.
            if response_is_download(response) or (navigation_allowed(uri) and main_frame):
                decision.download()
                return True
            decision.ignore()   # outside pages never replace Bale, nor load in its iframes
            if main_frame:
                self.open_external(view, uri)
            return True
        if kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri()
            target = links.bale_link_target(uri)
            if target:
                decision.ignore()
                self.open_in_app(view, target)
                return True
            if not navigation_allowed(uri):
                decision.ignore()
                self.open_external(view, uri)
                return True
        return False

    def new_web_window(self, view, action):
        # window.open() from page script arrives here directly, without a
        # NEW_WINDOW_ACTION policy decision; route it the same way.
        uri = action.get_request().get_uri()
        target = links.bale_link_target(uri)
        if target:
            self.open_in_app(view, target)
        elif navigation_allowed(uri) and not trusted_url(uri):
            # Bale file links opened in a new tab: there is no tab, so save them.
            view.download_uri(uri)
        else:
            self.open_external(view, uri)
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
        self.toast_button = button
        return toast

    def show_toast(self, message, seconds=6, downloads=True):
        """Small in-window notice; reuses one widget and resets its timer."""
        self.toast_revision += 1
        revision = self.toast_revision
        self.toast_label.set_text(message)
        # no-show-all keeps the toast out of window.show_all(); show it explicitly.
        self.toast.show()
        self.toast.show_all()
        self.toast_button.set_visible(downloads)

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
        # WebKitGTK can emit download-started more than once for one transfer.
        if any(state.download is download for state in self.downloads):
            return
        request_uri = download.get_request().get_uri()
        bridged_name = self.download_names.pop(request_uri, None)
        state = DownloadJob(download)

        def decide(download, filename):
            # WebKit knows the real name here (Content-Disposition or the <a download>
            # attribute), which is more accurate than download-started's fallback.
            suggested = bridged_name or filename or self._response_filename(download)
            if not suggested:
                suggested = Path(urlsplit(request_uri).path).name or 'bale-file'
            directory = self.download_directory()
            try:
                destination = self.unique_download_path(directory, suggested)
            except OSError as error:
                self.show_download_error('نام فایل دانلود معتبر نیست: %s' % error)
                return False
            state.path = destination
            download.set_allow_overwrite(False)
            download.set_destination(destination.as_uri())
            if not state.toasted:
                state.toasted = True
                self.show_toast('در حال دانلود · %s' % destination.name, 4)
            return True

        def finish(download):
            if state.finished:
                return
            state.finished = True
            self.downloads.discard(state)
            for signal_id in state.signals:
                download.disconnect(signal_id)
            self.show_download_done(state.path or self.download_directory())

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

    @staticmethod
    def _response_filename(download):
        response = download.get_response()
        return response.get_suggested_filename() if response else None

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

    # ---------- اینترنت ملی ----------

    def settings_path(self):
        return Path(GLib.get_user_data_dir()) / 'bale-desktop' / 'settings.json'

    def load_settings(self):
        try:
            value = json.loads(self.settings_path().read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_settings(self, **changes):
        settings = self.load_settings()
        settings.update(changes)
        path = self.settings_path()
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(settings))
        temporary.replace(path)

    def national_enabled(self):
        button = getattr(self, 'national_button', None)
        return button.get_active() if button else self.load_settings().get('national') is True

    def apply_network(self, data):
        if self.national_enabled():
            if self.national is None:
                self.national = NationalProxy()
            data.set_network_proxy_settings(WebKit2.NetworkProxyMode.CUSTOM,
                                            WebKit2.NetworkProxySettings.new(self.national.url, None))
        else:
            # Back to the system settings, including a VPN's proxy.
            data.set_network_proxy_settings(WebKit2.NetworkProxyMode.DEFAULT, None)

    def national_toggled(self, button):
        enabled = button.get_active()
        try:
            self.save_settings(national=enabled)
        except OSError:
            pass  # still applies for this run
        for session in self.sessions.values():
            self.apply_network(session['data'])
            # Open connections (the message socket) keep their old route; reconnect.
            if not self.demo:
                session['view'].reload()
        self.show_toast('اینترنت ملی روشن شد · اتصال مستقیم با DNS ایران' if enabled
                        else 'اینترنت ملی خاموش شد · اتصال از تنظیمات سیستم', 4, downloads=False)

    # ---------- به‌روزرسانی ----------

    def auto_update_enabled(self):
        return self.load_settings().get('auto_update', True) is not False

    def start_update_checks(self):
        if self.demo:
            return
        GLib.timeout_add_seconds(30, lambda: (self.check_updates(False), False)[1])
        GLib.timeout_add_seconds(updater.CHECK_INTERVAL, lambda: (self.check_updates(False), True)[1])

    def check_updates(self, manual, status_label=None):
        """Ask GitHub for the latest release, off the main thread."""
        if (not manual and not self.auto_update_enabled()) or self.update_busy:
            return
        self.update_busy = True
        if status_label:
            status_label.set_text('در حال بررسی…')

        def work():
            try:
                result = updater.fetch_latest()
            except Exception as error:  # network, GitHub or JSON problems
                result = error
            GLib.idle_add(done, result)

        def done(result):
            self.update_busy = False
            if isinstance(result, Exception):
                if manual:
                    self.report_update(status_label, 'بررسی نشد؛ اتصال به گیت‌هاب برقرار نشد.')
                return False
            if not updater.is_newer(result.version):
                if manual:
                    self.report_update(status_label, 'آخرین نسخه را دارید (%s).' % __version__)
                return False
            self.available_release = result
            if status_label:
                status_label.set_text('نسخهٔ %s آمده است.' % result.version)
            if not manual and self.load_settings().get('skipped_version') == result.version:
                return False
            if manual or self.window.get_visible():
                self.update_prompt(result)
            else:
                note = Gio.Notification.new('نسخهٔ تازهٔ بله دسکتاپ: %s' % result.version)
                note.set_body('برای به‌روزرسانی کلیک کنید.')
                note.set_icon(Gio.ThemedIcon.new(APP_ID))
                note.set_default_action('app.update-prompt')
                self.send_notification('update-available', note)
            return False

        threading.Thread(target=work, daemon=True).start()

    def report_update(self, label, text):
        if label is not None:
            label.set_text(text)
        else:
            self.show_message(text)

    def show_message(self, text, kind=Gtk.MessageType.INFO):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=kind,
                                   buttons=Gtk.ButtonsType.OK, text=text)
        dialog.run()
        dialog.destroy()

    def update_notification_clicked(self):
        self.show_main()
        if self.available_release:
            self.update_prompt(self.available_release)

    def update_prompt(self, release):
        automatic = updater.running_appimage() is not None and release.asset('_x86_64.AppImage')
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.INFO,
                                   text='نسخهٔ %s بله دسکتاپ آمده است' % release.version)
        dialog.format_secondary_text(
            'نسخهٔ فعلی: %s\n\n' % __version__ +
            ('فایل جدید دریافت و بررسی می‌شود و بله دوباره باز می‌شود؛ حساب‌ها حفظ می‌شوند.' if automatic else
             'صفحهٔ دانلود نسخهٔ جدید در گیت‌هاب باز می‌شود.'))
        dialog.add_buttons('رد کردن این نسخه', 1, 'بعداً', Gtk.ResponseType.CANCEL,
                           'به‌روزرسانی' if automatic else 'دریافت از گیت‌هاب', Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == 1:
            self.save_settings(skipped_version=release.version)
        elif response == Gtk.ResponseType.OK:
            if automatic:
                self.install_update(release)
            else:
                Gio.AppInfo.launch_default_for_uri(release.page, None)

    def install_update(self, release):
        self.show_toast('در حال دریافت به‌روزرسانی…', 120, downloads=False)

        def progress(fraction):
            GLib.idle_add(self.toast_label.set_text, 'در حال دریافت به‌روزرسانی… %d٪' % (fraction * 100))

        def work():
            try:
                result = updater.install_appimage(release, progress)
            except Exception as error:
                result = error
            GLib.idle_add(done, result)

        def done(result):
            self.hide_toast()
            if isinstance(result, Exception):
                self.show_message('به‌روزرسانی انجام نشد: %s' % result, Gtk.MessageType.ERROR)
                return False
            dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                       buttons=Gtk.ButtonsType.YES_NO,
                                       text='بله دسکتاپ به نسخهٔ %s به‌روز شد. الان دوباره باز شود؟' % release.version)
            restart = dialog.run() == Gtk.ResponseType.YES
            dialog.destroy()
            if restart:
                self.restart_path = result
                self.quit()
            return False

        threading.Thread(target=work, daemon=True).start()

    def about_dialog(self):
        dialog = Gtk.AboutDialog(transient_for=self.window, modal=True)
        dialog.set_program_name('بله دسکتاپ')
        dialog.set_version(__version__)
        dialog.set_logo_icon_name(APP_ID)
        dialog.set_comments('برنامهٔ غیررسمی پیام‌رسان بله برای لینوکس و ویندوز.\n'
                            'ساختهٔ شرکت بله نیست؛ ورود و پیام‌ها مستقیم در سایت بله انجام می‌شود.')
        dialog.set_website('https://github.com/' + updater.REPO)
        dialog.set_website_label('صفحهٔ پروژه در گیت‌هاب')
        dialog.set_license_type(Gtk.License.MIT_X11)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        status = Gtk.Label()
        check = Gtk.Button(label='بررسی به‌روزرسانی')
        check.connect('clicked', lambda *_: self.check_updates(True, status))
        row.pack_start(check, False, False, 0)
        row.pack_start(status, False, False, 0)
        automatic = Gtk.CheckButton(label='بررسی خودکار به‌روزرسانی در پس‌زمینه', halign=Gtk.Align.CENTER)
        automatic.set_active(self.auto_update_enabled())
        automatic.connect('toggled', lambda button: self.save_settings(auto_update=button.get_active()))
        box.pack_start(row, False, False, 0)
        box.pack_start(automatic, False, False, 0)
        dialog.get_content_area().pack_end(box, False, False, 0)
        box.show_all()
        dialog.run()
        dialog.destroy()

    def do_shutdown(self):
        if self.national is not None:
            self.national.close()
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
    parser.add_argument('links', nargs='*', help='Bale links to open: bale://…, ble://…, https://ble.ir/…')
    args = parser.parse_args()
    app = BaleApplication(args.background, args.demo)
    code = app.run([sys.argv[0]] + [link for link in args.links if links.bale_link_target(link)])
    if app.restart_path:
        # Start the updated AppImage in place of this process.
        os.execv(str(app.restart_path), [str(app.restart_path)])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
