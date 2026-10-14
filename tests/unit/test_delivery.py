import hashlib
import json
from pathlib import Path

from asm.delivery import snapshot_changes
from asm.orchestrator import Workbench
from tests.unit.test_orchestrator import configuration, local_asset, workbench_root  # noqa: F401


def baseline(tmp_path, data):
    directory = tmp_path / "old"
    directory.mkdir()
    raw = json.dumps(data).encode()
    (directory / "observations.snapshot.json").write_bytes(raw)
    (directory / "manifest.json").write_text(json.dumps({"snapshot_id": "old", "files": [{
        "path": "observations.snapshot.json", "status": "complete", "sha256": hashlib.sha256(raw).hexdigest()}]}))
    return directory


def test_compare_added_not_reobserved_changed_and_incomparable(tmp_path):
    old = {"comparison_key": "matching", "run_id": "prior", "assets": [{"asset_id": "gone"},
        {"asset_id": "both", "title": "before", "evidence_ids": ["one"]}]}
    directory = baseline(tmp_path, old)
    new = {"comparison_key": "matching", "assets": [{"asset_id": "new"},
        {"asset_id": "both", "title": "after", "evidence_ids": ["two"]}]}
    changes = snapshot_changes(new, [directory])
    assert changes["status"] == "comparable"
    assert changes["added_asset_ids"] == ["new"]
    assert changes["not_reobserved_asset_ids"] == ["gone"]
    assert changes["changed_assets"][0]["fields"]["title"]["current"] == "after"
    assert changes["changed_evidence_asset_ids"] == ["both"]
    new["comparison_key"] = "revoked_permission"
    assert snapshot_changes(new, [directory])["status"] == "unavailable"
    (directory / "observations.snapshot.json").write_text("tampered")
    new["comparison_key"] = "matching"
    assert snapshot_changes(new, [directory])["status"] == "unavailable"


def test_real_navigation_and_export_failure_recovery(workbench_root, monkeypatch):  # noqa: F811
    wb = Workbench(workbench_root, adapters={"web_visit": local_asset})
    item = wb.save_project(configuration(["http://localhost:8765"]))
    run = wb.start(item["project_id"], background=False)
    path = Path(run["directory"])
    assert (path / "index.html").is_file()
    assert (path.parents[1] / "index.html").is_file()
    assert run["snapshot"]["comparison"]["status"] == "unavailable"
    first = run["snapshot"]["snapshot_id"]
    second = wb.export(run["run_id"])
    assert second["comparison"]["status"] == "comparable"
    assert second["comparison"]["previous_snapshot_id"] == first
    old_files = {p: p.read_bytes() for p in (path / "exports").rglob("*") if p.is_file()}
    original = wb._export_locked

    def fail(_run_id):
        raise PermissionError("fixture write failure")

    monkeypatch.setattr(wb, "_export_locked", fail)
    failure = wb.export(run["run_id"])
    assert failure["status"] == "incomplete"
    assert wb.run(run["run_id"])["delivery_error"]["reason"] == "PermissionError"
    assert wb.run(run["run_id"])["snapshot"]["snapshot_id"] == second["snapshot_id"]
    assert all(p.read_bytes() == raw for p, raw in old_files.items())
    monkeypatch.setattr(wb, "_export_locked", original)
    wb.export(run["run_id"])
    assert wb.run(run["run_id"])["delivery_error"] is None
