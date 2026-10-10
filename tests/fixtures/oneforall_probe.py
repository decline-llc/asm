"""Offline HTTP transport for tests of the real pinned OneForAll vendor core."""
import json
import runpy
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

directory = Path.cwd()
plan = json.loads((directory / "oneforall-input.json").read_text(encoding="utf-8"))
fixture = json.loads((directory / "fixture.json").read_text(encoding="utf-8"))
lock = threading.Lock()
for name in ("fixture-requests.jsonl", "network-attempts.jsonl"):
    (directory / name).write_text("", encoding="utf-8")


def record(name, value):
    with lock, (directory / name).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value) + "\n")


def no_network(*args, **kwargs):
    record("network-attempts.jsonl", {"thread": threading.current_thread().name})
    raise AssertionError("Native passive fixture must never access the network")


def send(session, request, **kwargs):
    host = urlsplit(request.url).hostname
    record("fixture-requests.jsonl", {"url": request.url, "host": host,
        "thread": threading.current_thread().name, "verify": kwargs.get("verify"),
        "allow_redirects": kwargs.get("allow_redirects")})
    mode = fixture["mode"]
    if mode == "job_timeout":
        time.sleep(60)
    if mode == "module_timeout" and host == "api.certspotter.com":
        time.sleep(60)
    root = plan["root"]
    domains = [
        "api." + root, "mail." + root, "blocked." + root,
        "api.example.invalid", root + ".evil.invalid"]
    if host == "otx.alienvault.com":
        prefix = "dns-only" if "passive_dns" in request.url else "url-only"
        domains.append(prefix + "." + root)
    body = "" if mode == "empty" else json.dumps({"dns_names": domains})
    reply = requests.Response()
    reply.status_code = 503 if mode == "partial" and host == "api.certspotter.com" else 200
    reply.url, reply.request = request.url, request
    reply.encoding = "utf-8"
    reply.headers["Content-Type"] = "application/json"
    reply._content, reply._content_consumed = body.encode(), True
    return reply


requests.sessions.Session.send = send
socket.socket.connect = socket.socket.connect_ex = socket.getaddrinfo = no_network
sys.argv = ["oneforall_runner.py", "--input", str(directory / "oneforall-input.json")]
runpy.run_path(str(directory / "oneforall_runner.py"), run_name="__main__")
