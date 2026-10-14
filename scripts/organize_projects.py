"""Move local profile files by purpose and preserve all run/evidence references."""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asm.project_catalog import project_purpose, profile_directory  # noqa: E402
from asm.run_store import RunStore, digest  # noqa: E402


def organize(root, *, apply=False):
    root = Path(root).resolve()
    profiles = root / "profiles"
    database = root / "data/workbench.sqlite"
    plans = []
    for source in sorted(profiles.glob("local-*.yaml")):
        config = yaml.safe_load(source.read_text(encoding="utf-8"))
        purpose = project_purpose(config, config.get("profile", ""))
        target = profile_directory(root, purpose) / source.name
        # Resolve both targets before moving; never overwrite a different file.
        if not source.resolve().is_relative_to(profiles) or not target.resolve().is_relative_to(profiles):
            raise ValueError("Profile path leaves the intended workspace directory")
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError(f"Destination already exists: {target.name}")
        plans.append({"project_id": config.get("profile"), "purpose": purpose,
                      "source": str(source), "target": str(target),
                      "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    result = {"applied": apply, "profiles": plans, "moved": 0,
              "evidence_policy": "Existing run directories and evidence snapshots retain their original paths"}
    if not apply or not plans:
        return result
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    audit = root / "data/organization" / stamp
    audit.mkdir(parents=True)
    (audit / "plan.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    store = RunStore(database)
    with store.connection() as conn:
        with sqlite3.connect(audit / "workbench.before.sqlite") as backup:
            conn.backup(backup)
        frozen_tables = ("runs", "steps", "events", "assets", "records", "action_receipts", "feedback")
        def state_hash():
            return digest({table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                           for table in frozen_tables})
        before = state_hash()
        for item in plans:
            source, target = Path(item["source"]), Path(item["target"])
            # Copy first, commit the new DB reference, then remove the old file.
            # An interruption before commit leaves a valid old path and a recoverable copy.
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            if hashlib.sha256(target.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Profile copy checksum differs")
            conn.execute("UPDATE projects SET path=? WHERE path=?", (str(target), str(source)))
        if state_hash() != before:
            raise ValueError("Historical run state changed during organization")
    for item in plans:
        Path(item["source"]).unlink()
        result["moved"] += 1
    result.update({"history_state_sha256": before, "history_state_unchanged": True,
                   "backup": str(audit / "workbench.before.sqlite")})
    (audit / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the reviewed organization plan")
    args = parser.parse_args()
    summary = organize(ROOT, apply=args.apply)
    print(json.dumps({"applied": summary["applied"], "planned": len(summary["profiles"]),
                      "moved": summary["moved"], "backup": summary.get("backup"),
                      "counts": {purpose: sum(p["purpose"] == purpose for p in summary["profiles"])
                                 for purpose in ("investigation", "validation", "demo")}}, ensure_ascii=False, indent=2))
