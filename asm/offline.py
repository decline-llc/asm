"""Offline execution services: local evidence only, with no live fallback."""
import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .utils.http import TargetHTTP


class OfflineExecutionError(RuntimeError):
    pass


def _forbidden(*args, **kwargs):
    raise OfflineExecutionError("External tools and browser launches are disabled during offline replay")


class OfflineBridge:
    """Fail before constructing a WSL command or discovering a WSL home."""
    control = command = argv = runner = _forbidden

    @property
    def home(self):
        return _forbidden()

    @property
    def workspace(self):
        return _forbidden()


class OfflineJobs:
    """A fixture run cannot launch, poll, recover or drain live tool jobs."""
    def __init__(self):
        self.handles = []

    run = wait = poll = result_dir = _forbidden

    def wait_all(self, **kwargs):
        if self.handles:
            _forbidden()
        return []

    def recover(self):
        # Persisted live jobs belong to the live executor, never to a replay.
        return []

    @property
    def fs(self):
        return _forbidden()


def evidence_path(root, value, suffix):
    root = Path(root).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() != suffix:
        raise ValueError(f"Replay evidence must be a project-local {suffix} file")
    return path


class ReplayHTTP(TargetHTTP):
    """Reuse URL/redirect validation with an exclusively in-memory transport.

    Exact saved URLs are required. The one synthetic URL family is the legacy
    random missing-page baseline, explicitly stored as ``/asm-missing-*``.
    Missing evidence raises a request error; it never requests a live response.
    """
    def __init__(self, ctx):
        self.ctx = ctx
        settings = ctx.config.get("replay", {})
        self.path = evidence_path(ctx.profile.root, settings.get("web_file", "tests/fixtures/web.json"), ".json")
        self.evidence = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(self.evidence, dict) or not isinstance(self.evidence.get("responses", []), list):
            raise ValueError("Replay web evidence must contain a responses list")
        self.requests = []
        self.screenshots = []
        self.entries = {}
        for entry in self.evidence.get("responses", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
                raise ValueError("Replay HTTP entries need a URL")
            if entry["url"] in self.entries:
                raise ValueError("Duplicate replay HTTP URL")
            self.entries[entry["url"]] = entry
        client = httpx.Client(transport=httpx.MockTransport(self._reply), follow_redirects=False, trust_env=False)
        super().__init__(ctx.scope, max_bytes=ctx.config.get("web", {}).get("max_response_bytes", 65536),
                         client=client)

    def _reply(self, request):
        url = str(request.url).rstrip("/")
        entry = self.entries.get(url)
        if entry is None:
            parsed = urlsplit(url)
            if parsed.path.startswith("/asm-missing-") and not parsed.query:
                prefix = f"{parsed.scheme}://{parsed.netloc}/asm-missing-*"
                entry = self.entries.get(prefix)
        record = {"url": url, "source": str(self.path.relative_to(self.ctx.profile.root)),
                  "execution_source": "replay", "status": "missing_evidence"}
        self.requests.append(record)
        if entry is None:
            raise httpx.RequestError("No saved offline HTTP response for this URL", request=request)
        if "body_file" in entry:
            body_path = evidence_path(self.ctx.profile.root, entry["body_file"], ".html")
            body = body_path.read_bytes()
        else:
            body = str(entry.get("body", "")).encode("utf-8")
        status = entry.get("status", 200)
        if type(status) is not int or not 100 <= status <= 599:
            raise ValueError("Invalid saved HTTP status")
        record.update(status="replayed", http_status=status, sha256=hashlib.sha256(body).hexdigest())
        return httpx.Response(status, headers=entry.get("headers", {}), content=body, request=request)

    def save(self):
        self.ctx.write("web-replay-evidence.json", {"execution_source": "replay",
            "fixture": str(self.path.relative_to(self.ctx.profile.root)),
            "fixture_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
            "requests": self.requests, "screenshots": self.screenshots})

    def close(self):
        try:
            super().close()
        finally:
            self.save()


def replay_screenshot(ctx, url, asset_id, http=None):
    """Copy an existing PNG; never import Playwright or start a browser."""
    ctx.scope.assert_in_scope(urlsplit(url).hostname or "")
    own = http is None
    http = http or ReplayHTTP(ctx)
    try:
        saved = http.evidence.get("screenshots", {})
        value = saved.get(url.rstrip("/")) if isinstance(saved, dict) else None
        if not value:
            raise OfflineExecutionError("No saved offline screenshot for this URL")
        source = evidence_path(ctx.profile.root, value, ".png")
        if not source.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Saved replay screenshot is not a PNG")
        destination = ctx.stage_dir.parent.parent / "screenshots" / f"asset-{asset_id}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
        ctx.db.execute("UPDATE urls SET screenshot=? WHERE url=?", (str(destination), url))
        http.screenshots.append({"url": url, "source": str(source.relative_to(ctx.profile.root)),
            "output": str(destination), "execution_source": "replay",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
        return destination
    finally:
        if own:
            http.close()
