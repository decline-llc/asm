from dataclasses import replace
import shutil

import httpx
import pytest

from asm.bridge import Bridge, JobManager
from asm.conf import load_config
from asm.pipeline import StageContext
from asm.scope import ScopeError
from asm.stages.s7_web import run, screenshot
from asm.stages.s8_report import write_report
from asm.utils.http import TargetHTTP
from tests.fixtures.server import INJECTED_ROUTES, start_server


@pytest.fixture
def server():
    server = start_server()
    yield server
    server.shutdown()
    server.server_close()


def context(project, tmp_path, db, local_scope, url):
    config = load_config("test", project)
    data = {**config.data, "web": {"urls": [url], "screenshots": False}, "rates": {"ffuf_tps": 10000}}
    config = replace(config, data=data)
    bridge = Bridge()
    return StageContext(config, db, bridge, JobManager(bridge, db, tmp_path), local_scope, tmp_path / "stages/7",
                        target_local=True)


def test_all_injected_routes(project, tmp_path, db, local_scope, server):
    base = f"http://127.0.0.1:{server.server_address[1]}"
    ctx = context(project, tmp_path, db, local_scope, base)
    result = run(ctx)
    assert result.status == "completed"
    found = {r["url"].removeprefix(base) for r in db.rows("SELECT url FROM urls")}
    expected = set(INJECTED_ROUTES) - {"/", "/cdn-502", "/cdn-403"}
    assert expected <= found
    assert db.rows("SELECT * FROM findings WHERE kind='leak'")
    assert write_report(db, tmp_path / "report.xlsx")["总表"] == 1


def test_redirect_scope_blocks_before_second_request(local_scope):
    requested = []
    def handle(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://example.com/forbidden"})
    http = TargetHTTP(local_scope, client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ScopeError):
        http.get("http://127.0.0.1:8765/redirect")
    assert requested == ["http://127.0.0.1:8765/redirect"]
    with pytest.raises(ScopeError):
        http.get("https://example.com/")
    assert len(requested) == 1
    http.close()


@pytest.mark.browser
def test_screenshot_and_report_link(project, tmp_path, db, local_scope, server):
    from asm.doctor import chromium_installed
    if not chromium_installed():
        pytest.skip("Playwright Chromium not installed")
    base = f"http://127.0.0.1:{server.server_address[1]}"
    ctx = context(project, tmp_path, db, local_scope, base)
    run(ctx)
    screenshot(ctx, base, 1)
    path = tmp_path / "screenshots/asset-1.png"
    assert path.is_file() and path.read_bytes().startswith(b"\x89PNG")
    hostile = '</script><script>window.report_pwned=true</script>'
    db.execute("UPDATE assets SET title=? WHERE id=1", (hostile,))
    write_report(db, tmp_path / "report.xlsx")
    assert (tmp_path / "screenshots/1.png").is_file()
    # Move only HTML: the report must work offline with no screenshot folder beside it.
    moved = tmp_path / "moved" / "offline.html"
    moved.parent.mkdir()
    shutil.copyfile(tmp_path / "report.html", moved)
    from playwright.sync_api import expect, sync_playwright
    png_width = int.from_bytes(path.read_bytes()[16:20], "big")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        browser_context = browser.new_context(offline=True)
        page = browser_context.new_page()
        requests, errors = [], []
        page.on("request", lambda request: requests.append(request.url))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(moved.as_uri())
        assert page.locator("section[data-sheet]").count() == 8
        assert hostile in page.locator("#sheet-0").inner_text()
        assert page.evaluate("typeof window.report_pwned === 'undefined'")
        page.locator("#screenshot-1").scroll_into_view_if_needed()
        expect(page.locator("#screenshot-1 img")).to_have_js_property("naturalWidth", png_width)
        assert page.locator("#screenshot-1 img").get_attribute("src").startswith("data:image/png;base64,")
        page.locator("#search").fill("__NO_MATCH__")
        assert page.locator("#sheet-0 tr.data-row:visible").count() == 0
        page.locator("#search").fill("127.0.0.1")
        assert page.locator("#sheet-0 tr.data-row:visible").count() == 1
        assert not errors
        assert not any(url.startswith(("http://", "https://")) for url in requests)
        browser_context.close()
        static = browser.new_context(offline=True, java_script_enabled=False)
        page = static.new_page()
        page.goto(moved.as_uri())
        assert page.locator("#sheet-0 tr.data-row:visible").count() == 1
        page.locator("#screenshot-1").scroll_into_view_if_needed()
        expect(page.locator("#screenshot-1 img")).to_have_js_property("naturalWidth", png_width)
        static.close()
        browser.close()


def test_catchall_differential(project, tmp_path, db, local_scope):
    server = start_server(catch_all=True)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        run(context(project, tmp_path, db, local_scope, base))
        assert db.get_fact("catch_all:" + base) is True
        assert not db.rows("SELECT * FROM urls WHERE url LIKE '%/admin'")
    finally:
        server.shutdown()
        server.server_close()
