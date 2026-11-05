"""«اینترنت ملی»: DNS parsing, resolver fallback and the local proxy relay."""
import http.server
import socket
import socketserver
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bale_desktop.national import NationalProxy, Resolver, build_query, parse_answer
from fake_dns import FakeDNS


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = ('host=%s path=%s' % (self.headers['Host'], self.path)).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class NationalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dns = FakeDNS({'web.bale.test': '127.0.0.1'})
        cls.web = socketserver.TCPServer(('127.0.0.1', 0), Page)
        threading.Thread(target=cls.web.serve_forever, daemon=True).start()
        cls.web_port = cls.web.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.web.shutdown()
        cls.web.server_close()
        cls.dns.close()

    def resolver(self, servers=None):
        return Resolver(servers or ['127.0.0.1'], port=self.dns.port, timeout=0.5)

    def test_query_and_answer_with_cname(self):
        resolver = self.resolver()
        self.assertEqual(resolver.resolve('web.bale.test'), ['127.0.0.1'])
        # Cached: no second query.
        count = len(self.dns.queries)
        self.assertEqual(resolver.resolve('WEB.bale.test.'), ['127.0.0.1'])
        self.assertEqual(len(self.dns.queries), count)

    def test_rejects_foreign_reply_and_bad_names(self):
        query = build_query('web.bale.ai', 7)
        self.assertEqual(parse_answer(b'\x00\x08' + query[2:], 7), ([], 0))
        with self.assertRaises(ValueError):
            build_query('a..b', 1)

    def test_ip_literal_and_unreachable_dns_fallback(self):
        self.assertEqual(self.resolver().resolve('10.1.2.3'), ['10.1.2.3'])
        # Iranian DNS unreachable: fall back to the system resolver instead of failing.
        dead = Resolver(['127.0.0.1'], port=1, timeout=0.3)
        self.assertIn('127.0.0.1', dead.resolve('localhost'))

    def request(self, proxy, raw):
        host, port = proxy.server.server_address
        with socket.create_connection((host, port), timeout=5) as client:
            client.sendall(raw)
            data = b''
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b'Proxy Error' in data:
                    break
            return data

    def test_plain_http_through_iranian_dns(self):
        proxy = NationalProxy(self.resolver(), allowed_ports=[self.web_port])
        try:
            reply = self.request(proxy, ('GET http://web.bale.test:%d/chat?x=1 HTTP/1.1\r\nHost: web.bale.test:%d\r\n'
                                         'Proxy-Connection: keep-alive\r\nConnection: close\r\n\r\n'
                                         % (self.web_port, self.web_port)).encode())
            self.assertIn(b'200', reply.split(b'\r\n')[0])
            self.assertIn(b'path=/chat?x=1', reply)
        finally:
            proxy.close()

    def test_connect_tunnel(self):
        proxy = NationalProxy(self.resolver(), allowed_ports=[self.web_port])
        try:
            reply = self.request(proxy, ('CONNECT web.bale.test:%d HTTP/1.1\r\n\r\n'
                                         'GET /tunnel HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n'
                                         % self.web_port).encode())
            self.assertTrue(reply.startswith(b'HTTP/1.1 200 Connection Established'), reply[:60])
            self.assertIn(b'path=/tunnel', reply)
        finally:
            proxy.close()

    def test_only_web_ports_are_relayed(self):
        proxy = NationalProxy(self.resolver())
        try:
            self.assertIn(b'403', self.request(proxy, b'CONNECT web.bale.test:22 HTTP/1.1\r\n\r\n'))
            self.assertEqual(proxy.server.server_address[0], '127.0.0.1')
        finally:
            proxy.close()


if __name__ == '__main__':
    unittest.main()
