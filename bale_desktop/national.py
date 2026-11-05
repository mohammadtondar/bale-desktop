"""«اینترنت ملی»: reach Bale directly, with Iranian DNS, around a VPN.

A local-only HTTP proxy inside the app. WebKit sends Bale's traffic to it
instead of the system/VPN proxy; it resolves each host with Iranian DNS
servers (so Bale answers with its domestic addresses) and connects directly.
TLS is passed through untouched: the proxy only sees host names, not content.
"""
import ipaddress
import random
import socket
import socketserver
import struct
import threading
import time

# TCI (مخابرات), Shecan, Electro: reachable on the national network.
IRAN_DNS = ('217.218.155.155', '217.218.127.127', '178.22.122.100', '185.51.200.2', '78.157.42.100')


def build_query(name, ident):
    labels = name.rstrip('.').split('.')
    if not name or any(not 0 < len(label) < 64 for label in labels):
        raise ValueError('invalid host name')
    question = b''.join(bytes([len(part)]) + part for part in (l.encode('idna') for l in labels))
    return struct.pack('>HHHHHH', ident, 0x0100, 1, 0, 0, 0) + question + b'\0' + struct.pack('>HH', 1, 1)


def _skip_name(data, offset):
    while True:
        length = data[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + length


def parse_answer(data, ident):
    """IPv4 addresses and the shortest TTL from a DNS response."""
    reply, flags, questions, answers, _, _ = struct.unpack_from('>HHHHHH', data)
    if reply != ident or not flags & 0x8000 or flags & 0x000F:
        return [], 0
    offset = 12
    for _ in range(questions):
        offset = _skip_name(data, offset) + 4
    addresses, ttl = [], 3600
    for _ in range(answers):
        offset = _skip_name(data, offset)
        kind, klass, record_ttl, length = struct.unpack_from('>HHIH', data, offset)
        offset += 10
        if kind == 1 and klass == 1 and length == 4:
            addresses.append(socket.inet_ntoa(data[offset:offset + 4]))
            ttl = min(ttl, record_ttl)
        offset += length
    return addresses, max(ttl, 30)


class Resolver:
    def __init__(self, servers=IRAN_DNS, port=53, timeout=1.5):
        self.servers, self.port, self.timeout = list(servers), port, timeout
        self.cache = {}
        self.lock = threading.Lock()

    def query(self, server, host):
        ident = random.randrange(1 << 16)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.settimeout(self.timeout)
            udp.sendto(build_query(host, ident), (server, self.port))
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                data, source = udp.recvfrom(4096)
                if source[0] == server:
                    return parse_answer(data, ident)
        return [], 0

    def resolve(self, host):
        try:
            ipaddress.ip_address(host)
            return [host]
        except ValueError:
            pass
        host = host.lower().rstrip('.')
        with self.lock:
            cached = self.cache.get(host)
            if cached and cached[1] > time.monotonic():
                return cached[0]
        for server in self.servers:
            try:
                addresses, ttl = self.query(server, host)
            except (OSError, ValueError, IndexError, struct.error):
                continue
            if addresses:
                with self.lock:
                    self.cache[host] = (addresses, time.monotonic() + ttl)
                    if len(self.cache) > 500:
                        self.cache.pop(next(iter(self.cache)))
                return addresses
        # Iranian DNS unreachable: still connect directly, with the system resolver.
        try:
            return [info[4][0] for info in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)]
        except OSError:
            return []


def _pump(source, target):
    try:
        while True:
            data = source.recv(65536)
            if not data:
                break
            target.sendall(data)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        client = self.request
        client.settimeout(30)
        head = b''
        try:
            while b'\r\n\r\n' not in head:
                chunk = client.recv(8192)
                if not chunk or len(head) > 32768:
                    return
                head += chunk
            header, rest = head.split(b'\r\n\r\n', 1)
            lines = header.split(b'\r\n')
            method, target, version = lines[0].decode('latin-1').split(' ', 2)
            if method == 'CONNECT':
                host, _, port = target.rpartition(':')
                port, payload = int(port), rest
            else:
                # Plain http:// request in absolute form.
                if not target.startswith('http://'):
                    return self.fail(client, 400)
                authority, _, path = target[7:].partition('/')
                host, _, port = authority.partition(':')
                port = int(port or 80)
                kept = [l for l in lines[1:] if not l.lower().startswith(b'proxy-')]
                payload = b'\r\n'.join([('%s /%s %s' % (method, path, version)).encode('latin-1')] + kept) + b'\r\n\r\n' + rest
            host = host.strip('[]')
            if port not in self.server.allowed_ports or not host:
                return self.fail(client, 403)
        except (ValueError, OSError, UnicodeError):
            return self.fail(client, 400)

        upstream = None
        for address in self.server.resolver.resolve(host):
            try:
                upstream = socket.create_connection((address, port), timeout=10)
                break
            except OSError:
                continue
        if upstream is None:
            return self.fail(client, 502)
        with upstream:
            upstream.settimeout(None)
            client.settimeout(None)
            try:
                if method == 'CONNECT':
                    client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                if payload:
                    upstream.sendall(payload)
            except OSError:
                return
            other = threading.Thread(target=_pump, args=(upstream, client), daemon=True)
            other.start()
            _pump(client, upstream)
            other.join()

    @staticmethod
    def fail(client, code):
        try:
            client.sendall(b'HTTP/1.1 %d Proxy Error\r\nContent-Length: 0\r\nConnection: close\r\n\r\n' % code)
        except OSError:
            pass


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class NationalProxy:
    """Listens on 127.0.0.1 only; ports limited so it is not a general relay."""

    def __init__(self, resolver=None, allowed_ports=(80, 443)):
        self.server = _Server(('127.0.0.1', 0), _Handler)
        self.server.resolver = resolver or Resolver()
        self.server.allowed_ports = set(allowed_ports)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return 'http://127.0.0.1:%d' % self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
