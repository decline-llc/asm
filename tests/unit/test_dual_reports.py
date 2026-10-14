import base64
import copy
import csv
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path
from urllib.parse import unquote

import pytest

from asm.reports import ASSET_FIELDS, CHAPTERS, TABLE_FIELDS, USER_HEADERS, export_snapshot


def png_bytes(color=17):
    def chunk(kind, content):
        return (struct.pack(">I", len(content)) + kind + content +
                struct.pack(">I", zlib.crc32(kind + content)))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes([0, color, 34, 51]))) + chunk(b"IEND", b""))


@pytest.fixture
def normalized(tmp_path):
    run = tmp_path / "runs" / "run-fixture"
    evidence = run / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "http.json").write_text('{"status":200,"title":"登录"}', encoding="utf-8")
    (evidence / "home.png").write_bytes(png_bytes())
    (evidence / "login.png").write_bytes(png_bytes(88))
    snapshot = {
        "project_id": "fixture-project", "run_id": "run-fixture", "status": "completed", "mode": "full_asm",
        "execution_source": "replay", "data_cutoff": "2026-10-11T00:00:00+00:00", "config_hash": "cfg-hash",
        "scope_revision": 2, "permission_revision": 3, "permissions": {"web_fetch": True},
        "scope": {"ips": ["127.0.0.1"]}, "usage": {"fixture_account": {"used": 2}},
        "assets": [{"asset_id": "a1", "asset_type": "web", "domain": "fixture.example.invalid",
                    "ip": "127.0.0.1", "protocol": "tcp", "port": 8443, "url": "https://127.0.0.1:8443/",
                    "title": "本地测试登录", "http_status": 200, "technology": ["fixture"],
                    "scope_status": "in_scope", "verification_status": "verified", "confidence": "A",
                    "organization": "人工测试主体", "attribution_status": "candidate", "evidence_ids": ["e1"],
                    "screenshot_path": "evidence/home.png", "login_screenshot_path": "evidence/login.png"},
                   {"asset_id": "a2", "domain": "outside.example.invalid", "scope_status": "out_of_scope",
                    "verification_status": "candidate", "remarks": "关联线索，需手动加入调查范围"},
                   {"asset_id": "a3", "domain": "isolated.example.invalid", "scope_status": "in_scope",
                    "quarantine": True, "verification_status": "candidate"}],
        "evidence": [{"evidence_id": "e1", "asset_id": "a1", "path": "evidence/http.json", "kind": "http"}],
        "coverage": [{"feature": "web_fetch", "status": "completed", "selected": True, "permitted": True},
                     {"feature": "udp_scan", "status": "permission_denied", "reason": "UDP 权限未授予"},
                     {"feature": "risk_checks", "status": "disabled", "reason": "用户未选择"}],
        "tables": {"execution_steps": [{"step_id": "step-1", "feature": "web_fetch", "tool": "fixture-http",
                                       "status": "completed", "params": {"timeout": 3}, "evidence_ids": ["e1"]}]},
        "audit": {"event_sequence": 8, "tool_log_sha256": "toolhash", "ledger_sha256": "ledgerhash"},
    }
    return run, snapshot


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.reader(stream))


@pytest.mark.parametrize("status", ["completed", "partial_failed", "stopped", "interrupted"])
def test_every_terminal_state_emits_six_files_and_eleven_three_format_tables(normalized, status):
    run, snapshot = normalized
    snapshot["status"] = status
    before = copy.deepcopy(snapshot)
    manifest = export_snapshot(run, snapshot)
    assert snapshot == before
    assert manifest["status"] == "complete"
    assert manifest["run_status"] == status
    export = Path(manifest["path"])
    for edition, stem, headers in (("professional", "专业调查报告", ASSET_FIELDS),
                                    ("user_custom", "资产梳理总结表", USER_HEADERS)):
        assert all((export / edition / f"{stem}.{suffix}").is_file() for suffix in ("csv", "html", "md"))
        csv_rows = read_csv(export / edition / f"{stem}.csv")
        assert csv_rows[0] == headers
        assert len(csv_rows) == 2
        assert (export / edition / f"{stem}.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert manifest["row_asset_ids"] == {"professional": {"1": "a1"}, "user_custom": {"1": "a1"}}
    assert manifest["main_asset_count"] == 1 and manifest["excluded_asset_count"] == 2
    assert len(list((export / "professional/tables").glob("*"))) == 33
    for name, headers in TABLE_FIELDS.items():
        assert read_csv(export / "professional/tables" / f"{name}.csv")[0][:len(headers)] == headers
    report = (export / "professional/专业调查报告.html").read_text(encoding="utf-8")
    assert report.count("<h2>") == 10
    assert all(chapter in report for chapter in CHAPTERS)
    assert "UDP 权限未授予" in report and "用户未选择" in report
    assert "没有可比历史快照依据" in report
    user = read_csv(export / "user_custom/资产梳理总结表.csv")[1]
    assert user[0] == "待确认"
    assert "登录页面截图" in user[4]
    assert "e1" in user[5]


def test_frozen_data_audit_hashes_and_old_delivery_survive_new_export(normalized):
    run, snapshot = normalized
    first = export_snapshot(run, snapshot, snapshot_id="snap-first")
    first_path = Path(first["path"])
    frozen_bytes = {path.relative_to(first_path).as_posix(): path.read_bytes() for path in first_path.rglob("*") if path.is_file()}
    frozen = json.loads((first_path / "observations.snapshot.json").read_text(encoding="utf-8"))
    audit = json.loads((first_path / "audit.snapshot.json").read_text(encoding="utf-8"))
    assert frozen["assets"][0]["screenshot_path"] == "evidence/home.png"
    assert audit["event_sequence"] == 8 and audit["permission_revision"] == 3
    assert audit["usage"] == snapshot["usage"]
    assert first["data_cutoff"] == snapshot["data_cutoff"]
    all_paths = {entry["path"] for entry in first["files"]}
    assert all_paths == set(frozen_bytes) - {"manifest.json"}
    for entry in first["files"]:
        payload = (first_path / entry["path"]).read_bytes()
        assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
        assert entry["size"] == len(payload)
    (run / "evidence/http.json").write_text('{"new":true}', encoding="utf-8")
    (run / "evidence/login.png").write_bytes(png_bytes(99))
    snapshot["permission_revision"] = 4
    snapshot["permissions"] = {"web_fetch": False}
    second = export_snapshot(run, snapshot, snapshot_id="snap-second")
    assert second["permission_revision"] == 4
    assert first["snapshot_id"] != second["snapshot_id"]
    assert frozen_bytes == {path.relative_to(first_path).as_posix(): path.read_bytes()
                            for path in first_path.rglob("*") if path.is_file()}
    with pytest.raises(FileExistsError):
        export_snapshot(run, snapshot, snapshot_id="snap-first")


def test_all_evidence_and_screenshot_links_resolve_offline_and_html_embeds_real_login(normalized):
    run, snapshot = normalized
    manifest = export_snapshot(run, snapshot)
    export = Path(manifest["path"])
    for file in export.rglob("*.html"):
        document = file.read_text(encoding="utf-8")
        assert "connect-src &#x27;none&#x27;" in document
        assert "<script" not in document
        for link in re.findall(r'href="([^"]+)"', document):
            assert (file.parent / unquote(link)).is_file()
        for source in re.findall(r'src="([^"]+)"', document):
            assert source.startswith("data:image/")
    for file in export.rglob("*.md"):
        for link in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding="utf-8")):
            assert (file.parent / unquote(link)).is_file()
    html = (export / "user_custom/资产梳理总结表.html").read_text(encoding="utf-8")
    assert base64.b64encode(png_bytes(88)).decode() in html
    assert base64.b64encode(png_bytes()).decode() not in html
    professional = read_csv(export / "professional/专业调查报告.csv")
    shot = professional[1][ASSET_FIELDS.index("screenshot_path")]
    assert (export / "professional" / shot).is_file()


def test_external_text_escaping_and_formula_defense_preserve_csv_fields(normalized):
    run, snapshot = normalized
    title = '\t=SUM(1,2), "引号"\n<script>alert(1)</script>|[x](javascript:alert(1))'
    snapshot["assets"][0]["title"] = title
    manifest = export_snapshot(run, snapshot)
    export = Path(manifest["path"])
    professional = read_csv(export / "professional/专业调查报告.csv")
    user = read_csv(export / "user_custom/资产梳理总结表.csv")
    assert professional[1][ASSET_FIELDS.index("title")] == "'" + title
    assert user[1][1] == "'" + title and len(user[1]) == 7
    assert len(professional[1]) == len(ASSET_FIELDS)
    for edition, stem in (("professional", "专业调查报告"), ("user_custom", "资产梳理总结表")):
        document = (export / edition / f"{stem}.html").read_text(encoding="utf-8")
        markdown = (export / edition / f"{stem}.md").read_text(encoding="utf-8")
        assert "<script>alert(1)</script>" not in document and "&lt;script&gt;" in document
        assert "[x](javascript:alert(1))" not in markdown
        assert "\\|" in markdown and "&lt;script&gt;" in markdown


def test_empty_table_reasons_distinguish_disabled_denied_failed_and_completed(tmp_path):
    snapshot = {"project_id": "empty", "run_id": "empty-run", "status": "partial_failed", "assets": [],
                "table_states": {"dns_observations": {"status": "permission_denied", "reason": "DNS 未获准"},
                                 "web_endpoints": "failed", "certificates": "completed", "findings": "disabled"}}
    manifest = export_snapshot(tmp_path, snapshot)
    export = Path(manifest["path"])
    for name in TABLE_FIELDS:
        assert read_csv(export / "professional/tables" / f"{name}.csv") == [TABLE_FIELDS[name]]
    states = manifest["empty_table_states"]
    assert states["dns_observations"] == "无权限：DNS 未获准"
    assert states["web_endpoints"] == "失败"
    assert states["certificates"] == "执行成功但无结果"
    assert states["findings"] == "未启用"
    assert "未采集" in states["organizations_relationships"]
    assert read_csv(export / "user_custom/资产梳理总结表.csv") == [USER_HEADERS]


def test_secrets_redacted_and_evidence_escape_and_env_are_never_read(normalized, monkeypatch, tmp_path):
    run, snapshot = normalized
    snapshot["audit"]["effective_config"] = {"FOFA_EMAIL": "secret@invalid", "FOFA_KEY": "KEY_SECRET",
                                              "nested": {"api_key": "ANOTHER_SECRET"}}
    snapshot["assets"][0]["remarks"] = "Authorization: Bearer BEARER_SECRET; token=TOKEN_SECRET"
    forbidden = run / ".env"
    escaped = tmp_path / "external-secret.json"
    forbidden.write_text("ENV_SECRET", encoding="utf-8")
    escaped.write_text("ESCAPED_SECRET", encoding="utf-8")
    original_read = Path.read_bytes

    def guarded(path):
        assert path.resolve() not in {forbidden.resolve(), escaped.resolve()}
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    snapshot["evidence"] += [{"evidence_id": "bad-env", "path": ".env"},
                             {"evidence_id": "bad-escape", "path": str(escaped)}]
    manifest = export_snapshot(run, snapshot)
    assert manifest["status"] == "incomplete"
    assert {row["status"] for row in manifest["shared_evidence"]} == {"available", "rejected"}
    export = Path(manifest["path"])
    for path in export.rglob("*"):
        if path.is_file():
            payload = original_read(path)
            assert all(secret.encode() not in payload for secret in
                       ["secret@invalid", "KEY_SECRET", "ANOTHER_SECRET", "BEARER_SECRET", "TOKEN_SECRET",
                        "ENV_SECRET", "ESCAPED_SECRET"])


def test_missing_and_corrupt_screenshots_are_visible_and_never_fabricated(normalized):
    run, snapshot = normalized
    asset = snapshot["assets"][0]
    asset.pop("login_screenshot_path")
    asset["screenshot_path"] = "evidence/missing.png"
    snapshot["assets"] += [{"asset_id": "corrupt", "scope_status": "in_scope",
                            "screenshot_path": "evidence/corrupt.png"}]
    (run / "evidence/corrupt.png").write_text("FAKE_SCREENSHOT", encoding="utf-8")
    manifest = export_snapshot(run, snapshot)
    assert manifest["status"] == "incomplete"
    export = Path(manifest["path"])
    user = (export / "user_custom/资产梳理总结表.html").read_text(encoding="utf-8")
    assert "无法作为图像显示" in user
    assert "data:image/" not in user and "FAKE_SCREENSHOT" not in user
    assert read_csv(export / "professional/专业调查报告.csv")[1][ASSET_FIELDS.index("screenshot_path")] == ""


def test_one_file_failure_is_recorded_while_other_formats_still_deliver(normalized, monkeypatch):
    import asm.reports as reports
    run, snapshot = normalized
    original = reports._write_csv

    def fail_one(path, headers, rows):
        if path.name == "专业调查报告.csv":
            raise PermissionError("fixture write denied")
        return original(path, headers, rows)

    monkeypatch.setattr(reports, "_write_csv", fail_one)
    manifest = export_snapshot(run, snapshot)
    assert manifest["status"] == "incomplete"
    assert any(row["path"] == "professional/专业调查报告.csv" and row["status"] == "failed"
               for row in manifest["files"])
    export = Path(manifest["path"])
    assert (export / "professional/专业调查报告.html").is_file()
    assert (export / "user_custom/资产梳理总结表.csv").is_file()
    assert json.loads((export / "manifest.json").read_text(encoding="utf-8"))["status"] == "incomplete"


def test_identical_assets_deduplicate_conflicting_ids_fail_and_unknown_scope_excluded(normalized):
    run, snapshot = normalized
    snapshot["assets"].append(copy.deepcopy(snapshot["assets"][0]))
    snapshot["assets"].append({"asset_id": "unknown", "domain": "unknown.example.invalid"})
    manifest = export_snapshot(run, snapshot)
    assert manifest["main_asset_count"] == 1 and manifest["excluded_asset_count"] == 3
    snapshot["assets"][-2]["title"] = "different observation needs collector merge"
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        export_snapshot(run, snapshot)


@pytest.mark.parametrize("identifier", ["../escape", "..", "/absolute", "bad\\path", ""])
def test_snapshot_id_cannot_escape_exports(normalized, identifier):
    run, snapshot = normalized
    with pytest.raises(ValueError, match="Invalid snapshot_id"):
        export_snapshot(run, snapshot, snapshot_id=identifier)


def test_no_screenshot_explains_feature_permission_without_new_requests(normalized):
    run, snapshot = normalized
    snapshot["assets"][0].pop("screenshot_path")
    snapshot["assets"][0].pop("login_screenshot_path")
    snapshot["coverage"].append({"feature": "screenshot", "status": "permission_denied", "reason": "截图范围为空"})
    result = export_snapshot(run, snapshot)
    rows = read_csv(Path(result["path"]) / "user_custom/资产梳理总结表.csv")
    assert "无权限" in rows[1][4] and "截图范围为空" in rows[1][4]
    assert rows[1][3] == "127.0.0.1"


@pytest.mark.parametrize("remote", ["https://fixture.invalid/a.png", "\\\\fixture.invalid\\share\\a.png",
                                   "//fixture.invalid/share/a.png"])
def test_remote_evidence_rejected_before_filesystem_resolution(normalized, monkeypatch, remote):
    run, snapshot = normalized
    original = Path.resolve

    def guarded(path, *args, **kwargs):
        assert "fixture.invalid" not in str(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", guarded)
    snapshot["evidence"].append({"evidence_id": "remote", "path": remote})
    manifest = export_snapshot(run, snapshot)
    assert manifest["status"] == "incomplete"
    record = next(row for row in manifest["shared_evidence"] if row["evidence_id"] == "remote")
    assert record["status"] == "rejected" and "不访问网络" in record["reason"]
