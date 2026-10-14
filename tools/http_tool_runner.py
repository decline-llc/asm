"""Native WSL HTTP-tool broker. Run only inside a private network namespace.

There is no upstream transport here. Every HTTP request is exchanged with the
Windows coordinator over stdin/stdout; only that coordinator contacts targets.
"""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import socket
import ssl
import subprocess
import sys
import threading
from urllib.parse import urlsplit
import uuid

LOCK = threading.Lock()
PENDING = {}
SPEC = {}


def emit(value):
    with LOCK:
        print(json.dumps(value, ensure_ascii=True), flush=True)


def responses():
    for line in sys.stdin:
        value = json.loads(line)
        waiter = PENDING.get(value.get("id"))
        if waiter:
            waiter.put(value)


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    tunnel_host = None

    def log_message(self, *_args):
        pass

    def do_CONNECT(self):
        host = urlsplit("https://" + self.path).hostname
        # The certificate is generated for this job's input host only.
        if host != SPEC["host"]:
            self.send_error(403, "CONNECT host is outside this tool job")
            return
        self.send_response_only(200, "Connection established")
        self.end_headers()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain("broker.pem", "broker.key")
        self.connection = context.wrap_socket(self.connection, server_side=True)
        self.rfile = self.connection.makefile("rb")
        self.wfile = self.connection.makefile("wb")
        self.tunnel_host = self.path
        self.close_connection = False
        self.handle_one_request()

    def do_GET(self):
        self.forward()

    def do_HEAD(self):
        self.forward()

    def forward(self):
        if self.headers.get("Upgrade") or int(self.headers.get("Content-Length", "0")) or self.headers.get("Transfer-Encoding"):
            self.send_error(405, "Only bounded GET/HEAD observation is supported")
            return
        url = self.path if self.path.startswith(("http://", "https://")) else "https://" + self.tunnel_host + self.path
        request_id, waiter = uuid.uuid4().hex, queue.Queue(maxsize=1)
        PENDING[request_id] = waiter
        try:
            emit({"kind": "http_request", "id": request_id, "url": url, "method": self.command,
                  "headers": {k: v for k, v in self.headers.items() if k.lower() in {"accept", "user-agent", "origin"}}})
            reply = waiter.get(timeout=SPEC["timeout"])
            raw = base64.b64decode(reply.get("body_base64", ""), validate=True)
            self.send_response_only(int(reply["status"]))
            for key, value in reply.get("headers", {}).items():
                if key.lower() not in {"transfer-encoding", "content-encoding", "content-length", "connection", "set-cookie"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(raw)
        except (queue.Empty, BrokenPipeError, ConnectionError):
            self.close_connection = True
        finally:
            PENDING.pop(request_id, None)
            self.close_connection = True


def command(spec, proxy):
    tool, target = spec["tool"], spec["target"]
    rate, timeout = str(spec["rate"]), str(spec["timeout"])
    if tool == "httpx":
        return [tool, "-u", target, "-sc", "-title", "-td", "-j", "-silent", "-duc", "-nfs", "-retries", "0", "-rl", rate, "-timeout", timeout, "-http-proxy", proxy]
    if tool == "ffuf":
        return [tool, "-u", target.rstrip("/") + "/FUZZ", "-w", "dictionary.txt", "-mc", "all", "-rate", rate, "-t", "1", "-timeout", timeout, "-x", proxy, "-of", "json", "-o", "result.json", "-noninteractive", "-k"]
    if tool == "katana":
        return [tool, "-u", target, "-cs", spec["crawl_scope"], "-dr", "-duc", "-j", "-silent", "-d", str(spec["depth"]), "-rl", rate, "-c", "1", "-p", "1", "-timeout", timeout, "-proxy", proxy]
    if tool == "wafw00f":
        return [tool, "-r", "-p", proxy, "-T", timeout, "-f", "json", "-o", "result.json", target]
    if tool == "nuclei":
        args = [tool, "-u", target, "-pt", "http", "-ni", "-duc", "-dr", "-j", "-silent", "-omit-raw", "-omit-template", "-retries", "0", "-rl", rate, "-c", "1", "-timeout", timeout, "-proxy", proxy]
        for filename in spec["templates"]:
            args += ["-t", filename]
        return args
    if tool == "gowitness":
        return [tool, "scan", "file", "-f", "urls.txt", "--driver", spec.get("driver", "gorod"), "--chrome-path", str(Path("chrome-wrapper.py").resolve()), "--chrome-proxy", proxy,
                "--write-jsonl", "--write-jsonl-file", "result.jsonl", "--screenshot-format", "png", "--screenshot-path", "screenshots", "--threads", "1", "--timeout", timeout, "--skip-html"]
    raise ValueError("Unsupported broker tool")


def main():
    global SPEC
    SPEC = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    # A launch without network isolation must fail before launching a tool.
    interfaces = {name for _, name in socket.if_nameindex()}
    if interfaces != {"lo"} or SPEC["host"] != urlsplit(SPEC["target"]).hostname:
        raise ValueError("A private loopback-only network namespace is required")
    host = SPEC["host"]
    try:
        import ipaddress
        ipaddress.ip_address(host)
        san = "IP:" + host
    except ValueError:
        san = "DNS:" + host
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-keyout", "broker.key", "-out", "broker.pem", "-subj", "/CN=ASM local broker", "-addext", "subjectAltName=" + san], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.chmod("broker.key", 0o600)
    public = subprocess.run(["openssl", "x509", "-in", "broker.pem", "-pubkey", "-noout"], check=True, capture_output=True).stdout
    der = subprocess.run(["openssl", "pkey", "-pubin", "-outform", "DER"], input=public, check=True, capture_output=True).stdout
    pinned = base64.b64encode(hashlib.sha256(der).digest()).decode()
    wrapper = Path("chrome-wrapper.py")
    wrapper.write_text("#!/usr/bin/python3\nimport os,sys\nos.execv('/usr/bin/google-chrome', ['/usr/bin/google-chrome', '--no-sandbox', '--disable-quic', '--proxy-bypass-list=<-loopback>', '--ignore-certificate-errors-spki-list=" + pinned + "'] + sys.argv[1:])\n")
    wrapper.chmod(0o700)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=responses, daemon=True).start()
    proxy = "http://127.0.0.1:" + str(server.server_port)
    env = {**os.environ, "HTTP_PROXY": proxy, "HTTPS_PROXY": proxy, "NO_PROXY": "", "http_proxy": proxy, "https_proxy": proxy, "no_proxy": "",
           "SSL_CERT_FILE": str(Path("broker.pem").resolve()), "REQUESTS_CA_BUNDLE": str(Path("broker.pem").resolve())}
    version_args = [SPEC["tool"], "version"] if SPEC["tool"] == "gowitness" else [SPEC["tool"], "-V"] if SPEC["tool"] in {"ffuf", "wafw00f"} else [SPEC["tool"], "-version", "-duc"]
    version = subprocess.run(version_args, stdin=subprocess.DEVNULL, capture_output=True, timeout=10, env=env)
    version_text = (version.stdout + version.stderr)[:8192].decode("utf-8", errors="replace")
    args = command(SPEC, proxy)
    emit({"kind": "started", "args": args, "version": version_text})
    with Path("tool.stdout").open("wb") as stdout, Path("tool.stderr").open("wb") as stderr:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, env=env)
        try:
            code = process.wait(timeout=SPEC["job_timeout"])
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            code = 124
    server.shutdown()
    total = 0
    for pattern in ("tool.stdout", "tool.stderr", "result.json", "result.jsonl", "screenshots/*.png"):
        for path in sorted(Path.cwd().glob(pattern)):
            if not path.is_file() or path.is_symlink():
                continue
            total += path.stat().st_size
            if total > 32 * 1024 * 1024:
                raise ValueError("Tool artifact byte budget exceeded")
            emit({"kind": "artifact", "name": path.relative_to(Path.cwd()).as_posix(), "body_base64": base64.b64encode(path.read_bytes()).decode()})
    emit({"kind": "completed", "exit_code": code, "transport": "isolated_http_broker", "args": args, "version": version_text})


if __name__ == "__main__":
    Path("process-group.pid").write_text(str(os.getpgrp()) + "\n")
    main()
