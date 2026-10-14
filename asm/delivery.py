"""Local navigation and evidence-based comparison of frozen report snapshots."""
import hashlib
import html
import json
import uuid
from pathlib import Path
from urllib.parse import quote

from .run_store import digest, encode


def comparison_key(config, current):
    return digest({"mode": config.get("mode_preset"), "mode_version": config.get("mode_version"),
        "source": config.get("execution", {}).get("source"), "targets": config.get("targets"),
        "tools": config.get("tools"), "tool_lists": config.get("tool_lists"), "plan": config.get("plan"),
        "budgets": config.get("budgets"), "rates": config.get("rates"),
        "permissions": current.get("permissions"), "scopes": current.get("scope_sets")})


def snapshot_changes(snapshot, candidate_paths):
    for directory in candidate_paths:
        directory = Path(directory)
        try:
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            payload = (directory / "observations.snapshot.json").read_bytes()
            expected = next(f["sha256"] for f in manifest["files"] if f["path"] == "observations.snapshot.json" and f["status"] == "complete")
            if hashlib.sha256(payload).hexdigest() != expected:
                continue
            previous = json.loads(payload)
            if not previous.get("comparison_key") or previous["comparison_key"] != snapshot["comparison_key"]:
                continue
        except (OSError, ValueError, KeyError, StopIteration):
            continue
        before = {a["asset_id"]: a for a in previous.get("assets", []) if a.get("asset_id")}
        after = {a["asset_id"]: a for a in snapshot.get("assets", []) if a.get("asset_id")}
        fields = ("title", "service", "version", "http_status", "tls_protocol", "technology", "verification_status", "attribution_status", "scope_status", "review_status", "corroboration_status")
        changed, evidence_changed = [], []
        for key in sorted(before.keys() & after.keys()):
            changes = {field: {"previous": before[key].get(field), "current": after[key].get(field)}
                for field in fields if before[key].get(field) != after[key].get(field)}
            if changes:
                changed.append({"asset_id": key, "fields": changes})
            if set(before[key].get("evidence_ids", [])) != set(after[key].get("evidence_ids", [])):
                evidence_changed.append(key)
        return {"status": "comparable", "previous_run_id": previous.get("run_id"),
            "previous_snapshot_id": manifest["snapshot_id"], "previous_data_cutoff": previous.get("data_cutoff"),
            "comparison_key": snapshot["comparison_key"], "added_asset_ids": sorted(after.keys() - before.keys()),
            "not_reobserved_asset_ids": sorted(before.keys() - after.keys()), "changed_assets": changed,
            "changed_evidence_asset_ids": evidence_changed,
            "interpretation": "Recorded observations under matching plans, permissions and scopes. Not reobserved does not establish removal or remediation."}
    return {"status": "unavailable", "comparison_key": snapshot["comparison_key"],
        "reason": "no_valid_snapshot_with_matching_plan_permissions_and_scope"}


def _write(path, text):
    path = Path(path)
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _link(path, label):
    uri = "/".join(quote(part) for part in path.split("/"))
    return f'<a href="{html.escape(uri, quote=True)}">{html.escape(str(label))}</a>'


def _document(title, content):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' + \
        f'<title>{html.escape(title)}</title><style>body{{font:15px/1.7 system-ui;max-width:1000px;margin:32px auto;padding:16px;color:#19364a}}a{{color:#135c81}}li{{margin:10px 0;overflow-wrap:anywhere}}small{{color:#526779}}</style><h1>{html.escape(title)}</h1>' + content + "</html>"


def write_navigation(run, manifest, project_runs):
    directory = Path(run["directory"])
    snapshots = []
    for path in sorted((directory / "exports").glob("*/manifest.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            links = [_link(f"exports/{path.parent.name}/{f['path']}", f"{f['edition']} · {f['format']}")
                for f in data["files"] if f["edition"] in {"professional", "user_custom"}
                and "/tables/" not in f["path"] and f["status"] == "complete"]
            snapshots.append(f"<li><strong>{html.escape(data['snapshot_id'])}</strong> · {html.escape(data['status'])}<br>" + " · ".join(links) + "</li>")
        except (OSError, KeyError, ValueError):
            continue
    content = f"<p>运行 {html.escape(run['run_id'])} · 状态 {html.escape(run['status'])} · 当前快照 {html.escape(manifest['snapshot_id'])}</p>"
    content += "<p>每个链接指向独立冻结快照；检查manifest的数据截止时间与交付完整性。</p><ul>" + "".join(snapshots) + "</ul>"
    _write(directory / "index.html", _document("ASM 运行交付", content))
    rows = [_link(f"runs/{item['id']}/index.html", item["id"]) + " · " + html.escape(item["status"]) for item in project_runs]
    _write(directory.parents[1] / "index.html", _document("ASM 项目交付", "<ul>" + "".join("<li>" + item + "</li>" for item in rows) + "</ul>"))


def save_export_failure(run, error):
    failure = {"status": "incomplete", "run_id": run["run_id"], "reason": type(error).__name__}
    try:
        _write(Path(run["directory"]) / "delivery-error.json", encode(failure))
    except OSError:
        pass
    return failure
