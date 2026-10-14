import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from asm.orchestrator import Workbench
from tests.unit.test_orchestrator import configuration, local_asset, workbench_root  # noqa: F401


def test_bundle_packages_exact_snapshot_evidence_and_audit_cutoff(workbench_root):  # noqa: F811
    wb = Workbench(workbench_root, adapters={"web_visit": local_asset})
    item = wb.save_project(configuration(["http://localhost:8765"]))
    run = wb.start(item["project_id"], background=False)
    directory = Path(run["directory"])
    frozen = {p: p.read_bytes() for p in (directory / "exports").rglob("*") if p.is_file()}
    package = wb.bundle(run["run_id"])
    with zipfile.ZipFile(directory / package["path"]) as archive:
        metadata = json.loads(archive.read("bundle.json"))
        assert metadata["run_id"] == run["run_id"]
        assert package["status"] == "complete"
        assert sum(name.startswith("exports/") and name.endswith((".csv", ".html", ".md")) and "/tables/" not in name for name in archive.namelist()) == 6
        assert any("shared_evidence/" in name for name in archive.namelist())
        for name, checksum in metadata["payloads"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum["sha256"]
        prefix = "exports/" + run["snapshot"]["snapshot_id"] + "/"
        audit = json.loads(archive.read(prefix + "audit.snapshot.json"))
        for name, cutoff in audit["logs"]["files"].items():
            assert len(archive.read("logs/" + name)) == cutoff["bytes"]
    wb.store.event(run["run_id"], "later_event", {"fixture": True})
    wb.checkpoint(run["run_id"])
    assert wb.bundle(run["run_id"]) == package
    assert all(p.read_bytes() == raw for p, raw in frozen.items())


def test_bundle_rejects_tampering_and_invalid_paths_without_overwriting(workbench_root):  # noqa: F811
    wb = Workbench(workbench_root, adapters={"web_visit": local_asset})
    item = wb.save_project(configuration(["http://localhost:8765"]))
    run = wb.start(item["project_id"], background=False)
    package = wb.bundle(run["run_id"])
    path = Path(run["directory"]) / package["path"]
    original = path.read_bytes()
    payload = Path(run["directory"]) / "exports" / run["snapshot"]["snapshot_id"] / "observations.snapshot.json"
    payload.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        wb.bundle(run["run_id"])
    assert path.read_bytes() == original
    with pytest.raises(ValueError):
        wb.bundle(run["run_id"], "../../.env")


def test_bundle_copies_saved_ledger_and_preserves_incomplete_status(workbench_root):  # noqa: F811
    from asm.db import Database
    with Database(workbench_root / "data/account-rate-ledger.sqlite") as db:
        db.execute("INSERT INTO sources VALUES(?,?,?,?)", ("fixture-account", "2026-10-11", 7, 20))
    wb = Workbench(workbench_root, adapters={"web_visit": local_asset})
    item = wb.save_project(configuration(["http://localhost:8765"]))
    run = wb.start(item["project_id"], background=False)
    directory = Path(run["directory"])
    package = wb.bundle(run["run_id"])
    with zipfile.ZipFile(directory / package["path"]) as archive:
        assert sum(name.startswith("logs/rate-ledger-") for name in archive.namelist()) == 1
    manifest_path = directory / "exports" / run["snapshot"]["snapshot_id"] / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["status"] = "incomplete"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    incomplete = wb.bundle(run["run_id"])
    assert incomplete["status"] == "incomplete" and incomplete["path"] != package["path"]
