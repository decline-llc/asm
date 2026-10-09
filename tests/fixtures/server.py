"""Local-only fixture; runnable in Windows or copied into native WSL storage."""
import argparse
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

INJECTED_ROUTES = {
    "/": (200, "<html><title>Fixture Asset Portal</title><h1>Fixture Portal</h1><a href='/login'>Login</a></html>"),
    "/login": (200, '<html><title>Fixture Login</title><input type="password"></html>'),
    "/actuator/env": (200, '{"propertySources":[{"name":"fixture","properties":{"VALUE":{"value":"REDACTED"}}}]}'),
    "/actuator/heapdump": (200, "FIXTURE_HEAP_HEADER_NO_REAL_DATA"),
    "/swagger.json": (200, '{"swagger":"2.0","info":{"title":"Fixture API","version":"1"}}'),
    "/api/v1/user": (200, '{"fixture":true,"version":"v1"}'),
    "/mobile/v1/x": (200, '{"fixture":true,"version":"mobile-v1"}'),
    "/.git/HEAD": (200, "ref: refs/heads/fixture\n"),
    "/backup.zip": (200, "FIXTURE_ZIP_HEADER_NO_ARCHIVE"),
    "/phpinfo.php": (200, "<html><title>Fixture PHP Information</title>PHP Version fixture</html>"),
    "/server-status": (200, "Fixture Apache server status"),
    "/robots.txt": (200, "User-agent: *\nDisallow: /fixture-hidden\n"),
    "/sitemap.xml": (200, "<urlset><url><loc>http://localhost/fixture-hidden</loc></url></urlset>"),
    "/fixture-hidden": (200, "Fixture discovered route"),
    "/cdn-502": (502, "Fixture backend filtered"),
    "/cdn-403": (403, "Fixture denied"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append(self.path)
        if self.path in INJECTED_ROUTES:
            status, body = INJECTED_ROUTES[self.path]
        elif self.server.catch_all:
            status, body = 200, "<html><title>Fixture Catch All</title>" + "X" * 1000 + "</html>"
        else:
            status, body = 404, "Fixture Not Found".ljust(146, ".")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *_):
        pass


def start_server(port=0, catch_all=False):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.catch_all = catch_all
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def tcp_listener(port):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(100)
    def serve():
        while True:
            try:
                conn, _ = sock.accept()
                conn.sendall(b"SSH-2.0-Fixture_1.0\r\n")
                conn.close()
            except OSError:
                break
    threading.Thread(target=serve, daemon=True).start()
    return sock


def udp_listener(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", port))
    def serve():
        while True:
            try:
                packet, addr = sock.recvfrom(4096)
                sock.sendto(b"FIXTURE:" + packet, addr)
            except OSError:
                break
    threading.Thread(target=serve, daemon=True).start()
    return sock


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--catch-all", action="store_true")
    parser.add_argument("--extra-listeners", action="store_true")
    args = parser.parse_args()
    server = start_server(args.port, args.catch_all)
    listeners = [tcp_listener(8766), tcp_listener(8768), udp_listener(8767)] if args.extra_listeners else []
    print(json.dumps({"http": server.server_address[1], "tcp": [8766, 8768] if listeners else [],
                      "udp": [8767] if listeners else []}), flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        for listener in listeners:
            listener.close()
