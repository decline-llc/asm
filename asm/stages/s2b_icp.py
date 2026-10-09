import json
import re
from pathlib import Path

from ..models import Domain
from ..pipeline import StageResult
from ..utils.http import TargetHTTP

ICP_RE = re.compile(r"[\u4e00-\u9fff]{1,3}ICP(?:备|证)\s*\d{6,12}号?(?:-\d+)?", re.I)


def parse_icp(text):
    return sorted(set(re.sub(r"\s", "", m) for m in ICP_RE.findall(text)))


def branch(status, text=""):
    if status is None:
        return "expired_or_unreachable"
    if 300 <= status < 400:
        return "redirect"
    if status in {403, 503}:
        return "snapshot"
    return "footer" if status == 200 and parse_icp(text) else "snapshot"


def enumerate_subnumbers(records):
    """Only enumerate observed subnumbers; never invent other sites from a number."""
    groups = {}
    for number in records:
        base = re.sub(r"-\d+$", "", number)
        groups.setdefault(base, set()).add(number)
    return {k: sorted(v) for k, v in groups.items()}


def run(ctx):
    records = []
    import_file = ctx.config.get("icp", {}).get("import_file")
    if ctx.dry_run or import_file:
        path = ctx.profile.root / (import_file or "tests/fixtures/icp.json")
        records = json.loads(Path(path).read_text(encoding="utf-8"))
    elif not ctx.passive_only:
        http = TargetHTTP(ctx.scope, timeout=ctx.config.get("limits", {}).get("http_timeout", 15))
        try:
            for row in ctx.db.rows("SELECT domain FROM domains"):
                if not ctx.scope.contains(row["domain"]):
                    continue
                try:
                    reply = http.get("https://" + row["domain"])
                    records.append({"domain": row["domain"], "status": reply.status, "text": reply.text})
                except (OSError, RuntimeError) as exc:
                    ctx.note("icp_lookup", row["domain"], type(exc).__name__)
        finally:
            http.close()
    for row in records:
        numbers = parse_icp(row.get("text", ""))
        ctx.db.fact("icp:" + row["domain"], {"branch": branch(row.get("status"), row.get("text", "")),
                                            "numbers": numbers, "groups": enumerate_subnumbers(numbers)})
        for domain in row.get("related_domains", []):
            ctx.db.domain(Domain(domain, sources="icp", confidence="A"))
    ctx.write("icp.json", records)
    if not records:
        return StageResult("partial", notes=["Passive mode avoids target footer requests; import verified ICP export"])
    return StageResult(count=len(records))
