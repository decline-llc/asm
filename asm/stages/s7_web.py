import hashlib
import re
import secrets
import time
from urllib.parse import urljoin, urlsplit

import httpx

from ..models import Asset
from ..pipeline import StageResult
from ..scope import ScopeError
from ..utils.constants import JAVA_PRODUCTS, LEAK_PATHS, SPRAY_PATHS
from ..utils.http import TargetHTTP


def differential(status):
    return {502: "backend_filtered_candidate", 404: "not_found", 403: "route_denied"}.get(status, "other")


def catch_all(responses):
    return len(responses) >= 3 and len({(r.status, len(r.body), hashlib.sha256(r.body).hexdigest())
                                      for r in responses}) == 1 and responses[0].status == 200


def technologies(response):
    text = response.text.lower()
    headers = response.headers
    items = []
    server = headers.get("server", "")
    if server:
        items.append(server)
    for marker, product in (("jsessionid", "Java"), ("phpsessid", "PHP"), ("_rails_session", "Rails"),
                            ("spring", "Spring"), ("shiro", "Shiro"), ("tomcat", "Tomcat")):
        if marker in text or marker in str(headers).lower():
            items.append(product)
    return ",".join(sorted(set(items)))


def discovered_paths(text):
    paths = set(re.findall(r"(?im)^Disallow:\s*(/[^\s]*)", text))
    for url in re.findall(r"<loc>(.*?)</loc>", text, re.I):
        parsed = urlsplit(url)
        if parsed.path:
            paths.add(parsed.path)
    return paths


def run(ctx):
    urls = list(ctx.config.get("web", {}).get("urls", []))
    for asset in ctx.db.rows("SELECT * FROM assets WHERE proto='tcp'"):
        if asset["service"] in {"http", "https", "ssl/http", "http-proxy"} or asset["port"] in {80, 443, 8765}:
            host = asset["host"]
            host = "[" + host + "]" if ":" in host else host
            urls.append(f"{'https' if asset['port'] in {443,8443} else 'http'}://{host}:{asset['port']}")
    urls = list(dict.fromkeys(u.rstrip("/") for u in urls))
    http = TargetHTTP(ctx.scope, timeout=ctx.config.get("limits", {}).get("http_timeout", 15),
                      max_bytes=ctx.config.get("web", {}).get("max_response_bytes", 65536))
    count, notes = 0, []
    try:
        for url in urls:
            ctx.scope.assert_in_scope(urlsplit(url).hostname or "")
            if ctx.db.rows("SELECT 1 FROM findings WHERE kind='honeypot' AND url=?", (urlsplit(url).hostname,)):
                continue
            try:
                root = http.get(url)
            except httpx.HTTPError as exc:
                notes.append(f"{url}: {type(exc).__name__}")
                continue
            parsed = urlsplit(url)
            table, asset_id = ctx.db.asset(Asset(host=parsed.hostname, port=parsed.port or (443 if parsed.scheme == "https" else 80),
                service=parsed.scheme, title=root.title, tech=technologies(root), source="http"))
            if table != "assets":
                continue
            ctx.db.upsert("urls", {"url": url, "asset_id": asset_id, "title": root.title,
                "status": root.status, "len": len(root.body), "tech": technologies(root), "screenshot": ""}, ("url",))
            baselines = [http.get(url + "/asm-missing-" + secrets.token_hex(5)) for _ in range(3)]
            baseline = {(r.status, len(r.body), hashlib.sha256(r.body).hexdigest()) for r in baselines}
            is_catchall = catch_all(baselines)
            ctx.db.fact("catch_all:" + url, is_catchall)
            paths = list(dict.fromkeys(SPRAY_PATHS + LEAK_PATHS + ["/api/v1/user", "/mobile/v1/x"]))
            visited = set()
            for path in paths:
                if path in visited:
                    continue
                visited.add(path)
                endpoint = urljoin(url + "/", path.lstrip("/"))
                time.sleep(1 / ctx.config.get("rates", {}).get("ffuf_tps", 50))
                try:
                    reply = http.get(endpoint)
                except httpx.HTTPError as exc:
                    ctx.note("request_error", endpoint, type(exc).__name__)
                    continue
                signature = (reply.status, len(reply.body), hashlib.sha256(reply.body).hexdigest())
                if reply.status in {403, 502}:
                    ctx.note("cdn_differential", endpoint, differential(reply.status))
                if reply.status != 200 or signature in baseline:
                    continue
                tech = technologies(reply)
                ctx.db.upsert("urls", {"url": endpoint, "asset_id": asset_id, "title": reply.title,
                    "status": reply.status, "len": len(reply.body), "tech": tech, "screenshot": ""}, ("url",))
                evidence = f"status={reply.status}; len={len(reply.body)}; sha256={hashlib.sha256(reply.body).hexdigest()}"
                kind = ("leak" if path in LEAK_PATHS else "actuator" if path.startswith("/actuator")
                        else "swagger" if path in {"/swagger.json", "/openapi.json", "/api-docs"} else "route")
                ctx.db.finding({"asset_id": asset_id, "kind": kind, "url": endpoint, "evidence": evidence,
                                "severity": "medium" if kind != "route" else "info", "status": "review"})
                if 'type="password"' in reply.text.lower() or "type='password'" in reply.text.lower():
                    ctx.note("login", endpoint, "Password field observed; SSO入口/登录页")
                for marker, (product, _) in JAVA_PRODUCTS.items():
                    if path.startswith(marker):
                        ctx.db.upsert("systems", {"system_name": product, "urls": endpoint,
                            "tags": "middleware", "source": "route_fingerprint"}, ("system_name",), merge=True)
                if path in {"/robots.txt", "/sitemap.xml"}:
                    paths.extend(p for p in discovered_paths(reply.text) if p.startswith("/") and not p.startswith("//"))
                if (reply.headers.get("access-control-allow-origin") == "*"
                        and reply.headers.get("access-control-allow-credentials", "").lower() == "true"):
                    ctx.note("cors", endpoint, "Wildcard origin with credentials; browser behavior requires review", "low")
                count += 1
            if ctx.config.get("web", {}).get("screenshots", True):
                try:
                    screenshot(ctx, url, asset_id)
                except (RuntimeError, OSError) as exc:
                    notes.append("Screenshot: " + str(exc))
    finally:
        http.close()
    return StageResult("partial" if notes else "completed", count, notes)


def screenshot(ctx, url, asset_id):
    """Scoped Playwright in Windows is a library-level capability, per architecture."""
    from playwright.sync_api import sync_playwright
    destination = ctx.stage_dir.parent.parent / "screenshots" / f"asset-{asset_id}.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    blocked = []
    def route(request_route):
        request_url = request_route.request.url
        try:
            if urlsplit(request_url).scheme not in {"http", "https"}:
                request_route.abort()
                return
            ctx.scope.assert_in_scope(urlsplit(request_url).hostname or "")
            request_route.continue_()
        except (ValueError, ScopeError):
            blocked.append(request_url)
            request_route.abort()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(service_workers="block", accept_downloads=False)
            context.route("**/*", route)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.screenshot(path=str(destination), full_page=True)
        finally:
            browser.close()
    for request_url in blocked:
        ctx.note("screenshot_scope_block", request_url, "Blocked out-of-scope browser request before dispatch")
    ctx.db.execute("UPDATE urls SET screenshot=? WHERE url=?", (str(destination), url))
