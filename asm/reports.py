"""Immutable, offline dual report exports from one normalized run snapshot.

``export_snapshot(run_dir, snapshot)`` accepts JSON-compatible mappings. Required
identifiers are project_id and run_id; assets carry asset_id and scope_status.
The optional tables mapping (or same-named top-level lists) supplies the eleven
classification tables. Missing data stays empty; coverage supplies the reason.
Evidence paths must point to existing files inside run_dir. They are copied by
content hash into the export so later execution cannot alter an old delivery.
This module never resolves a host, accesses a URL, starts a browser, or reads an
environment file. Callers must record sanitized tool output at collection time.
"""

from __future__ import annotations

import base64
import copy
import csv
import hashlib
import html
import json
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

SCHEMA_VERSION = "asm.snapshot.v1"
TEMPLATE_VERSION = "asm.dual-report.v2"
USER_HEADERS = ["归属", "名称", "链接", "IP(域名的可以解析一下)", "页面截图（优先放登录页面的）", "备注", "批量总结"]
ASSET_FIELDS = (
    "asset_id asset_type organization attribution_status attribution_evidence name domain ip protocol port url "
    "title http_status technology version environment sources first_seen observed_at last_verified_at "
    "verification_status confidence scope_status screenshot_path evidence_ids finding_ids remarks "
    "review_status corroboration_status review_evidence"
).split()
TABLE_FIELDS = {
    "scope_and_coverage": "feature target status reason selected permitted scope method ports source evidence_ids".split(),
    "organizations_relationships": "organization_id organization related_organization relationship attribution_status "
                                  "basis source observed_at evidence_ids remarks".split(),
    "domains": "asset_id domain registrable scope_status attribution_status verification_status sources "
               "first_seen observed_at evidence_ids remarks".split(),
    "dns_observations": "asset_id domain record_type value resolver observed_at execution_source status "
                        "cdn_geo_hint fake_ip evidence_ids remarks".split(),
    "ip_services": "asset_id ip protocol port service product version method execution_source observed_at "
                   "verification_status evidence_ids remarks".split(),
    "web_endpoints": "asset_id url http_status title technology page_kind screenshot_path method execution_source "
                     "observed_at verification_status evidence_ids remarks".split(),
    "certificates": "asset_id certificate_id host subject issuer serial fingerprint not_before not_after "
                    "sans observed_at source evidence_ids remarks".split(),
    "findings": "finding_id asset_id kind title severity status basis evidence_ids impact recommendation "
                "observed_at remarks".split(),
    "out_of_scope_leads": "asset_id name domain ip url relationship scope_status quarantine reason "
                          "evidence_ids next_step remarks".split(),
    "execution_steps": "step_id feature tool version status reason params started_at finished_at attempt_id "
                       "outputs evidence_ids".split(),
    "evidence_index": "evidence_id asset_id kind source_path path sha256 size observed_at status reason".split(),
}
TABLE_TITLES = {
    "scope_and_coverage": "范围与功能覆盖", "organizations_relationships": "主体与关系",
    "domains": "域名明细", "dns_observations": "DNS 观测", "ip_services": "IP、端口与服务",
    "web_endpoints": "Web 入口", "certificates": "证书", "findings": "暴露与风险核查",
    "out_of_scope_leads": "范围外与隔离线索", "execution_steps": "执行步骤", "evidence_index": "证据索引",
}
CHAPTERS = ["项目与执行摘要", "主体、归属与关系", "完整资产清单", "DNS/CDN/TLS", "端口与服务",
            "Web 与页面证据", "暴露与风险核查", "范围外与隔离线索", "执行与覆盖缺口", "证据、变化与后续计划"]
EMPTY_STATES = {
    "disabled": "未启用", "not_enabled": "未启用", "permission_denied": "无权限", "not_authorized": "无权限",
    "unauthorized": "无权限", "failed": "失败", "degraded": "部分失败或降级", "not_collected": "未采集",
    "pending": "未开始", "not_started": "未开始", "interrupted": "中断，待恢复", "stopped": "已停止",
    "not_selected": "未启用", "blocked": "受阻，未完成采集", "partial": "部分失败",
    "quota-exhausted": "配额耗尽，未完成采集", "skipped": "已跳过",
    "completed": "执行成功但无结果", "succeeded": "执行成功但无结果", "success": "执行成功但无结果",
}
TABLE_FEATURES = {
    "organizations_relationships": {"organization", "ownership", "supply_chain", "passive_search", "relationships",
                                    "company_lookup", "passive_supply_chain"},
    "domains": {"subdomain", "passive_search", "passive_subdomains", "dns_enumeration", "search", "dns_enum"},
    "dns_observations": {"dns", "dns_observation", "dns_enumeration", "dns_recursive", "dns_enum"},
    "ip_services": {"tcp", "udp", "ports", "tcp_scan", "udp_scan", "service_detection", "service_probe", "deep_service_probe"},
    "web_endpoints": {"web", "web_fetch", "screenshot", "web_screenshot", "crawl", "js_analysis", "path_discovery",
                      "web_visit", "web_crawl", "web_path_enum"},
    "certificates": {"tls", "tls_inspection", "passive_search", "certificate_search", "tls_inspect", "search"},
    "findings": {"exposure", "exposure_checks", "risk", "risk_checks", "exposure_check", "vulnerability_check",
                 "takeover_probe", "auth_audit"},
}
_SECRET_KEY = re.compile(r"(?:password|passwd|secret|token|credential|api[_-]?key|access[_-]?key|"
                         r"private[_-]?key|fofa[_-]?(?:key|email)|authorization)", re.I)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b((?:api[_-]?key|access[_-]?key|token|password|secret|fofa[_-]?(?:key|email))\s*[=:]\s*)([^\s&;,]+)"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _redact(value):
    if isinstance(value, Mapping):
        return {str(key): "[redacted]" if _SECRET_KEY.search(str(key)) else _redact(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", value)
        return _SECRET_ASSIGNMENT.sub(r"\1[redacted]", value)
    return value


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _csv_text(value) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", _text(value))
    return "'" + text if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else text


def _md(value) -> str:
    # Escaping HTML first also neutralizes raw tags and image/event markup.
    text = html.escape(_text(value), quote=True).replace("\r\n", "\n").replace("\r", "\n")
    for char in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", "!", "|"):
        text = text.replace(char, "\\" + char)
    return text.replace("\n", "<br>")


def _rows(snapshot, name) -> list[dict]:
    source = snapshot.get("tables", {}).get(name, snapshot.get(name, []))
    if source is None:
        return []
    if not isinstance(source, list) or not all(isinstance(row, Mapping) for row in source):
        raise ValueError(f"{name} must be a list of mappings")
    return [dict(row) for row in source]


def _asset_id(asset) -> str:
    explicit = asset.get("asset_id", asset.get("id"))
    if explicit is not None and str(explicit):
        return str(explicit)
    identity = {key: asset.get(key) for key in ("asset_type", "name", "domain", "ip", "protocol", "port", "url")}
    if not any(value not in (None, "") for value in identity.values()):
        raise ValueError("Asset lacks asset_id and identifying fields")
    return "asset-" + _sha(_json_bytes(identity))[:20]


def _in_scope(asset) -> bool:
    scoped = asset.get("scope_status") in {"in_scope", "in-scope", "in", "included"}
    quarantine = bool(asset.get("quarantine", asset.get("quarantined", False)))
    quarantine |= asset.get("verification_status") in {"quarantined", "quarantine", "isolated"}
    return scoped and not quarantine and asset.get("review_status") != "excluded"


def _unique_assets(snapshot) -> list[dict]:
    source = snapshot.get("assets", [])
    if not isinstance(source, list) or not all(isinstance(row, Mapping) for row in source):
        raise ValueError("assets must be a list of mappings")
    assets = {}
    for supplied in source:
        asset = dict(supplied)
        identifier = _asset_id(asset)
        asset["asset_id"] = identifier
        if identifier in assets and assets[identifier] != asset:
            # The collector must merge conflicting observations, not the report template.
            raise ValueError(f"Conflicting duplicate asset_id: {identifier}")
        assets[identifier] = asset
    return list(assets.values())


def _empty_reason(snapshot, table) -> str:
    explicit = snapshot.get("table_states", {}).get(table)
    if explicit:
        if isinstance(explicit, Mapping):
            state = EMPTY_STATES.get(explicit.get("status"), _text(explicit.get("status")))
            return state + ("：" + _text(explicit.get("reason")) if explicit.get("reason") else "")
        return EMPTY_STATES.get(str(explicit), str(explicit))
    coverage = snapshot.get("coverage", [])
    relevant = [row for row in coverage if row.get("table") == table or
                row.get("feature") in TABLE_FEATURES.get(table, set())]
    if relevant:
        return "；".join(dict.fromkeys(
            EMPTY_STATES.get(row.get("status"), _text(row.get("status")) or "未采集") +
            ("：" + _text(row.get("reason")) if row.get("reason") else "") for row in relevant))
    return "未采集（没有对应执行观测；空表不代表无资产或无风险）"


def _image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 33 and data[12:16] == b"IHDR":
        return "png"
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 13:
        return "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return None


class _EvidenceStore:
    def __init__(self, run_dir: Path, export_dir: Path):
        self.root = run_dir.resolve()
        self.export_dir = export_dir
        self.records: list[dict] = []
        self.by_source: dict[str, dict] = {}
        self.images: dict[str, bytes] = {}

    def capture(self, raw_path, *, evidence_id="", kind="", asset_id="", require_image=False) -> dict:
        supplied = _text(raw_path)
        record = {"evidence_id": str(evidence_id), "asset_id": str(asset_id), "kind": kind,
                  "source_path": supplied, "path": "", "sha256": "", "size": "", "status": "missing", "reason": ""}
        if not supplied:
            record["reason"] = "未采集文件"
            self.records.append(record)
            return record
        if supplied.startswith(("\\\\", "//")) or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", supplied):
            record.update(status="rejected", reason="离线报告不访问网络文件或远程 URL")
            self.records.append(record)
            return record
        source = Path(supplied)
        if not source.is_absolute():
            source = self.root / source
        try:
            if any(part.lower() == ".env" or part.lower().startswith(".env.") for part in source.parts):
                raise ValueError("秘密配置不得作为证据导出")
            source = source.resolve()
            source.relative_to(self.root)
            if any(part.lower() == ".env" or part.lower().startswith(".env.") for part in source.parts):
                raise ValueError("秘密配置不得作为证据导出")
            if self.export_dir == source or self.export_dir in source.parents:
                raise ValueError("新快照不能引用自身输出")
        except (ValueError, OSError):
            record.update(status="rejected", reason="路径不属于运行目录，或指向秘密配置/新快照")
            self.records.append(record)
            return record
        try:
            data = source.read_bytes()
            image_type = _image_type(data)
            if require_image and image_type is None:
                raise ValueError("截图文件无法作为图像显示")
            digest = _sha(data)
            # Preserve harmless evidence extensions; no HTML is embedded or executed.
            suffix = "." + image_type if require_image else source.suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
                suffix = ".bin"
            relative = f"shared_evidence/{digest}{suffix}"
            destination = self.export_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                with destination.open("xb") as stream:
                    stream.write(data)
            elif destination.read_bytes() != data:
                raise ValueError("同名证据校验失败")
            record.update(path=relative, sha256=digest, size=len(data), status="available")
            if require_image:
                self.images[relative] = data
        except (OSError, ValueError) as error:
            record.update(status="missing", reason=str(error))
        self.records.append(record)
        self.by_source[supplied] = record
        return record


def _relative(snapshot_path: str, output: Path, export_dir: Path) -> str:
    return Path(os.path.relpath(export_dir / snapshot_path, output.parent)).as_posix()


def _html_table(headers, rows) -> str:
    head = "".join(f"<th>{html.escape(str(header), quote=True)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(_text(cell), quote=True)}</td>" for cell in row) + "</tr>"
                   for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _md_table(headers, rows) -> str:
    lines = ["| " + " | ".join(_md(header) for header in headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(_md(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def _html_document(title, content) -> str:
    escaped = html.escape(title, quote=True)
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{escaped}</title>'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src &#x27;none&#x27;; '
            'img-src data:; style-src &#x27;unsafe-inline&#x27;; base-uri &#x27;none&#x27;; '
            'form-action &#x27;none&#x27;; connect-src &#x27;none&#x27;">'
            '<style>body{font:15px/1.6 system-ui,sans-serif;color:#182b41;background:#f3f6fa;margin:0;}'
            'main{max-width:1440px;margin:auto;padding:32px;background:white;}h1,h2{color:#163b63;}'
            '.table-wrap{overflow:auto;margin:16px 0}table{border-collapse:collapse;width:100%;}'
            'th,td{border:1px solid #c7d3df;padding:9px;vertical-align:top;overflow-wrap:anywhere;}'
            'th{background:#e8eff7;text-align:left;}figure{margin:18px 0;}img{max-width:100%;max-height:720px;}'
            'a{color:#154f8b}p{overflow-wrap:anywhere}.status{padding:12px;background:#edf3f9;}'
            '@media(max-width:600px){main{padding:12px}}@media print{main{padding:0}.table-wrap{overflow:visible}}'
            f'</style></head><body><main><h1>{escaped}</h1>{content}</main></body></html>')


def _write_csv(path, headers, rows):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows([_csv_text(cell) for cell in row] for row in rows)


def _write_text(path, text):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def _summary(snapshot, assets, excluded) -> list[tuple[str, object]]:
    states = {}
    for asset in assets:
        state = asset.get("verification_status") or "未标注核实状态"
        states[state] = states.get(state, 0) + 1
    return [("项目", snapshot.get("project_id")), ("目标", snapshot.get("target", snapshot.get("targets", ""))),
            ("权限模式", snapshot.get("mode")), ("执行来源", snapshot.get("execution_source")),
            ("运行 ID", snapshot.get("run_id")), ("运行状态", snapshot.get("status")),
            ("开始时间", snapshot.get("started_at")), ("结束时间", snapshot.get("finished_at")),
            ("数据截止时间", snapshot.get("data_cutoff")), ("配置哈希", snapshot.get("config_hash")),
            ("范围版本", snapshot.get("scope_revision")), ("权限版本", snapshot.get("permission_revision")),
            ("逐功能权限", snapshot.get("permissions", {})), ("调查范围", snapshot.get("scope", {})),
            ("预算", snapshot.get("budget", {})), ("实际用量", snapshot.get("usage", {})),
            ("主表资产数量", len(assets)), ("主表核实状态数量", states), ("范围外/隔离/未确定范围数量", len(excluded)),
            ("统计口径", "统一 asset_id 去重；仅调查范围内且未隔离资产进入两版主表；来源置信度不等于已核实。")]


def _value_rows(headers, records, output, export_dir):
    rows = []
    for record in records:
        values = []
        for field in headers:
            value = record.get(field)
            if field in {"path", "screenshot_path"} and value and str(value).startswith("shared_evidence/"):
                value = _relative(str(value), output, export_dir)
            values.append(value)
        rows.append(values)
    return rows


def _link_sections(output, export_dir, evidence, screenshots, *, markdown=False) -> str:
    pieces = []
    seen = set()
    for record in evidence:
        path = record.get("path")
        if not path or path in seen:
            continue
        seen.add(path)
        link = quote(_relative(path, output, export_dir), safe="/-._~")
        label = record.get("evidence_id") or record.get("kind") or "原始证据"
        if markdown:
            pieces.append(f"- [{_md(label)}]({link}) · SHA-256: `{record['sha256']}`")
        else:
            pieces.append(f'<p><a href="{html.escape(link, quote=True)}">{html.escape(label, quote=True)}</a>'
                          f' · SHA-256: {record["sha256"]}</p>')
    for asset_id, record in screenshots.items():
        if record.get("status") != "available":
            continue
        link = quote(_relative(record["path"], output, export_dir), safe="/-._~")
        caption = f"资产 {asset_id}：{record['caption']}"
        if markdown:
            pieces.append(f"\n![{_md(caption)}]({link})\n")
        else:
            data = (export_dir / record["path"]).read_bytes()
            mime = _image_type(data)
            pieces.append(f'<figure><figcaption>{html.escape(caption, quote=True)}</figcaption>'
                          f'<a href="{html.escape(link, quote=True)}">截图原文件</a>'
                          f'<br><img alt="{html.escape(caption, quote=True)}" '
                          f'src="data:image/{mime};base64,{base64.b64encode(data).decode()}"></figure>')
    return "\n".join(pieces)


def _professional(snapshot, assets, excluded, tables, output, export_dir, evidence, screenshots, *, markdown=False):
    summary = _summary(snapshot, assets, excluded)
    chapter_tables = {
        1: ["organizations_relationships"], 2: [], 3: ["dns_observations", "certificates"],
        4: ["ip_services"], 5: ["web_endpoints"], 6: ["findings"], 7: ["out_of_scope_leads"],
        8: ["scope_and_coverage", "execution_steps"], 9: ["evidence_index"],
    }
    sections = []
    for index, title in enumerate(CHAPTERS):
        heading = f"{index + 1}. {title}"
        sections.append(f"\n## {heading}\n" if markdown else f"<h2>{heading}</h2>")
        if index == 0:
            sections.append(_md_table(["项目", "值"], summary) if markdown else _html_table(["项目", "值"], summary))
        if index == 2:
            rows = _value_rows(ASSET_FIELDS, assets, output, export_dir)
            sections.append(_md_table(ASSET_FIELDS, rows) if markdown else _html_table(ASSET_FIELDS, rows))
            note = "空值表示快照未提供对应事实；资产的多次、多源观测见分类表。"
            sections.append(_md(note) + "\n" if markdown else f"<p>{note}</p>")
            sections.append(_render_table("domains", tables["domains"], snapshot, output, export_dir, markdown))
        for name in chapter_tables.get(index, []):
            sections.append(_render_table(name, tables[name], snapshot, output, export_dir, markdown))
        if index == 6:
            note = "观测、推断、候选与已核实以记录状态区分；版本指纹、登录页或检测命中不自行构成已确认漏洞。"
            sections.append(_md(note) + "\n" if markdown else f"<p>{note}</p>")
        if index == 9:
            changes = snapshot.get("changes")
            note = _text(changes) if changes else "没有可比历史快照依据，未计算新增、移除或变化。"
            todo = _text(snapshot.get("next_steps")) or "待办由实际覆盖缺口、失败/中断步骤及待核实线索确定。"
            sections.append(_md(note) + "\n\n" + _md(todo) + "\n" if markdown else
                            f"<p>{html.escape(note, quote=True)}</p><p>{html.escape(todo, quote=True)}</p>")
            sections.append(_link_sections(output, export_dir, evidence, screenshots, markdown=markdown))
    content = "\n".join(sections)
    return "# 专业调查报告\n" + content if markdown else _html_document("专业调查报告", content)


def _render_table(name, records, snapshot, output, export_dir, markdown):
    headers = list(TABLE_FIELDS[name])
    # Preserve supplied facts beyond the stable minimum table schema.
    headers += sorted(set().union(*(set(row) for row in records)) - set(headers)) if records else []
    rows = _value_rows(headers, records, output, export_dir)
    title = TABLE_TITLES[name]
    if markdown:
        content = f"\n### {title}\n\n" + _md_table(headers, rows)
        if not rows:
            content += "\n" + _md(_empty_reason(snapshot, name)) + "\n"
        return content
    content = f"<h3>{title}</h3>" + _html_table(headers, rows)
    if not rows:
        content += f'<p class="status">{html.escape(_empty_reason(snapshot, name), quote=True)}</p>'
    return content


def _user_rows(assets, screenshots, output, export_dir, screenshot_reason="未采集截图"):
    rows = []
    for asset in assets:
        identifier = asset["asset_id"]
        shot = screenshots.get(identifier, {})
        caption = shot.get("caption", asset.get("screenshot_reason") or screenshot_reason)
        if shot.get("path"):
            caption += "；" + _relative(shot["path"], output, export_dir)
        elif shot.get("reason"):
            caption += "：" + shot["reason"]
        attributed = asset.get("attribution_status") in {"verified", "confirmed", "已核实", "已确认"}
        organization = asset.get("organization") if attributed and asset.get("organization") else "待确认"
        name = asset.get("title") or asset.get("name") or asset.get("domain") or asset.get("ip") or ""
        if not asset.get("title") and asset.get("name_source") == "manual":
            name = _text(name) + "（人工标签）"
        state = asset.get("verification_status") or "未标注核实状态"
        remarks = asset.get("remarks") or ""
        evidence_ids = _text(asset.get("evidence_ids"))
        remark = f"核实状态：{state}；证据：{evidence_ids or '未关联'}"
        if remarks:
            remark += "；" + _text(remarks)
        if asset.get("manual_review"):
            remark += "；人工复核：" + _text(asset.get("review_status")) + "；佐证状态：" + _text(asset.get("corroboration_status"))
            remark += "；复核依据：" + _text(asset["manual_review"].get("note"))
        batch = asset.get("batch_summary") or f"资产 ID：{identifier}；归属状态：{asset.get('attribution_status') or '待确认'}"
        # Only observed fields are presented. Never synthesize a URL or resolve an IP.
        rows.append([organization, name, asset.get("url"), asset.get("ip"), caption, remark, batch])
    return rows


def export_snapshot(run_dir: Path | str, snapshot: Mapping, *, snapshot_id: str | None = None) -> dict:
    """Write a new append-only delivery and return its manifest including ``path``.

    A repeated explicit snapshot_id raises FileExistsError. Individual file
    write failures are retained in manifest.files and produce status=incomplete;
    a failure to reserve the directory or write the manifest raises OSError.
    No live action or secret configuration lookup is performed here.
    """
    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot must be a mapping")
    data = _redact(copy.deepcopy(dict(snapshot)))
    for field in ("project_id", "run_id"):
        if not data.get(field):
            raise ValueError(f"Missing {field}")
    data.setdefault("data_cutoff", _now())
    data.setdefault("status", "interrupted")
    data.setdefault("coverage", [])
    data.setdefault("tables", {})
    if not isinstance(data["coverage"], list) or not all(isinstance(row, Mapping) for row in data["coverage"]):
        raise ValueError("coverage must be a list of mappings")
    if not isinstance(data["tables"], Mapping):
        raise ValueError("tables must be a mapping")
    if not isinstance(data.get("audit", {}), Mapping):
        raise ValueError("audit must be a mapping")
    # Validate serializability and input tables before reserving an export ID.
    _json_bytes(data)
    all_assets = _unique_assets(data)
    assets = [asset for asset in all_assets if _in_scope(asset)]
    excluded = [asset for asset in all_assets if not _in_scope(asset)]
    tables = {name: _rows(data, name) for name in TABLE_FIELDS}
    evidence_sources = data.get("evidence", tables["evidence_index"])
    if not isinstance(evidence_sources, list) or not all(isinstance(row, Mapping) for row in evidence_sources):
        raise ValueError("evidence must be a list of mappings")
    if data["coverage"]:
        tables["scope_and_coverage"] += [dict(row) for row in data["coverage"]
                                         if row not in tables["scope_and_coverage"]]
    if not tables["domains"]:
        tables["domains"] = [dict(asset) for asset in all_assets if asset.get("domain") or asset.get("asset_type") == "domain"]
    if not tables["ip_services"]:
        tables["ip_services"] = [dict(asset) for asset in all_assets if asset.get("ip") and asset.get("port") is not None]
    if not tables["web_endpoints"]:
        tables["web_endpoints"] = [dict(asset) for asset in all_assets if asset.get("url")]
    for asset in excluded:
        if not any(str(row.get("asset_id")) == asset["asset_id"] for row in tables["out_of_scope_leads"]):
            tables["out_of_scope_leads"].append({**asset, "reason":
                "人工排除：" + asset.get("manual_review", {}).get("note", "") if asset.get("review_status") == "excluded"
                else asset.get("scope_reason") or "范围外、隔离或调查范围未确认；不计入主表"})
    if str(run_dir).startswith(("\\\\", "//")):
        raise ValueError("Offline export run_dir must be local")
    run_dir = Path(run_dir)
    identifier = snapshot_id if snapshot_id is not None else \
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:12]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", identifier) or identifier in {".", ".."}:
        raise ValueError("Invalid snapshot_id")
    output = run_dir / "exports" / identifier
    output.mkdir(parents=True, exist_ok=False)
    evidence_store = _EvidenceStore(run_dir, output)
    for evidence in evidence_sources:
        captured = evidence_store.capture(evidence.get("path", evidence.get("source_path")),
                                          evidence_id=evidence.get("evidence_id", evidence.get("id", "")),
                                          kind=evidence.get("kind", ""), asset_id=evidence.get("asset_id", ""))
        for key in ("observed_at", "source", "provenance"):
            if key in evidence:
                captured[key] = evidence[key]
    screenshots = {}
    for asset in all_assets:
        login = asset.get("login_screenshot_path")
        shot_path = login or asset.get("screenshot_path")
        if not shot_path:
            continue
        captured = evidence_store.capture(shot_path, kind="screenshot", asset_id=asset["asset_id"], require_image=True,
                                          evidence_id=asset.get("screenshot_evidence_id", ""))
        caption = "登录页面截图" if login or asset.get("screenshot_kind") == "login" else "首页截图，未取得登录页"
        screenshots[asset["asset_id"]] = {**captured, "caption": caption}
        # Canonical facts retain their original pointer in observations.snapshot;
        # presentation rows use the immutable exported file.
        asset["screenshot_path"] = captured["path"]
    tables["evidence_index"] = evidence_store.records
    for row in tables["web_endpoints"]:
        shot_path = row.get("screenshot_path")
        if shot_path:
            captured = evidence_store.by_source.get(str(shot_path))
            if captured is None:
                captured = evidence_store.capture(shot_path, kind="screenshot", asset_id=row.get("asset_id", ""),
                                                  require_image=True)
            row["screenshot_path"] = captured["path"]
    empty_states = {name: _empty_reason(data, name) for name, rows in tables.items() if not rows}
    screenshot_coverage = [row for row in data["coverage"] if row.get("feature") in {"screenshot", "web_screenshot"}]
    screenshot_reason = "未采集截图"
    if screenshot_coverage:
        screenshot_reason += "：" + "；".join(
            EMPTY_STATES.get(row.get("status"), _text(row.get("status"))) +
            ("，" + _text(row.get("reason")) if row.get("reason") else "") for row in screenshot_coverage)
    manifest = {
        "schema_version": SCHEMA_VERSION, "template_version": TEMPLATE_VERSION,
        "project_id": data["project_id"], "run_id": data["run_id"], "snapshot_id": identifier,
        "path": str(output.resolve()), "status": "complete", "run_status": data["status"],
        "created_at": _now(), "data_cutoff": data["data_cutoff"], "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"), "config_hash": data.get("config_hash", ""),
        "scope_revision": data.get("scope_revision"), "permission_revision": data.get("permission_revision"),
        "mode": data.get("mode"), "execution_source": data.get("execution_source"),
        "coverage": data["coverage"], "usage": data.get("usage", {}), "table_counts": {},
        "comparison": data.get("changes", {"status": "unavailable"}),
        "empty_table_states": empty_states, "main_asset_count": len(assets), "excluded_asset_count": len(excluded),
        "row_asset_ids": {"professional": {str(index): asset["asset_id"] for index, asset in enumerate(assets, 1)},
                          "user_custom": {str(index): asset["asset_id"] for index, asset in enumerate(assets, 1)}},
        "shared_evidence": evidence_store.records, "files": [], "errors": [],
        "hash_policy": "SHA-256 for every exported payload and shared evidence; manifest excludes its own recursive hash",
    }

    def emit(path: Path, producer, *, edition="snapshot", format="json", rows=None):
        entry = {"path": path.relative_to(output).as_posix(), "edition": edition, "format": format,
                 "status": "pending", "sha256": "", "size": 0}
        if rows is not None:
            entry["rows"] = rows
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            producer(path)
            payload = path.read_bytes()
            entry.update(status="complete", sha256=_sha(payload), size=len(payload))
        except (OSError, ValueError) as error:
            entry.update(status="failed", reason=str(error))
            # A disk-full/late-write failure may leave a partial payload. Keep
            # its checksum when readable, while still recording a failed file.
            try:
                if path.is_file():
                    partial = path.read_bytes()
                    entry.update(sha256=_sha(partial), size=len(partial), partial=True)
            except OSError:
                entry["checksum_status"] = "unavailable_after_write_failure"
            manifest["errors"].append({"path": entry["path"], "reason": str(error)})
            manifest["status"] = "incomplete"
        manifest["files"].append(entry)

    frozen = {**data, "assets": [dict(asset) for asset in _unique_assets(data)],
              "exported_evidence": evidence_store.records}
    emit(output / "observations.snapshot.json", lambda path: _write_text(path, _json_bytes(frozen).decode()))
    audit = {**data.get("audit", {}), "data_cutoff": data["data_cutoff"], "config_hash": data.get("config_hash", ""),
             "scope_revision": data.get("scope_revision"), "permission_revision": data.get("permission_revision"),
             "usage": data.get("usage", {}), "coverage": data["coverage"]}
    emit(output / "audit.snapshot.json", lambda path: _write_text(path, _json_bytes(audit).decode()))
    for edition, stem in (("professional", "专业调查报告"), ("user_custom", "资产梳理总结表")):
        for format in ("csv", "html", "md"):
            path = output / edition / f"{stem}.{format}"
            if format == "csv":
                headers = ASSET_FIELDS if edition == "professional" else USER_HEADERS
                rows = _value_rows(ASSET_FIELDS, assets, path, output) if edition == "professional" else \
                    _user_rows(assets, screenshots, path, output, screenshot_reason)
                emit(path, lambda file, heads=headers, values=rows: _write_csv(file, heads, values),
                     edition=edition, format=format, rows=len(assets))
            elif edition == "professional":
                emit(path, lambda file, fmt=format: _write_text(file, _professional(
                    data, assets, excluded, tables, file, output, evidence_store.records, screenshots,
                    markdown=fmt == "md")), edition=edition, format=format, rows=len(assets))
            else:
                summary = _summary(data, assets, excluded)
                rows = _user_rows(assets, screenshots, path, output, screenshot_reason)
                if format == "md":
                    content = "# 资产梳理总结表\n\n" + _md_table(["项目", "值"], summary) + "\n" + _md_table(USER_HEADERS, rows)
                    content += "\n## 覆盖缺口与表外线索\n\n" + _render_table(
                        "scope_and_coverage", tables["scope_and_coverage"], data, path, output, True)
                    content += "\n范围外/隔离/未确认调查范围线索数：" + str(len(excluded)) + "；明细见专业报告。\n"
                    content += "\n## 证据与截图\n\n" + _link_sections(path, output, evidence_store.records, screenshots, markdown=True)
                else:
                    content = _html_table(["项目", "值"], summary) + _html_table(USER_HEADERS, rows)
                    content += "<h2>覆盖缺口与表外线索</h2>" + _render_table(
                        "scope_and_coverage", tables["scope_and_coverage"], data, path, output, False)
                    content += f"<p>范围外/隔离/未确认调查范围线索数：{len(excluded)}；明细见专业报告。</p>"
                    content += "<h2>证据与截图</h2>" + _link_sections(path, output, evidence_store.records, screenshots)
                    content = _html_document("资产梳理总结表", content)
                emit(path, lambda file, text=content: _write_text(file, text), edition=edition, format=format, rows=len(assets))
    for name, records in tables.items():
        manifest["table_counts"][name] = len(records)
        for format in ("csv", "html", "md"):
            path = output / "professional" / "tables" / f"{name}.{format}"
            if format == "csv":
                heads = TABLE_FIELDS[name] + sorted(set().union(*(set(row) for row in records)) - set(TABLE_FIELDS[name])) \
                    if records else TABLE_FIELDS[name]
                values = _value_rows(heads, records, path, output)
                emit(path, lambda file, headers=heads, rows=values: _write_csv(file, headers, rows),
                     edition="professional", format=format, rows=len(records))
            else:
                content = _render_table(name, records, data, path, output, format == "md")
                if name in {"evidence_index", "web_endpoints"}:
                    content += _link_sections(path, output, evidence_store.records, screenshots, markdown=format == "md")
                if format == "html":
                    content = _html_document(TABLE_TITLES[name], content)
                emit(path, lambda file, text=content: _write_text(file, text), edition="professional", format=format, rows=len(records))
    seen_paths = set()
    for evidence in evidence_store.records:
        if evidence.get("path") and evidence["path"] not in seen_paths:
            seen_paths.add(evidence["path"])
            manifest["files"].append({"path": evidence["path"], "edition": "shared_evidence", "format": "binary",
                                      "status": "complete", "sha256": evidence["sha256"], "size": evidence["size"]})
        elif evidence["status"] != "available":
            # Missing referenced evidence is visible and cannot be declared a full delivery.
            manifest["status"] = "incomplete"
            manifest["errors"].append({"evidence_id": evidence.get("evidence_id", ""), "source_path": evidence["source_path"],
                                       "reason": evidence["reason"]})
    _write_text(output / "manifest.json", _json_bytes(manifest).decode())
    return manifest
