import json
from pathlib import Path

from ..browser.xiaolanben import Xiaolanben
from ..pipeline import StageResult


def run(ctx):
    source = ctx.config.get("equity", {}).get("import_file")
    if ctx.dry_run:
        records = Xiaolanben().replay(ctx.profile.root / "tests/fixtures/equity.json")
    elif source:
        path = Path(source)
        if not path.is_absolute():
            path = ctx.profile.root / path
        records = json.loads(path.read_text(encoding="utf-8"))
    else:
        ctx.note("manual_equity", ctx.config.get("targets", {}).get("company", ""),
                 "Supervised browsing/export required; configure equity.import_file. No fixture data imported.")
        return StageResult("partial", notes=["Awaiting supervised equity export"])
    accepted = {r["cid"] for r in records if not r.get("parent_cid")}
    pending, output = list(records), []
    for _ in range(len(records) + 1):
        progress = False
        for item in list(pending):
            parent = item.get("parent_cid")
            if parent and (parent not in accepted or float(item.get("share_pct") or 0) < 51):
                continue
            data = {k: v for k, v in item.items() if k in ctx.db.columns["companies"]}
            data["website"] = data.get("website") or None
            ctx.db.upsert("companies", data, ("cid",), merge=True)
            accepted.add(item["cid"])
            output.append(data)
            pending.remove(item)
            progress = True
        if not progress:
            break
    suffixes = {r.get("email_suffix") for r in output if r.get("email_suffix")}
    ctx.db.fact("shared_email_management", next(iter(suffixes)) if len(suffixes) == 1 else None)
    ctx.write("companies.json", output)
    return StageResult(count=len(output))
