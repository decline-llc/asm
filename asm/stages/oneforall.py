"""Submission and evidence ingestion for the isolated native passive collector."""
import json
import re
from pathlib import Path

from ..models import Domain
from ..utils.oneforall import PASSIVE_FLAGS, OneForAllSettings, domain_name


def submit(ctx, root, settings):
    ctx.scope.assert_in_scope(root, active=False)
    root = domain_name(root)
    vendor = ctx.bridge.workspace + "/tools/OneForAll"
    lock = json.loads((ctx.profile.root / "tools/tool-lock.json").read_text(encoding="utf-8"))
    plan = {"root": root, "vendor": vendor, "settings": settings.as_config(),
            "expected_commit": lock["source_repositories"]["OneForAll"]["commit"]}
    inputs = {"oneforall_runner.py": (ctx.profile.root / "tools/oneforall_runner.py").read_text(encoding="utf-8"),
              "oneforall_support.py": (Path(__file__).parents[1] / "utils/oneforall.py").read_text(encoding="utf-8"),
              "oneforall-input.json": json.dumps(plan, sort_keys=True)}
    return ctx.jobs.run(vendor + "/.venv/bin/python", ["{job}/oneforall_runner.py", "--input", "{job}/oneforall-input.json"],
        stage="4", timeout=ctx.config.get("limits", {}).get("oneforall_timeout", 3600), background=True,
        inputs=inputs, idempotent=True)


def ingest(ctx, root, handle):
    ctx.jobs.wait(handle)
    directory, notes, accepted, excluded, invalid = ctx.jobs.result_dir(handle), [], [], [], []
    report = {}
    if handle.rc != 0:
        notes.append(f"OneForAll {root} failed/partial, rc={handle.rc}")
    try:
        report = json.loads((directory / "oneforall-run.json").read_text(encoding="utf-8"))
        if (not isinstance(report, dict) or report.get("root") != root or report.get("mode") != "passive" or
                not isinstance(report.get("flags"), dict) or set(report["flags"]) != set(PASSIVE_FLAGS) or
                any(value is not False for value in report["flags"].values())):
            raise ValueError("Invalid OneForAll run evidence")
        if report.get("status") != "completed":
            notes.append(f"OneForAll {root}: {report.get('status')} {report.get('error', '')}".strip())
        rows = json.loads((directory / "oneforall-observations.json").read_text(encoding="utf-8-sig"))
        if not isinstance(rows, list):
            raise ValueError("OneForAll observations must be a JSON array")
    except (OSError, ValueError, TypeError) as exc:
        notes.append(f"OneForAll {root} unusable output: {type(exc).__name__}: {exc}")
        ctx.db.fact("oneforall:" + root, {"jobid": handle.jobid, "run": report, "status": "partial", "notes": notes})
        ctx.note("oneforall_partial", root, json.dumps({"jobid": handle.jobid, "notes": notes}))
        return [], notes
    for row in rows:
        if isinstance(row, dict) and row.get("subdomain") is None:
            continue  # Upstream records empty module results as null subdomains.
        try:
            domain = domain_name(row["subdomain"].removeprefix("*."))
            if domain != root and not domain.endswith("." + root) or not ctx.scope.contains(domain):
                excluded.append(row)
                continue
            sources = row.get("source", "")
            if not isinstance(sources, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sources):
                raise ValueError("Invalid OneForAll module source")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            invalid.append({"row": row, "error": type(exc).__name__})
            continue
        source = "oneforall:" + sources
        ctx.db.domain(Domain(domain, sources=source))
        accepted.append({"domain": domain, "source": source})
    if invalid:
        notes.append(f"OneForAll {root}: {len(invalid)} invalid observation(s)")
    evidence = {"jobid": handle.jobid, "run": report, "accepted": accepted, "excluded": excluded,
                "invalid": invalid, "status": "partial" if notes else "completed", "notes": notes}
    ctx.db.fact("oneforall:" + root, evidence)
    if notes:
        ctx.note("oneforall_partial", root, json.dumps({"jobid": handle.jobid, "notes": notes}))
    return accepted, notes


def settings(config):
    return OneForAllSettings.from_config(config)
