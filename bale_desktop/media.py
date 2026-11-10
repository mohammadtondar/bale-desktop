"""Drag-and-drop and paste of photos, videos and files into Bale.

WebKitGTK does not give web pages the files of a drop (only their
file:// addresses as text) nor pasted images, so Bale Web never sees them.
This reads them on the app side and hands them to the page as real files
(see files.js). Only files the user actually dropped or pasted are served,
each once, at an unguessable bale-file:// address, and only to web.bale.ai.
"""
import json
from pathlib import Path
import secrets
import time
from urllib.parse import unquote, urlsplit

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Soup', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gdk, Gio, GLib, Gtk, Soup, WebKit2  # noqa: E402

SCHEME = 'bale-file'
ORIGIN = 'https://web.bale.ai'
MAX_FILES = 20
TOKEN_LIFETIME = 120
IMAGE_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')
TEXT_TARGETS = ('text/plain', 'text/plain;charset=utf-8', 'UTF8_STRING', 'STRING', 'TEXT')
ROOT = Path(__file__).resolve().parent


def mime_type(name):
    guess, _ = Gio.content_type_guess(name, None)
    return Gio.content_type_get_mime_type(guess) or 'application/octet-stream'


def local_files(uris):
    """Regular local files among file:// URIs (directories and others skipped)."""
    paths = []
    for uri in uris or []:
        try:
            parts = urlsplit(uri.strip())
        except ValueError:
            continue
        if parts.scheme != 'file' or parts.netloc not in ('', 'localhost'):
            continue
        path = Path(unquote(parts.path))
        if path.is_file():
            paths.append(path)
    return paths[:MAX_FILES]


def gnome_copied_files(data):
    """x-special/gnome-copied-files: 'copy' or 'cut', then one URI per line."""
    lines = (data or b'').decode('utf-8', 'replace').splitlines()
    return lines[1:] if lines and lines[0] in ('copy', 'cut') else lines


def paste_is_ctrl_v(event):
    """Ctrl+V or Shift+Insert, also with a Persian (or any non-Latin) layout active."""
    state = event.state & Gtk.accelerator_get_default_mod_mask()
    keyvals = {event.keyval}
    keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
    found, keyval, *_ = keymap.translate_keyboard_state(event.hardware_keycode, event.state, 0)
    if found:
        keyvals.add(keyval)   # the key's meaning in the first (usually Latin) layout
    if state == Gdk.ModifierType.CONTROL_MASK and keyvals & {Gdk.KEY_v, Gdk.KEY_V}:
        return True
    return state == Gdk.ModifierType.SHIFT_MASK and event.keyval in (Gdk.KEY_Insert, Gdk.KEY_KP_Insert)


class MediaBridge:
    def __init__(self, javascript):
        self.javascript = javascript          # app.javascript(view, code): runs only on web.bale.ai
        self.shared = {}                      # token -> (path or bytes, name, type, expires)
        self.script = (ROOT / 'files.js').read_text().strip()
        self.drag = {}                        # view -> (file paths of the drag in progress, time)
        self.drops = {}                       # view -> (x, y, time) of a drop awaiting its data

    # ---------- wiring ----------

    def attach(self, context, view):
        context.register_uri_scheme(SCHEME, self.serve)
        security = context.get_security_manager()
        security.register_uri_scheme_as_secure(SCHEME)
        security.register_uri_scheme_as_cors_enabled(SCHEME)
        view.connect('drag-data-received', self.drag_data_received)
        view.connect('drag-drop', self.drag_drop)
        view.connect('key-press-event', self.key_press)
        view.connect('context-menu', self.context_menu)

    # ---------- serving files to the page ----------

    def share(self, value, name, kind):
        now = time.monotonic()
        self.shared = {t: v for t, v in self.shared.items() if v[3] > now}
        token = secrets.token_urlsafe(24)
        self.shared[token] = (value, name, kind, now + TOKEN_LIFETIME)
        return {'url': '%s://%s' % (SCHEME, token), 'name': name, 'type': kind}

    def serve(self, request):
        token = urlsplit(request.get_uri()).netloc
        entry = self.shared.pop(token, None)      # each address works once
        if entry is None or entry[3] < time.monotonic():
            request.finish_error(GLib.Error.new_literal(Gio.io_error_quark(), 'not available',
                                                        Gio.IOErrorEnum.NOT_FOUND))
            return
        value, _, kind, _ = entry
        try:
            if isinstance(value, Path):
                file = Gio.File.new_for_path(str(value))
                size = file.query_info('standard::size', Gio.FileQueryInfoFlags.NONE, None).get_size()
                stream = file.read(None)
            else:
                size, stream = len(value), Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(value))
        except GLib.Error as error:
            request.finish_error(error)
            return
        response = WebKit2.URISchemeResponse.new(stream, size)
        response.set_content_type(kind)
        headers = Soup.MessageHeaders.new(Soup.MessageHeadersType.RESPONSE)
        headers.append('Access-Control-Allow-Origin', ORIGIN)
        response.set_http_headers(headers)
        request.finish_with_response(response)

    def deliver(self, view, event, files, x=0, y=0):
        if files:
            self.javascript(view, '(%s)(%s, %s, %d, %d)' % (self.script, json.dumps(event), json.dumps(files), x, y))

    def share_paths(self, paths):
        return [self.share(path, path.name, mime_type(path.name)) for path in paths]

    # ---------- drag and drop ----------

    def drag_data_received(self, view, context, x, y, data, info, when):
        # WebKit asks for the data while the pointer moves and on drop; keep
        # the latest, so it always belongs to the drag in progress.
        self.drag[view] = (local_files(data.get_uris()), time.monotonic())
        drop = self.drops.get(view)
        if drop and time.monotonic() - drop[2] < 5:
            GLib.timeout_add(50, self.finish_drop, view)

    def drag_drop(self, view, context, x, y, when):
        self.drops[view] = (x, y, time.monotonic())
        GLib.timeout_add(150, self.finish_drop, view)
        return False                              # WebKit still handles the drop itself

    def finish_drop(self, view):
        drop, drag = self.drops.get(view), self.drag.get(view)
        if drop and drag and drag[0] and abs(drag[1] - drop[2]) < 30:
            del self.drops[view]
            self.drag.pop(view, None)
            self.deliver(view, 'drop', self.share_paths(drag[0]), drop[0], drop[1])
        return False

    # ---------- paste ----------

    def clipboard_files(self):
        """Files to paste from the clipboard, or None to let WebKit paste normally."""
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        found, atoms = clipboard.wait_for_targets()
        if not found:
            return None
        targets = [atom.name() for atom in atoms]
        paths = []
        if 'text/uri-list' in targets:
            paths = local_files(clipboard.wait_for_uris())
        if not paths and 'x-special/gnome-copied-files' in targets:
            data = clipboard.wait_for_contents(Gdk.Atom.intern('x-special/gnome-copied-files', False))
            paths = local_files(gnome_copied_files(data.get_data() if data else b''))
        if paths:
            return self.share_paths(paths)
        # A screenshot or a copied picture. With text beside it (rich text from
        # an office app, say) the user most likely copied text: paste that.
        if any(target in TEXT_TARGETS for target in targets):
            return None
        kind = next((t for t in IMAGE_TYPES if t in targets), None)
        if kind is None:
            return None
        data = clipboard.wait_for_contents(Gdk.Atom.intern(kind, False))
        content = data.get_data() if data else None
        if not content:
            return None
        name = time.strftime('image-%Y%m%d-%H%M%S.') + kind.split('/')[1]
        return [self.share(bytes(content), name, kind)]

    def paste(self, view):
        """Paste clipboard files into Bale; False if there were none."""
        files = self.clipboard_files()
        if not files:
            return False
        self.deliver(view, 'paste', files)
        return True

    def key_press(self, view, event):
        return paste_is_ctrl_v(event) and self.paste(view)

    def context_menu(self, view, menu, event, hit):
        if not hit.context_is_editable():
            return False
        for position, item in enumerate(menu.get_items()):
            if item.get_stock_action() == WebKit2.ContextMenuAction.PASTE:
                action = Gio.SimpleAction.new('bale-paste', None)
                action.connect('activate', lambda *_: self.paste(view) or view.execute_editing_command(
                    WebKit2.EDITING_COMMAND_PASTE))
                menu.remove(item)
                menu.insert(WebKit2.ContextMenuItem.new_from_gaction(action, 'چسباندن', None), position)
                break
        return False
