"""Exercise the real loopback Workbench UI, never settings or internet assets."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
from pathlib import Path
import sys
import threading
import time
import zipfile
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:6400"
OUT = ROOT / "data/validation/workbench-20261011"


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append({"path": self.path, "at": time.monotonic()})
        body = ("<!doctype html><html><title>UI Fixture " + self.path +
                "</title><h1>Local Workbench fixture</h1></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def configuration(project_id, fixture_url):
    return {
        "schema_version": 2, "profile": project_id, "name": "Workbench UI fixture " + project_id,
        "project_purpose": "validation",
        "mode_preset": "full_asm", "authorization": True,
        "authorization_details": {"authority": "fixture_owner", "reference": "self_owned_local_fixture", "environment": "local_lab"},
        "execution": {"source": "live", "target_local": True},
        "targets": {"roots": [], "ip_cidrs": ["127.0.0.1/32"]},
        "scope_sets": {name: {"include": ["127.0.0.1/32"], "exclude": [], "domain_match": "exact"}
                       for name in ("investigation", "verification", "extended")},
        "permissions": {"web_visit": {"allow": True, "scope_ref": "verification"}},
        "plan": {"selection": "custom", "selected_capabilities": ["web_visit"], "selected_tools": ["target_http"],
                 "params": {"web_visit": {"urls": [fixture_url], "timeout_seconds": 3, "requests_per_second": 10}}},
        "web": {"urls": [fixture_url]},
        "budgets": {"max_rounds": 1, "max_hosts": 1, "max_duration_seconds": 120},
        "reports": {"variants": ["professional", "user_custom"], "formats": ["csv", "html", "md"], "snapshot_policy": "immutable"},
    }


def main(image_run_id=None):
    global BASE
    from asm.api import create_server
    from asm.orchestrator import Workbench
    testing = Workbench(ROOT, validation=True, recover=False)
    if image_run_id and not testing.store.rows("SELECT id FROM runs WHERE id=?", (image_run_id,)):
        # A legacy native fixture may be copied into the test catalog for read-only UI verification.
        # Its original project, frozen run configuration and on-disk evidence are retained verbatim.
        import sqlite3
        with sqlite3.connect((ROOT / "data/workbench.sqlite").as_uri() + "?mode=ro", uri=True) as original:
            original.row_factory = sqlite3.Row
            saved = original.execute("SELECT * FROM runs WHERE id=?", (image_run_id,)).fetchone()
            if not saved or not saved["project"].startswith("lab_native_") or not json.loads(saved["config"])["execution"]["target_local"]:
                raise ValueError("Only a saved local native fixture can be used for image verification")
            with testing.store.connection() as conn:
                for table, field, value in (("projects", "id", saved["project"]), ("runs", "id", image_run_id),
                                             ("steps", "run", image_run_id), ("assets", "run", image_run_id), ("records", "run", image_run_id)):
                    for row in original.execute(f"SELECT * FROM {table} WHERE {field}=?", (value,)):
                        marks = ",".join("?" for _ in row)
                        conn.execute(f"INSERT OR IGNORE INTO {table} VALUES({marks})", tuple(row))
    isolated = create_server(ROOT, port=0, workbench=testing)
    threading.Thread(target=isolated.serve_forever, daemon=True).start()
    BASE = "http://127.0.0.1:" + str(isolated.server_address[1])
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifact_dir = OUT / ("ui-" + stamp)
    artifact_dir.mkdir()
    checks, evidence, errors, blocked, forbidden_settings, sse = {}, {}, [], [], [], []
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    fixture.requests = []
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    fixture_url = "http://127.0.0.1:" + str(fixture.server_address[1])
    project_id = "ui_fixture_" + stamp
    config = configuration(project_id, fixture_url)

    def check(name, condition, details=None):
        checks[name] = bool(condition)
        if details is not None:
            evidence[name] = details
        print(("PASS " if condition else "FAIL ") + name, flush=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", service_workers="block")

            def guard(route):
                parsed = urlsplit(route.request.url)
                if parsed.path == "/api/settings":
                    forbidden_settings.append(route.request.url)
                    route.abort()
                elif parsed.scheme in {"data", "blob"} or parsed.hostname in {"localhost", "127.0.0.1"}:
                    route.continue_()
                else:
                    blocked.append(route.request.url)
                    route.abort()

            context.route("**/*", guard)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: sse.append({"url": request.url, "last_event_id": request.headers.get("last-event-id", "")})
                    if urlsplit(request.url).path.endswith("/events") else None)

            def api(path):
                # Reads are limited to explicitly created fixture records and their files.
                assert path.startswith(("/api/projects/" + project_id, "/api/runs/"))
                reply = context.request.get(BASE + path)
                assert reply.ok, (reply.status, path, reply.text())
                return reply.json()

            def state(run_id):
                return api("/api/runs/" + run_id + "/state")

            def await_state(run_id, accepted, timeout=30):
                deadline = time.monotonic() + timeout
                latest = None
                while time.monotonic() < deadline:
                    latest = state(run_id)
                    if latest["status"] in accepted and latest.get("snapshot"):
                        return latest
                    page.wait_for_timeout(150)
                raise AssertionError("Run state timeout: " + json.dumps(latest, ensure_ascii=False))

            def edit(value, creating=False):
                if creating:
                    page.get_by_role("button", name="新建项目", exact=True).click()
                else:
                    page.get_by_role("button", name="配置 / 工具 / 权限", exact=True).click()
                page.get_by_text("有效项目配置 · 高级 JSON 编辑（后端保存为 YAML）", exact=True).click()
                page.get_by_role("textbox", name="有效项目配置", exact=True).fill(json.dumps(value, ensure_ascii=False, indent=2))
                method = "POST" if creating else "PUT"
                path = "/api/projects" if creating else "/api/projects/" + project_id + "/config"
                with page.expect_response(lambda response: urlsplit(response.url).path == path and response.request.method == method) as saved:
                    page.get_by_role("button", name="创建项目" if creating else "保存配置及权限修订", exact=True).click()
                assert saved.value.ok, saved.value.text()
                page.get_by_role("button", name="新运行", exact=True).wait_for()

            def start():
                with page.expect_response(lambda response: urlsplit(response.url).path == "/api/projects/" + project_id + "/start") as started:
                    page.get_by_role("button", name="新运行", exact=True).click()
                assert started.value.ok, started.value.text()
                return started.value.json()["run_id"]

            def control(run_id, operation, label):
                button = page.get_by_role("button", name=label, exact=True)
                deadline = time.monotonic() + 10
                while not button.is_enabled() and time.monotonic() < deadline:
                    page.wait_for_timeout(150)
                with page.expect_response(lambda response: urlsplit(response.url).path == "/api/runs/" + run_id + "/" + operation) as controlled:
                    button.click()
                assert controlled.value.ok, controlled.value.text()

            def synchronize(run_id, wanted, timeout=15):
                page.wait_for_function("({id,state}) => document.querySelector('.wb-panel.wb-run-summary .wb-badge')?.dataset.state === state && document.body.innerText.includes(id)",
                                       arg={"id": run_id, "state": wanted}, timeout=timeout * 1000)
                page.wait_for_timeout(400)

            def report_links(run_id):
                links = page.locator(".wb-report-links a")
                deadline = time.monotonic() + 12
                while links.count() < 6 and time.monotonic() < deadline:
                    page.wait_for_timeout(150)
                paths, hashes = [], {}
                for href in links.evaluate_all("elements => elements.map(element => element.getAttribute('href'))"):
                    parsed = urlsplit(href)
                    prefix = "/api/runs/" + run_id + "/content/"
                    if parsed.path.startswith(prefix):
                        path = unquote(parsed.path[len(prefix):])
                    else:
                        assert parsed.path == "/api/runs/" + run_id + "/files"
                        path = parse_qs(parsed.query)["path"][0]
                    paths.append(path)
                    response = context.request.get(urljoin(BASE, href))
                    check("Report readable " + path, response.ok and bool(response.body()))
                    hashes[path] = sha256(response.body()).hexdigest()
                return paths, hashes

            page.goto(BASE, wait_until="domcontentloaded")
            page.get_by_role("button", name="新建项目", exact=True).wait_for()
            check("Default opens real Workbench", page.get_by_role("heading", name="ASM Workbench", exact=True).count() == 1)
            edit(config, creating=True)
            check("Project configuration saved through UI", api("/api/projects/" + project_id + "/config")["config"]["plan"]["steps"] == ["web_visit"])
            before_preview_requests = list(fixture.requests)
            with page.expect_response(lambda response: urlsplit(response.url).path == "/api/projects/" + project_id + "/plan") as planned:
                page.get_by_role("button", name="预览执行计划", exact=True).click()
            plan = planned.value.json()
            page.get_by_test_id("plan-preview").wait_for()
            check("Plan preview uses actual tools params and permission", plan["steps"][0]["target"] == fixture_url and
                  plan["steps"][0]["tool"] == "target_http" and plan["steps"][0]["can_execute"] and
                  page.get_by_test_id("plan-preview").inner_text().find(plan["config_hash"]) >= 0)
            check("Preview does not start a run or send target HTTP", not api("/api/projects/" + project_id + "/run") and fixture.requests == before_preview_requests)
            page.set_viewport_size({"width": 390, "height": 844})
            preview_size = page.evaluate("() => ({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})")
            check("390px plan preview has no document overflow", preview_size["scroll"] <= preview_size["client"], preview_size)
            page.screenshot(path=str(artifact_dir / "390-plan.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 900})
            page.get_by_role("button", name="关闭计划预览", exact=True).click()
            first = start()
            completed = await_state(first, {"completed"})
            synchronize(first, "completed")
            check("Real plan called configured HTTP fixture", len(completed["steps"]) == 1 and completed["steps"][0]["tool"] == "target_http" and fixture.requests[0]["path"] == "/")
            check("Preview matches actual initial executed plan", [(s["capability"], s["tool"], s["target"], s["params"]) for s in plan["steps"]] ==
                  [(s["capability"], s["tool"], s["target"], s["params"]) for s in completed["steps"]])
            asset_section = page.locator(".wb-four > section").filter(has=page.get_by_role("heading", name="实时资产与观测", exact=True))
            check("Live observed title is visible", "UI Fixture /" in asset_section.inner_text() and len(completed["assets"]) == 1,
                  {"asset_title": completed["assets"][0]["title"], "visible_asset_text": asset_section.inner_text()})
            first_paths, first_hashes = report_links(first)
            check("One snapshot has both variants in three formats", len(first_paths) == 6 and {Path(path).suffix for path in first_paths} == {".csv", ".html", ".md"})
            check("Evidence tree includes checkpoint and raw HTTP receipt", page.locator(".wb-file a").filter(has_text="checkpoints/current.json").count() == 1 and page.locator(".wb-file a").filter(has_text="evidence/").count() > 0)

            run_dir = Path(completed["directory"])
            disk_calls = [json.loads(line) for line in (run_dir / "logs/tool-calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            calls_section = page.locator(".wb-four > section").filter(has=page.get_by_role("heading", name="工具调用日志", exact=True))
            ui_calls = [json.loads(text) for text in calls_section.locator("article.wb-event pre").all_inner_texts()]
            check("UI tool calls exactly match disk source", ui_calls == disk_calls, {"disk_count": len(disk_calls), "ui_count": len(ui_calls)})
            page.get_by_role("textbox", name="过滤文件树", exact=True).fill("logs/tool-calls.jsonl")
            page.locator(".wb-file").filter(has_text="logs/tool-calls.jsonl").get_by_role("button", name="预览", exact=True).click()
            file_preview = page.locator(".wb-detail .wb-preview")
            file_preview.wait_for()
            check("Evidence text preview reads actual file", json.loads(file_preview.inner_text().strip()) == disk_calls[0])
            page.get_by_role("button", name="复核证据", exact=True).first.click()
            page.get_by_role("textbox", name="复核依据", exact=True).fill("Reviewed owned loopback HTTP evidence; ownership remains unconfirmed")
            with page.expect_response(lambda response: urlsplit(response.url).path == "/api/runs/" + first + "/review") as reviewed_reply:
                page.get_by_role("button", name="保存复核记录", exact=True).click()
            reviewed = reviewed_reply.value.json()
            check("Manual review persists without promoting ownership verification or confidence", reviewed_reply.value.ok and reviewed["review_status"] == "reviewed" and
                  reviewed["verification_status"] == completed["assets"][0]["verification_status"] and reviewed["attribution_status"] == "unconfirmed" and
                  reviewed["corroboration_status"] == "unconfirmed")
            page.get_by_test_id("asset-review").wait_for(state="detached")
            page.get_by_role("textbox", name="过滤文件树", exact=True).fill("")

            before = api("/api/projects/" + project_id + "/config")
            page.get_by_role("textbox", name="新增调查范围", exact=True).fill("127.0.0.2/32")
            with page.expect_response(lambda response: urlsplit(response.url).path == "/api/projects/" + project_id + "/scope"):
                page.get_by_role("button", name="加入调查范围", exact=True).click()
            page.get_by_text("已加入调查范围。主动核实范围与逐功能权限仍需独立配置；继续运行处理未完成步骤。", exact=True).wait_for()
            after = api("/api/projects/" + project_id + "/config")
            check("Scope addition only changes investigation authorization", "127.0.0.2" in after["config"]["scope_sets"]["investigation"]["include"] and
                  all(before["config"]["scope_sets"][key] == after["config"]["scope_sets"][key] for key in ("verification", "extended")) and before["config"]["permissions"] == after["config"]["permissions"])

            # A natural SSE stream rollover must reconnect with a durable cursor.
            deadline = time.monotonic() + 19
            while len([item for item in sse if first in item["url"]]) < 2 and time.monotonic() < deadline:
                page.wait_for_timeout(150)
            first_sse = [item for item in sse if first in item["url"]]
            check("SSE reconnect supplies Last-Event-ID", len(first_sse) >= 2 and bool(first_sse[-1]["last_event_id"]), first_sse)
            event_ids = calls_section.locator("details .wb-event-top strong").all_text_contents()
            check("SSE reconnect does not duplicate displayed events", len(event_ids) == len(set(event_ids)), event_ids)

            for width, height in ((1440, 900), (390, 844)):
                page.set_viewport_size({"width": width, "height": height})
                size = page.evaluate("() => ({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})")
                check(str(width) + "px Workbench has no document overflow", size["scroll"] <= size["client"], size)
                page.screenshot(path=str(artifact_dir / (str(width) + "-completed.png")), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 900})

            control(first, "export", "创建交付快照")
            exported = state(first)
            check("Explicit snapshot creates new immutable version", exported["snapshot"]["snapshot_id"] != completed["snapshot"]["snapshot_id"] and all(
                sha256((run_dir / path).read_bytes()).hexdigest() == value for path, value in first_hashes.items()))
            check("Changed investigation scope prevents misleading snapshot comparison", exported["snapshot"]["comparison"]["status"] == "unavailable")
            control(first, "export", "创建交付快照")
            comparable = state(first)
            check("Snapshot comparison uses matching original plan and current permission", comparable["snapshot"]["comparison"]["status"] == "comparable")
            page.get_by_text("快照比较 · 有匹配的历史配置", exact=True).wait_for()
            # Induce a filesystem failure only in this harness's own run, then
            # restore every old snapshot. No shared/historical directory moves.
            exports = (run_dir / "exports").resolve()
            backup = (run_dir / "exports-fixture-backup").resolve()
            assert exports.parent == backup.parent == run_dir.resolve()
            assert run_dir.resolve().is_relative_to((ROOT / "report").resolve()) and run_dir.name == first
            exports.rename(backup)
            try:
                exports.write_text("owned fixture export failure", encoding="utf-8")
                control(first, "export", "创建交付快照")
                failed_delivery = state(first)
                check("Export failure retains old snapshot and exposes incomplete status", bool(failed_delivery["delivery_error"]) and
                      failed_delivery["snapshot"]["snapshot_id"] == comparable["snapshot"]["snapshot_id"])
                page.get_by_text("最近一次导出失败，交付不完整。", exact=True).wait_for()
                page.screenshot(path=str(artifact_dir / "export-incomplete.png"), full_page=True)
            finally:
                if exports.is_file():
                    assert exports.read_text(encoding="utf-8") == "owned fixture export failure"
                    exports.unlink()
                backup.rename(exports)
            control(first, "export", "创建交付快照")
            repaired = state(first)
            check("Successful re-export clears failure and preserves prior files", repaired["delivery_error"] is None and all(
                sha256((run_dir / path).read_bytes()).hexdigest() == value for path, value in first_hashes.items()))
            with page.expect_response(lambda response: urlsplit(response.url).path == "/api/runs/" + first + "/bundle") as bundled:
                page.get_by_role("button", name="生成完整证据包", exact=True).click()
            package = bundled.value.json()
            download_link = page.locator("a[download]")
            download_link.wait_for()
            packed_response = context.request.get(urljoin(BASE, download_link.get_attribute("href")))
            packed = packed_response.body()
            check("UI downloads complete immutable evidence bundle", packed_response.ok and packed.startswith(b"PK") and sha256(packed).hexdigest() == package["sha256"])
            with zipfile.ZipFile(io.BytesIO(packed)) as archive:
                metadata = json.loads(archive.read("bundle.json"))
                names = archive.namelist()
                check("Bundle includes both report variants shared evidence and frozen logs", sum(name.startswith("exports/") and
                    name.endswith((".html", ".md", ".csv")) and "/tables/" not in name for name in names) == 6 and
                    "logs/tool-calls.jsonl" in names and any("shared_evidence/" in name for name in names) and
                    all(sha256(archive.read(name)).hexdigest() == value["sha256"] for name, value in metadata["payloads"].items()))

            config["plan"]["params"]["web_visit"] = {"urls": [fixture_url, fixture_url + "/second", fixture_url + "/third"], "timeout_seconds": 3, "requests_per_second": 0.25}
            config["web"]["urls"] = config["plan"]["params"]["web_visit"]["urls"]
            edit(config)
            second = start()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                second_state = state(second)
                if any(step["status"] == "completed" for step in second_state["steps"]):
                    break
                page.wait_for_timeout(100)
            control(second, "pause", "暂停任务")
            paused = await_state(second, {"paused"})
            synchronize(second, "paused")
            request_count = len(fixture.requests)
            page.wait_for_timeout(1200)
            check("Pause persists checkpoint and halts new physical requests", len(fixture.requests) == request_count and (Path(paused["directory"]) / "checkpoints/current.json").is_file())
            paused_completed = {step["id"] for step in paused["steps"] if step["status"] == "completed"}
            control(second, "resume", "继续 / 中断恢复")
            resumed = await_state(second, {"completed"}, timeout=35)
            synchronize(second, "completed")
            check("Resume retains original run and completed step attempts", resumed["run_id"] == second and len(resumed["steps"]) == 3 and all(
                step["attempt"] == 1 for step in resumed["steps"] if step["id"] in paused_completed))
            second_calls = [json.loads(line) for line in (Path(resumed["directory"]) / "logs/tool-calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            check("Resume does not repeat completed HTTP actions", len(second_calls) == 3 and len({row["call_id"] for row in second_calls}) == 3)
            third = start()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not any(step["status"] == "completed" for step in state(third)["steps"]):
                page.wait_for_timeout(100)
            control(third, "stop", "停止并保留证据")
            stopped = await_state(third, {"stopped"})
            synchronize(third, "stopped")
            count_at_stop = len(fixture.requests)
            page.wait_for_timeout(1200)
            check("Stop retains evidence and exports complete truthful delivery", len(fixture.requests) == count_at_stop and stopped["snapshot"]["status"] == "complete" and len(stopped["assets"]) == 1)
            check("Stopped report manifest preserves run outcome", stopped["snapshot"]["run_status"] == "stopped")
            stop_paths, _ = report_links(third)
            check("Stopped run exports both report variants", len(stop_paths) == 6)
            if image_run_id:
                image_run = state(image_run_id)
                assert image_run["project_id"].startswith("lab_native_"), "Image verification accepts only known native local fixture projects"
                assert image_run["config"]["execution"]["target_local"] is True
                image_project_id = image_run["project_id"]
                page.get_by_role("button", name="项目列表", exact=True).click()
                page.get_by_role("tab", name="测试验收", exact=False).click()
                card = page.locator(".wb-project-card").filter(has_text=image_project_id)
                card.get_by_role("button", name="打开工作台", exact=True).click()
                page.wait_for_function("id => document.querySelector('.wb-panel.wb-run-summary')?.innerText.includes(id)", arg=image_run_id)
                native_tools = page.locator(".wb-tool").all_inner_texts()
                check("Saved native TCP UDP and screenshot calls are visible", {"tcp_scan", "udp_scan", "screenshot"}.issubset(
                    {step["capability"] for step in image_run["steps"] if step["status"] == "completed"}) and
                    all(any(label in text for text in native_tools) for label in ("TCP 端口", "UDP 端口", "网页截图")), native_tools)
                image_link = page.locator(".wb-report-links a").filter(has_text="professional/").filter(has_text=".html").first
                image_link.wait_for()
                with page.expect_popup() as opened:
                    image_link.click()
                popup = opened.value
                popup.on("pageerror", lambda error: errors.append(str(error)))
                popup.wait_for_load_state("domcontentloaded")
                image_count = popup.locator("img").count()
                if image_count:
                    popup.wait_for_function("() => [...document.images].every(image => image.complete)", timeout=15000)
                image_info = popup.locator("img").evaluate_all("images => images.map(image => ({src:image.currentSrc.startsWith('data:')?image.currentSrc.slice(0,30):image.currentSrc,embedded:image.currentSrc.startsWith('data:image/png;base64,'),complete:image.complete,width:image.naturalWidth,height:image.naturalHeight}))")
                check("Professional HTML opened from UI loads real saved PNG", image_count > 0 and all(
                    item["width"] > 0 and item["height"] > 0 and (item["embedded"] or urlsplit(item["src"]).hostname in {"localhost", "127.0.0.1"})
                    for item in image_info), image_info)
                png_links = popup.locator("a[href$='.png']").evaluate_all("anchors => [...new Set(anchors.map(anchor => anchor.href))]")
                downloaded = []
                for png_url in png_links:
                    parsed_png = urlsplit(png_url)
                    assert parsed_png.hostname in {"localhost", "127.0.0.1"}
                    assert "/api/runs/" + image_run_id + "/content/" in parsed_png.path
                    response = context.request.get(png_url)
                    raw = response.body()
                    downloaded.append({"url": png_url, "status": response.status, "bytes": len(raw),
                                       "sha256": sha256(raw).hexdigest(), "valid_png": response.ok and raw.startswith(b"\x89PNG\r\n\x1a\n")})
                check("Report original PNG links resolve through durable content path", bool(downloaded) and all(
                    item["valid_png"] and Path(urlsplit(item["url"]).path).stem == item["sha256"] for item in downloaded), downloaded)
                popup.screenshot(path=str(artifact_dir / "native-professional-png.png"), full_page=True)
                popup.close()
                evidence["image_report_run"] = {"run_id": image_run_id, "directory": image_run["directory"], "snapshot_id": image_run["snapshot"]["snapshot_id"]}
            check("No browser JavaScript errors", not errors, errors)
            check("No external browser request attempted", not blocked, blocked)
            check("No settings endpoint read", not forbidden_settings, forbidden_settings)
            current_project = api("/api/projects/" + project_id + "/config")
            evidence["project"] = {"project_id": project_id, "path": current_project["path"], "revision": current_project["revision"],
                                   "permission_version": current_project["config"].get("permission_version"),
                                   "permission_hash": current_project["config"].get("permission_hash")}
            evidence["runs"] = [{"run_id": item["run_id"], "status": item["status"], "directory": item["directory"],
                                 "snapshot_id": item["snapshot"]["snapshot_id"], "checkpoint": str(Path(item["directory"]) / "checkpoints/current.json"),
                                 "permission_version": item["config"].get("permission_version"), "permission_hash": item["config"].get("permission_hash")}
                                for item in (completed, resumed, stopped)]
            page.screenshot(path=str(artifact_dir / "1440-stopped.png"), full_page=True)
            context.close()
            browser.close()
    except Exception as error:
        errors.append(type(error).__name__ + ": " + str(error))
        checks["Harness completed all acceptance steps"] = False
        print(errors[-1], flush=True)
    finally:
        isolated.shutdown()
        isolated.server_close()
        fixture.shutdown()
        fixture.server_close()
        summary = {"checked_at": datetime.now(timezone.utc).isoformat(), "checks": checks, "evidence": evidence,
                   "errors": errors, "blocked_external_requests": blocked, "forbidden_settings": forbidden_settings,
                   "fixture": {"url": fixture_url, "requests": fixture.requests, "closed": True}, "output_directory": str(artifact_dir)}
        (artifact_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Evidence: " + str(artifact_dir / "summary.json"), flush=True)
    return 0 if checks and all(checks.values()) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-run", help="Existing completed lab_native fixture run with a saved PNG")
    args = parser.parse_args()
    raise SystemExit(main(args.image_run))
