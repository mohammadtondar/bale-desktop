"""Real input on an isolated X display: dropping a file and pasting an image,
a copied video and plain text all reach Bale's own drop/paste logic.

Runs its own Xwayland display (a small window appears briefly), so neither
the real clipboard nor the real mouse is touched.
"""
from pathlib import Path
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]

if not os.environ.get('BALE_MEDIA_DISPLAY'):
    if not shutil.which('Xwayland') or not shutil.which('xclip'):
        print('SKIP: needs Xwayland and xclip')
        sys.exit(0)
    number = next(n for n in range(90, 200) if not Path('/tmp/.X11-unix/X%d' % n).exists())
    server = subprocess.Popen(['Xwayland', ':%d' % number, '-geometry', '700x450', '-noreset'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    env = dict(os.environ, DISPLAY=':%d' % number, GDK_BACKEND='x11', WAYLAND_DISPLAY='',
               BALE_MEDIA_DISPLAY='1')
    try:
        code = subprocess.run([sys.executable, __file__], env=env, timeout=120).returncode
    finally:
        server.terminate()
    sys.exit(code)

work = tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='media-test-', ignore_cleanup_errors=True)
work_path = Path(work.name)
os.environ['XDG_DATA_HOME'] = str(work_path / 'data')
os.environ['XDG_CACHE_HOME'] = str(work_path / 'cache')
photo = work_path / 'سفر photo.png'
photo.write_bytes(b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 40)
video = work_path / 'clip.mp4'
video.write_bytes(b'\x00\x00\x00\x18ftypmp42' + b'v' * 5000)
shot = work_path / 'shot.png'
shot.write_bytes(b'\x89PNG\r\n\x1a\nSCREENSHOT' * 50)

sys.path.insert(0, str(ROOT))
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gdk, GLib, Gtk, WebKit2
from bale_desktop import app as app_module
from bale_desktop.media import paste_is_ctrl_v

errors, seen = [], []

# Bale Web's own logic (MainRoutes / 1327 chunks), reduced to what matters here:
# the chat area's onDrop reads dataTransfer.files; the composer's paste
# listener reads clipboardData.items via webkitGetAsEntry/getAsFile and keeps
# only these types while the composer is focused.
FAKE_BALE = """<html><body style="margin:0">
<div id=chat style="height:330px;background:#efe">chat</div>
<div id=composer contenteditable=true style="height:60px;background:#fff">x</div>
<script>
const report = (how, files) => Promise.all(files.map(async f =>
  f.name + '|' + f.type + '|' + f.size + '|' + new Uint8Array(await f.slice(0, 4).arrayBuffer()).join(','))
).then(list => webkit.messageHandlers.bale.postMessage(JSON.stringify({kind: 'test', how, list})));
chat.addEventListener('dragover', e => e.preventDefault());
chat.addEventListener('drop', e => { e.preventDefault();
  if (e.dataTransfer.files && e.dataTransfer.files.length > 0) report('drop', [...e.dataTransfer.files]); });
const allowed = ["image/png","image/jpeg","image/gif","image/webp","video/mp4","video/webm"];
async function getFiles(ev) {
  const out = [], items = ev.clipboardData.items;
  for (let i = 0; i < items.length; i++) { const it = items[i];
    if (it.kind !== 'file') continue;
    const entry = it.webkitGetAsEntry() || it.getAsFile();
    const fallback = it.getAsFile();
    out.push(entry instanceof File ? entry : await new Promise(r => entry.file(f => r(f), () => r(fallback))));
  }
  return out;
}
document.addEventListener('paste', ev => {
  if (!ev.clipboardData || document.activeElement !== composer) return;
  getFiles(ev).then(files => { files = files.filter(f => allowed.includes(f.type));
    if (files.length) { ev.preventDefault(); report('paste', files); } });
});
composer.addEventListener('input', () => webkit.messageHandlers.bale.postMessage(
  JSON.stringify({kind: 'test', how: 'text', list: [composer.textContent]})));
</script></body></html>"""

x11 = ctypes.CDLL('libX11.so.6')
xtest = ctypes.CDLL('libXtst.so.6')
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XStringToKeysym.restype = ctypes.c_ulong
x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
display = ctypes.c_void_p(x11.XOpenDisplay(None))


def move(x, y):
    xtest.XTestFakeMotionEvent(display, -1, x, y, 0)
    x11.XFlush(display)


def button(down):
    xtest.XTestFakeButtonEvent(display, 1, down, 0)
    x11.XFlush(display)


def key(name, down):
    code = x11.XKeysymToKeycode(display, x11.XStringToKeysym(name.encode()))
    xtest.XTestFakeKeyEvent(display, code, down, 0)
    x11.XFlush(display)


def ctrl_v():
    """A real GTK key event for Ctrl+V, delivered to the web view like a key press.

    (Xwayland ignores modifier keys simulated with XTEST, so they cannot be
    typed on the test display.)"""
    done = threading.Event()

    def send():
        view = app.view
        keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
        seat = Gdk.Display.get_default().get_default_seat()
        for kind in (Gdk.EventType.KEY_PRESS, Gdk.EventType.KEY_RELEASE):
            event = Gdk.Event.new(kind)
            event.window = view.get_window()
            event.send_event = True
            event.time = Gtk.get_current_event_time()
            event.keyval = Gdk.KEY_v
            event.hardware_keycode = keymap.get_entries_for_keyval(Gdk.KEY_v)[1][0].keycode
            event.state = Gdk.ModifierType.CONTROL_MASK
            event.set_device(seat.get_keyboard())
            view.event(event)
        done.set()
        return False
    GLib.idle_add(send)
    done.wait(5)


def clip(kind, path=None, text=None):
    args = ['xclip', '-quiet', '-selection', 'clipboard', '-t', kind]
    process = subprocess.Popen(args + (['-i', str(path)] if path else []), stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if text is not None:
        process.stdin.write(text.encode())
    process.stdin.close()
    time.sleep(0.5)
    return process


class MediaApp(app_module.BaleApplication):
    def __init__(self):
        super().__init__(demo=True)
        self.set_application_id('io.github.baledesktop.MediaTest')

    def send_notification(self, *args):
        pass

    def withdraw_notification(self, *args):
        pass

    def bridge_message(self, manager, result, profile_id):
        value = result.get_js_value().to_string()
        if '"test"' in value:
            seen.append(__import__('json').loads(value))
        else:
            super().bridge_message(manager, result, profile_id)

    def do_activate(self):
        super().do_activate()
        self.window.move(0, 0)
        self.window.resize(700, 450)
        source = Gtk.Window(title='source')
        source.set_default_size(120, 120)
        source.move(560, 300)
        handle = Gtk.Button(label='photo')
        handle.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [Gtk.TargetEntry.new('text/uri-list', 0, 0)],
                               Gdk.DragAction.COPY)
        handle.connect('drag-data-get', lambda w, c, sel, i, t: sel.set_uris([photo.as_uri()]))
        source.add(handle)
        source.show_all()
        self.source = source
        self.view.load_html(FAKE_BALE, 'https://web.bale.ai/')
        threading.Thread(target=self.drive, daemon=True).start()

    def wait(self, count, timeout=6):
        end = time.time() + timeout
        while len(seen) < count and time.time() < end:
            time.sleep(0.1)

    def drive(self):
        clips = []
        try:
            time.sleep(3)
            # 1. Drag the photo from another window onto the chat area.
            move(620, 360); time.sleep(0.3); button(1); time.sleep(0.3)
            for step in range(40):
                move(620 - step * 12, 360 - step * 6); time.sleep(0.03)
            time.sleep(0.5); move(150, 120); time.sleep(0.6); button(0)
            self.wait(1)
            # Focus the composer like a user would.
            GLib.idle_add(lambda: self.view.grab_focus() or False)
            self.view.evaluate_javascript('composer.focus()', -1, None, None, None, None, None)
            time.sleep(0.5)
            # 2. A screenshot on the clipboard (image only, no text).
            clips.append(clip('image/png', shot)); ctrl_v(); self.wait(2)
            # 3. A video copied in the file manager.
            clips.append(clip('text/uri-list', text=video.as_uri() + '\r\n')); ctrl_v(); self.wait(3)
            # 4. Plain text still pastes as text.
            # (Filled like any GTK app does, with all text formats.)
            GLib.idle_add(lambda: Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text('سلام', -1) or False)
            time.sleep(0.5); ctrl_v(); self.wait(4)
        finally:
            for process in clips:
                process.terminate()
            GLib.idle_add(self.inspect)

    def inspect(self):
        try:
            png = '137,80,78,71'
            assert seen[0] == {'kind': 'test', 'how': 'drop', 'list': ['%s|image/png|%d|%s' % (photo.name, photo.stat().st_size, png)]}, seen
            assert seen[1]['how'] == 'paste' and seen[1]['list'][0].startswith('image-') \
                and seen[1]['list'][0].endswith('|image/png|%d|%s' % (shot.stat().st_size, png)), seen
            assert seen[2] == {'kind': 'test', 'how': 'paste', 'list': ['clip.mp4|video/mp4|%d|0,0,0,24' % video.stat().st_size]}, seen
            assert seen[3]['how'] == 'text' and 'سلام' in seen[3]['list'][0], seen
            assert not self.media.shared, 'every file address is used once and then gone'
            # Right-click «Paste» in the message box goes through the same path.
            menu = WebKit2.ContextMenu.new()
            for stock in (WebKit2.ContextMenuAction.COPY, WebKit2.ContextMenuAction.PASTE):
                menu.append(WebKit2.ContextMenuItem.new_from_stock_action(stock))

            class EditableHit:
                @staticmethod
                def context_is_editable():
                    return True
            self.media.context_menu(self.view, menu, None, EditableHit())
            item = menu.get_items()[1]
            assert item.get_stock_action() == WebKit2.ContextMenuAction.CUSTOM and item.get_gaction(), 'paste item replaced'
            item.get_gaction().activate(None)   # text on the clipboard: falls back to a normal paste
            GLib.timeout_add(800, self.check_menu_paste)
            return False
            # Ctrl+V with a Persian layout: the key's Latin meaning still counts.
            event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
            keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
            event.hardware_keycode = keymap.get_entries_for_keyval(Gdk.KEY_v)[1][0].keycode
            event.keyval, event.state = 0x5d1, Gdk.ModifierType.CONTROL_MASK   # Arabic letter reh, on the V key
            assert paste_is_ctrl_v(event)
            event.state = 0
            assert not paste_is_ctrl_v(event)
        except Exception as error:
            errors.append('%s | %s' % (error, seen))
            self.quit()
        return False

    def check_menu_paste(self):
        try:
            assert seen[-1]['how'] == 'text' and seen[-1]['list'][0].count('سلام') == 2, seen
            print('PASS: dropped photo, pasted screenshot, pasted copied video reach Bale as files; '
                  'text paste and right-click paste unchanged')
        except Exception as error:
            errors.append('%s | %s' % (error, seen))
        self.quit()
        return False


app = MediaApp()
GLib.timeout_add_seconds(60, lambda: (errors.append('timeout'), app.quit(), False)[-1])
app.run([sys.argv[0]])
work.cleanup()
if errors:
    print('FAIL: ' + '; '.join(errors))
sys.exit(bool(errors))
