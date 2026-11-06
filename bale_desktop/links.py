"""Which links stay in the app, and which go to the user's browser.

Bale links (ble.ir/…, bale://…, ble://…, web.bale.ai/…) open inside the app
at the address Bale Web itself understands; everything else goes to the
default browser. Mirrors windows/Links.cs.
"""
import re
import time
from urllib.parse import parse_qs, quote, urlencode, urlsplit

WEB = 'https://web.bale.ai/'
NICK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_]{3,}$')   # Bale Web: /^\/@[a-z0-9A-Z][a-z0-9_A-Z]{3,}/
NUMBER = re.compile(r'^-?\d+$')
PHONE = re.compile(r'^\+\d{8,15}$')
# ble.ir pages that are not user names.
RESERVED = {'post', 'join', 'share', 'download', 'app', 'apps', 'privacy', 'terms', 'about', 'blog',
            'contact', 'faq', 'help', 'support', 'banking-my-bank-page', 'static', 'api', '_next'}
EXTERNAL_SCHEMES = ('http', 'https', 'mailto', 'tel')


def is_web_bale(parts):
    return (parts.scheme == 'https' and parts.hostname == 'web.bale.ai' and parts.port in (None, 443)
            and not parts.username and not parts.password)


def bale_link_target(uri):
    """The in-app web.bale.ai address for a Bale link, or None for other links."""
    try:
        parts = urlsplit(uri or '')
        host = (parts.hostname or '').lower()
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if is_web_bale(parts):
        return uri
    if scheme in ('bale', 'ble'):
        # bale://join/token, ble://nick: the "host" is the first path segment.
        path, query = '/' + (parts.netloc + parts.path).strip('/'), parts.query
    elif scheme in ('http', 'https') and host in ('ble.ir', 'www.ble.ir') and not parts.username:
        path, query = parts.path, parts.query
    elif scheme in ('http', 'https') and host == 'l.ble.ir':
        # Bale's link-safety redirect: l.ble.ir?l=<target>
        inner = parse_qs(parts.query).get('l', [None])[0]
        return bale_link_target(inner) if inner else None
    else:
        return None

    segments = [s for s in path.split('/') if s]
    if not segments:
        return WEB
    first = segments[0]
    if first.lower() == 'join' and len(segments) >= 2:
        return WEB + 'join/' + quote(segments[1], safe='')
    if PHONE.match(first):
        return WEB + quote(first, safe='+')
    if NICK.match(first) and first.lower() not in RESERVED:
        params = {}
        if len(segments) >= 3 and NUMBER.match(segments[1]) and NUMBER.match(segments[2]):
            params = {'rid': segments[1], 'date': segments[2]}   # link to one message
        start = parse_qs(query).get('start')
        if start:
            params['start'] = start[0]
        return WEB + '@' + first + ('?' + urlencode(params) if params else '')
    return None


def external(uri):
    """True for links that belong in the user's browser or mail/phone app."""
    try:
        return urlsplit(uri or '').scheme.lower() in EXTERNAL_SCHEMES and bale_link_target(uri) is None
    except ValueError:
        return False


class OpenLimiter:
    """Bale opens outside links asynchronously (after its link-safety check), so
    there is no user gesture to rely on. Allow them, but never a burst of tabs
    and never the same link twice in a row."""

    def __init__(self, burst=3, window=10.0, repeat=2.0, clock=time.monotonic):
        self.burst, self.window, self.repeat, self.clock = burst, window, repeat, clock
        self.recent = []
        self.last = {}

    def allow(self, uri):
        now = self.clock()
        self.recent = [t for t in self.recent if now - t < self.window]
        if len(self.recent) >= self.burst or now - self.last.get(uri, -1e9) < self.repeat:
            return False
        self.recent.append(now)
        self.last[uri] = now
        if len(self.last) > 50:
            self.last = {u: t for u, t in self.last.items() if now - t < self.window}
        return True
