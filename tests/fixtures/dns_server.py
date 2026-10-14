"""Bounded, local-only UDP/TCP DNS fixture; works in Windows and native WSL."""
import argparse
import ipaddress
import json
import random
import socketserver
import struct
import threading
import time
from pathlib import Path

TYPES = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "AAAA": 28}


def name_bytes(name):
    return b"".join(bytes([len(v)]) + v.encode("ascii") for v in name.rstrip(".").split(".")) + b"\0"


def reply(packet, records):
    if len(packet) < 12:
        return b""
    offset, labels = 12, []
    while offset < len(packet) and packet[offset]:
        size = packet[offset]
        if size > 63 or offset + size + 1 > len(packet):
            return b""
        labels.append(packet[offset + 1:offset + 1 + size].decode("ascii").lower())
        offset += size + 1
    offset += 1
    if offset + 4 > len(packet):
        return b""
    qtype = struct.unpack("!H", packet[offset:offset + 2])[0]
    domain, end = ".".join(labels), offset + 4
    values = records.get(domain)
    if values == {"DROP": True}:
        return b""
    answers = []
    if values:
        for rtype, entries in values.items():
            if TYPES[rtype] != qtype and rtype != "CNAME":
                continue
            for value in entries:
                if rtype in ("A", "AAAA"):
                    data = ipaddress.ip_address(value).packed
                elif rtype == "MX":
                    priority, host = value.split()
                    data = struct.pack("!H", int(priority)) + name_bytes(host)
                else:
                    data = name_bytes(value)
                answers.append(b"\xc0\x0c" + struct.pack("!HHIH", TYPES[rtype], 1, 60, len(data)) + data)
    flags = 0x8180 if values is not None else 0x8183
    return packet[:2] + struct.pack("!HHHHH", flags, 1, len(answers), 0, 0) + packet[12:end] + b"".join(answers)


class UDP(socketserver.BaseRequestHandler):
    def handle(self):
        packet, connection = self.request
        value = reply(packet, self.server.records)
        if value:
            connection.sendto(value, self.client_address)


class TCP(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(2)
        prefix = self.request.recv(2)
        if len(prefix) != 2:
            return
        size = struct.unpack("!H", prefix)[0]
        if size > 4096:
            return
        packet = b""
        while len(packet) < size:
            chunk = self.request.recv(size - len(packet))
            if not chunk:
                return
            packet += chunk
        value = reply(packet, self.server.records)
        if value:
            self.request.sendall(struct.pack("!H", len(value)) + value)


class DNSFixture:
    """Loopback UDP+TCP DNS fixture sharing one port.

    Windows can exclude port ranges (Hyper-V/WSL NAT and administered reservations), and the
    ephemeral allocator may hand out a UDP port that is excluded for TCP, so repeated port-0 draws
    can fail every time. Retry across a spread of explicit candidates instead of relying on draws.
    """

    RETRYABLE_ERRNOS = frozenset({13, 48, 98, 10013, 10048})
    RANDOM_ATTEMPTS = 48

    def __init__(self, records, port=0):
        udp = tcp = None
        for candidate in self._candidates(port):
            try:
                udp = socketserver.ThreadingUDPServer(("127.0.0.1", candidate), UDP)
                tcp = socketserver.ThreadingTCPServer(("127.0.0.1", udp.server_address[1]), TCP)
            except OSError as exc:
                for server in (udp, tcp):
                    if server is not None:
                        server.server_close()
                udp = tcp = None
                if not self._retryable(exc, port):
                    raise
            else:
                break
        if udp is None or tcp is None:
            raise OSError("no loopback port is available for both UDP and TCP DNS fixture sockets")
        self.udp, self.tcp, self.port = udp, tcp, udp.server_address[1]
        for server in (self.udp, self.tcp):
            server.daemon_threads = True
            server.records = records
            threading.Thread(target=server.serve_forever, daemon=True).start()

    @classmethod
    def _retryable(cls, exc, port):
        if port:
            return False
        code = exc.errno if exc.errno is not None else getattr(exc, "winerror", None)
        return code in cls.RETRYABLE_ERRNOS

    @classmethod
    def _candidates(cls, port):
        if port:
            yield port
            return
        yield 0
        for _ in range(cls.RANDOM_ATTEMPTS):
            yield random.randrange(20000, 60000)

    def close(self):
        for server in (self.udp, self.tcp):
            server.shutdown()
            server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True)
    parser.add_argument("--lifetime", type=int, default=35)
    args = parser.parse_args()
    settings = json.loads(Path(args.records).read_text())
    servers = ([DNSFixture(records) for records in settings] if isinstance(settings, list)
               else [DNSFixture(records, int(port)) for port, records in settings.items()])
    try:
        Path("ready.json").write_text(json.dumps([server.port for server in servers]))
        Path("ready").write_text("ready")
        time.sleep(args.lifetime)
    finally:
        for server in servers:
            server.close()


if __name__ == "__main__":
    main()
