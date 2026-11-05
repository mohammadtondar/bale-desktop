"""A tiny local DNS server for tests: answers A records from a dict."""
import socket
import struct
import threading


class FakeDNS:
    def __init__(self, records):
        self.records, self.queries = records, []
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('127.0.0.1', 0))
        self.port = self.socket.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                data, client = self.socket.recvfrom(512)
            except OSError:
                return
            ident = struct.unpack_from('>H', data)[0]
            offset, labels = 12, []
            while data[offset]:
                labels.append(data[offset + 1:offset + 1 + data[offset]].decode())
                offset += 1 + data[offset]
            question = data[12:offset + 5]
            name = '.'.join(labels)
            self.queries.append(name)
            address = self.records.get(name)
            answer = b''
            if address:
                # A CNAME first, as real resolvers often return, then the A record.
                answer = (b'\xc0\x0c' + struct.pack('>HHIH', 5, 1, 60, 2) + b'\xc0\x0c'
                          + b'\xc0\x0c' + struct.pack('>HHIH', 1, 1, 120, 4) + socket.inet_aton(address))
            header = struct.pack('>HHHHHH', ident, 0x8180 if address else 0x8183, 1, 2 if address else 0, 0, 0)
            self.socket.sendto(header + question + answer, client)

    def close(self):
        self.socket.close()
