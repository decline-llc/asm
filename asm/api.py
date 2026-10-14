"""Loopback HTTP/SSE API over the same durable Workbench used by the CLI."""
import json
import mimetypes
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import yaml

from .orchestrator import Workbench
from .run_store import digest

PROVIDERS = {"fofa": ["FOFA_EMAIL", "FOFA_KEY"], "quake": ["QUAKE_TOKEN"], "hunter": ["HUNTER_KEY"],
    "zoomeye": ["ZOOEYE_KEY"], "shodan": ["SHODAN_KEY"], "censys": ["CENSYS_ID", "CENSYS_SECRET"]}


class SecretSettings:
    """Secret values never leave this backend object; API data is a status or mask."""
    def __init__(self, root):
        self.path = Path(root) / ".env"
        self.lock = threading.RLock()

    def _values(self):
        from dotenv import dotenv_values
        return dotenv_values(self.path) if self.path.is_file() else {}

    def status(self):
        with self.lock:
            values = self._values()
            providers = {name: {"configured": all(values.get(k) or os.getenv(k) for k in keys),
                "fields": {k: "3***" if values.get(k) or os.getenv(k) else "" for k in keys}} for name, keys in PROVIDERS.items()}
        return {"providers": providers, "policy": {"fofa_min_interval": 15, "fofa_daily": 200}}

    def update(self, credentials):
        from dotenv import set_key
        allowed = {k for fields in PROVIDERS.values() for k in fields}
        if not isinstance(credentials, dict) or set(credentials) - allowed:
            raise ValueError("Unknown credential field")
        for value in credentials.values():
            if not isinstance(value, str) or len(value) > 4096 or any(c in value for c in "\r\n\x00"):
                raise ValueError("Invalid credential value")
        with self.lock:
            for name, value in credentials.items():
                if value:
                    set_key(str(self.path), name, value, quote_mode="always")
                    os.environ[name] = value
        return self.status()

    def test(self, provider, root):
        if provider not in PROVIDERS:
            raise ValueError("Unknown provider")
        with self.lock:
            values = self._values()
        credentials = {k: values.get(k) or os.getenv(k, "") for k in PROVIDERS[provider]}
        if not all(credentials.values()):
            return {"provider": provider, "status": "credentials_missing"}
        if provider != "fofa":
            return {"provider": provider, "status": "configured_unverified", "reason": "account_validation_adapter_not_integrated"}
        from .db import Database
        from .panel.base import RateLimiter, QuotaExceeded
        import httpx
        account = digest([provider, list(credentials.values())])[:16]
        try:
            with Database(Path(root) / "data/account-rate-ledger.sqlite") as db:
                limiter = RateLimiter(db, "fofa", min_interval=15, daily=200)
                limiter.source = "fofa:" + account
                limiter.acquire()
                with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
                    response = client.get("https://fofa.info/api/v1/info/my", params={"email": credentials["FOFA_EMAIL"], "key": credentials["FOFA_KEY"]})
                    response.raise_for_status()
                    payload = response.json()
                    return {"provider": provider, "status": "failed" if payload.get("error") else "connected"}
        except QuotaExceeded:
            return {"provider": provider, "status": "quota-exhausted"}
        except (httpx.HTTPError, ValueError):
            return {"provider": provider, "status": "failed", "reason": "account_validation_failed"}


def create_server(root, *, port=6400, workbench=None):
    root = Path(root).resolve()
    settings = SecretSettings(root)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            # Requests may contain user input. The API does not write raw HTTP logs.
            pass

        def _origin(self):
            port = self.server.server_address[1]
            allowed = {f"http://{host}:{p}" for host in ("127.0.0.1", "localhost") for p in (port, 6100, 6200)}
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1:6100", "127.0.0.1:6200"}:
                raise ValueError("Local Host required")
            if origin and origin not in allowed:
                raise ValueError("Origin denied")
            return origin

        def _headers(self, code, mime, size=None):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            if size is not None:
                self.send_header("Content-Length", str(size))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if self.close_connection:
                self.send_header("Connection", "close")
            origin = self.headers.get("Origin")
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()

        def _json(self, value, code=200):
            raw = json.dumps(value, ensure_ascii=False).encode()
            self._headers(code, "application/json; charset=utf-8", len(raw))
            self.wfile.write(raw)

        def _body(self):
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise ValueError("JSON content type required")
            size = int(self.headers.get("Content-Length", 0))
            if size < 0 or size > 1_048_576:
                raise ValueError("Request too large")
            value = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(value, dict):
                raise ValueError("JSON object required")
            return value

        def do_OPTIONS(self):
            try:
                self._origin()
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
                self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type,Last-Event-ID")
                self.send_header("Content-Length", "0")
                self.end_headers()
            except ValueError:
                self._json({"error": "Origin denied"}, 403)

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def do_PUT(self):
            self._handle("PUT")

        def _artifact_response(self, run_id, relative):
            path = workbench.artifact(run_id, relative)
            raw = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime + ("; charset=utf-8" if path.suffix in {".html", ".md", ".csv", ".json", ".jsonl", ".yaml"} else ""))
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # Imported HTML is evidence, not trusted executable app content.
            self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def _handle(self, method):
            try:
                self._origin()
                route = urlsplit(self.path)
                parts = [unquote(p) for p in route.path.strip("/").split("/")]
                query = parse_qs(route.query)
                body = self._body() if method != "GET" else {}
                if parts == ["api", "health"] and method == "GET":
                    return self._json({"status": "ready", "pid": os.getpid()})
                if parts == ["api", "modes"] and method == "GET":
                    return self._json(yaml.safe_load((root / "profiles/modes.yaml").read_text(encoding="utf-8")))
                if parts == ["api", "tools"] and method == "GET":
                    from .workbench_tools import tool_registry
                    catalog = yaml.safe_load((root / "profiles/modes.yaml").read_text(encoding="utf-8"))["capability_catalog"]
                    adapters = tool_registry()
                    return self._json({k: {**v, "runtime_adapter": "integrated" if k in adapters else "missing", "installation": "checked_at_execution"} for k, v in catalog.items()})
                if parts == ["api", "projects"]:
                    return self._json(workbench.projects(query.get("purpose", ["investigation"])[0])
                                      if method == "GET" else workbench.save_project(body),
                                      200 if method == "GET" else 201)
                if parts == ["api", "import"] and method == "POST":
                    path = (root / "profiles" / (body["profile"] + ".yaml")).resolve()
                    if not path.is_relative_to(root / "profiles"):
                        raise ValueError("Invalid profile path")
                    if not path.is_file():
                        from .project_catalog import PURPOSE_DIRECTORIES
                        matches = [root / "profiles" / directory / (body["profile"] + ".yaml")
                                   for directory in PURPOSE_DIRECTORIES.values()
                                   if (root / "profiles" / directory / (body["profile"] + ".yaml")).is_file()]
                        if len(matches) != 1:
                            raise ValueError("Profile not found or ambiguous; specify its category path")
                        path = matches[0].resolve()
                    return self._json(workbench.import_project(str(path)))
                if len(parts) == 4 and parts[:2] == ["api", "projects"]:
                    project_id, action = parts[2:]
                    if action == "config":
                        return self._json(workbench.project(project_id) if method == "GET" else workbench.save_project(body, project_id=project_id))
                    if action == "plan" and method == "GET":
                        return self._json(workbench.plan(project_id))
                    if action == "start" and method == "POST":
                        return self._json(workbench.start(project_id, source=body.get("source")))
                    if action == "scope" and method == "POST":
                        return self._json(workbench.add_scope(project_id, body["value"]))
                    if action == "run" and method == "GET":
                        runs = workbench.store.rows("SELECT id FROM runs WHERE project=? ORDER BY started DESC,rowid DESC LIMIT 1", (project_id,))
                        return self._json(workbench.run(runs[0]["id"]) if runs else None)
                if len(parts) >= 5 and parts[:2] == ["api", "runs"] and parts[3] == "content" and method == "GET":
                    return self._artifact_response(parts[2], "/".join(parts[4:]))
                if len(parts) == 4 and parts[:2] == ["api", "runs"]:
                    run_id, action = parts[2:]
                    if action in {"pause", "resume", "stop"} and method == "POST":
                        return self._json(workbench.control(run_id, action))
                    if action == "export" and method == "POST":
                        return self._json(workbench.export(run_id))
                    if action == "bundle" and method == "POST":
                        return self._json(workbench.bundle(run_id, body.get("snapshot_id")))
                    if action == "review" and method == "POST":
                        return self._json(workbench.review(run_id, body["asset_id"], status=body["status"], note=body.get("note", ""),
                            evidence_ids=body.get("evidence_ids"), corroborated=body.get("corroborated", False)))
                    if action == "state" and method == "GET":
                        return self._json(workbench.run(run_id))
                    if action == "artifacts" and method == "GET":
                        return self._json(workbench.artifacts(run_id))
                    if action == "files" and method == "GET":
                        return self._artifact_response(run_id, query.get("path", [""])[0])
                    if action == "events" and method == "GET":
                        workbench.run(run_id)
                        after = int(self.headers.get("Last-Event-ID") or query.get("after", [0])[0])
                        self._headers(200, "text/event-stream; charset=utf-8")
                        for _ in range(60):
                            events = workbench.store.events(run_id, after)
                            for event in events:
                                raw = f"id: {event['id']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
                                self.wfile.write(raw)
                                after = event["id"]
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            time.sleep(0.25)
                        self.close_connection = True
                        return
                if parts == ["api", "settings"]:
                    return self._json(settings.status() if method == "GET" else settings.update(body.get("credentials", {})))
                if parts == ["api", "settings", "test"] and method == "POST":
                    return self._json(settings.test(body["provider"], root))
                if route.path.startswith("/api/"):
                    return self._json({"error": "Unknown endpoint"}, 404)
                if method == "GET":
                    directory = root / "frontend/dist"
                    path = (directory / route.path.lstrip("/")).resolve()
                    if not path.is_relative_to(directory):
                        raise ValueError("Invalid static path")
                    if not path.is_file():
                        path = directory / "index.html"
                    if not path.is_file():
                        return self._json({"status": "frontend_not_built", "command": "npm run build"}, 404)
                    raw = path.read_bytes()
                    self._headers(200, mimetypes.guess_type(path.name)[0] or "application/octet-stream", len(raw))
                    return self.wfile.write(raw)
                self._json({"error": "Unknown endpoint"}, 404)
            except ConnectionError:
                pass
            except (ValueError, KeyError, OSError) as exc:
                # Rejected bodies must not become the next keep-alive request line.
                self.close_connection = True
                self._json({"error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}, 400)
            except Exception:
                self.close_connection = True
                self._json({"error": "Internal error; inspect durable run state"}, 500)

    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address = False

        def server_bind(self):
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    # Bind before recovering state: a duplicate server must not touch live runs.
    server = LocalServer(("127.0.0.1", port), Handler)
    try:
        workbench = workbench or Workbench(root)
    except BaseException:
        server.server_close()
        raise
    server.daemon_threads = True
    server.workbench = workbench
    return server


def serve(root, *, port=6400):
    server = create_server(root, port=port)
    print(f"ASM Workbench: http://127.0.0.1:{server.server_address[1]} (PID {os.getpid()})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
