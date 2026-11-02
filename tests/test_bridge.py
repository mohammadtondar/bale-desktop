from pathlib import Path
import unittest
import gi

gi.require_version('JavaScriptCore', '4.1')
from gi.repository import JavaScriptCore
from bale_desktop.app import trusted_url

ROOT = Path(__file__).resolve().parents[1]


class AdapterTests(unittest.TestCase):
    def evaluate(self, context, source):
        result = context.evaluate(source, -1)
        error = context.get_exception()
        if error:
            self.fail(error.to_string())
        return result

    def fixture(self):
        context = JavaScriptCore.Context()
        self.evaluate(context, (ROOT / 'tests/fixture.js').read_text())
        return context

    def test_notification_only_scenarios(self):
        context = self.fixture()
        self.evaluate(context, (ROOT / 'bale_desktop/bridge.js').read_text())
        self.assertIn('PASS', self.evaluate(context, (ROOT / 'tests/scenarios.js').read_text()).to_string())

    def test_untrusted_origin(self):
        context = self.fixture()
        self.evaluate(context, "location.origin = 'https://example.com'")
        self.evaluate(context, (ROOT / 'bale_desktop/bridge.js').read_text())
        self.assertTrue(self.evaluate(context, "typeof BaleDesktop === 'undefined'").to_boolean())

    def test_changed_web_contract_fails_closed(self):
        context = self.fixture()
        # A rebuild that no longer exports the expected symbols must fail closed.
        self.evaluate(context, "modules[49655] = {}; modules[41219] = {}")
        self.evaluate(context, (ROOT / 'bale_desktop/bridge.js').read_text())
        self.assertEqual(self.evaluate(context, "for (let i = 0; i < 5; i++) tick(); reports.at(-1).kind").to_string(), 'adapter-error')
        self.assertTrue(self.evaluate(context, "observer === undefined").to_boolean())

    def test_relocated_module_ids_still_connect(self):
        context = self.fixture()
        # Bale moved selfId from 41219 to 49655; the adapter must follow it.
        self.evaluate(context, "delete modules[49655]; modules[41219] = {H4: s => s.owner}")
        self.evaluate(context, (ROOT / 'bale_desktop/bridge.js').read_text())
        self.assertEqual(self.evaluate(context, "tick(); reports.at(-1).kind").to_string(), 'ready')

    def test_origin_validation(self):
        for uri in ['https://web.bale.ai/', 'https://web.bale.ai:443/chat']:
            self.assertTrue(trusted_url(uri))
        for uri in ['http://web.bale.ai/', 'https://web.bale.ai.evil.test/',
                    'https://web.bale.ai@evil.test/', 'https://user@web.bale.ai/',
                    'https://web.bale.ai:999/', 'file:///etc/passwd', 'https://web.bale.ai:bad/']:
            self.assertFalse(trusted_url(uri), uri)


if __name__ == '__main__':
    unittest.main()
