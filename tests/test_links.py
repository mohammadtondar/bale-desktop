"""Bale links stay in the app; all other links go to the browser."""
import unittest

from bale_desktop.links import OpenLimiter, bale_link_target, external


class LinkTests(unittest.TestCase):
    def test_bale_links_map_to_web_addresses(self):
        cases = {
            'https://ble.ir/bale': 'https://web.bale.ai/@bale',
            'http://www.ble.ir/Some_Channel/': 'https://web.bale.ai/@Some_Channel',
            'https://ble.ir/news_ch/123456/1700000000': 'https://web.bale.ai/@news_ch?rid=123456&date=1700000000',
            'https://ble.ir/mybot?start=abc': 'https://web.bale.ai/@mybot?start=abc',
            'https://ble.ir/join/AbC-123_x': 'https://web.bale.ai/join/AbC-123_x',
            'bale://join/AbC123': 'https://web.bale.ai/join/AbC123',
            'ble://somebody': 'https://web.bale.ai/@somebody',
            'bale://': 'https://web.bale.ai/',
            'https://ble.ir/+989121234567': 'https://web.bale.ai/+989121234567',
            'https://web.bale.ai/chat?uid=5': 'https://web.bale.ai/chat?uid=5',
            'https://l.ble.ir?l=https%3A%2F%2Fble.ir%2Fbale': 'https://web.bale.ai/@bale',
        }
        for uri, target in cases.items():
            self.assertEqual(bale_link_target(uri), target, uri)

    def test_other_links_are_not_bale_links(self):
        for uri in ['https://example.com/', 'https://l.ble.ir?l=https%3A%2F%2Fexample.com',
                    'https://ble.ir/post/1/2/3', 'https://ble.ir/abc', 'https://bale.ai/',
                    'https://ble.ir.evil.test/bale', 'https://user@ble.ir/bale',
                    'http://web.bale.ai/', 'https://web.bale.ai:8443/', 'javascript:alert(1)', '', None]:
            self.assertIsNone(bale_link_target(uri), uri)

    def test_external(self):
        self.assertTrue(external('https://example.com/a'))
        self.assertTrue(external('https://l.ble.ir?l=https%3A%2F%2Fexample.com'), 'safety redirect goes to the browser')
        self.assertTrue(external('mailto:a@b.c'))
        self.assertFalse(external('https://ble.ir/bale'))
        self.assertFalse(external('javascript:alert(1)'))
        self.assertFalse(external('file:///etc/passwd'))

    def test_limiter(self):
        now = [0.0]
        limiter = OpenLimiter(burst=3, window=10, repeat=2, clock=lambda: now[0])
        self.assertTrue(limiter.allow('a'))
        self.assertFalse(limiter.allow('a'), 'the same link twice in a row is one click')
        self.assertTrue(limiter.allow('b'))
        self.assertTrue(limiter.allow('c'))
        self.assertFalse(limiter.allow('d'), 'no burst of browser tabs')
        now[0] = 11
        self.assertTrue(limiter.allow('d'))
        self.assertTrue(limiter.allow('a'))


if __name__ == '__main__':
    unittest.main()
