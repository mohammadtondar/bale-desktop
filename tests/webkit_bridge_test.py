"""Run the adapter contract in the actual embedded WebKit engine, offline."""
import json
from pathlib import Path
import sys
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib, Gtk, WebKit2

root = Path(__file__).resolve().parents[1]
manager = WebKit2.UserContentManager()
manager.register_script_message_handler('bale')
manager.register_script_message_handler('test')
result = {'ok': False, 'message': 'WebKit test timed out'}


def done(_, message):
    result.update(json.loads(message.get_js_value().to_string()))
    Gtk.main_quit()


manager.connect('script-message-received::test', done)
view = WebKit2.WebView(user_content_manager=manager)
script = '\n'.join((root / name).read_text() for name in
                   ['tests/fixture.js', 'bale_desktop/bridge.js', 'tests/scenarios.js'])
script = "try {\n" + script + "\nwebkit.messageHandlers.test.postMessage(JSON.stringify({ok:true,message:'PASS: WebKit adapter scenarios'}));} catch(e) {webkit.messageHandlers.test.postMessage(JSON.stringify({ok:false,message:String(e.stack||e)}));}"
html = '<div id="root"></div><script type="application/json" src="/index.fe3fa18088.js"></script><script>' + script + '</script>'
view.load_html(html, 'https://web.bale.ai/')
GLib.timeout_add_seconds(12, lambda: (Gtk.main_quit(), False)[1])
Gtk.main()
print(result['message'])
sys.exit(0 if result['ok'] else 1)
