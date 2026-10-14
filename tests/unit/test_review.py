import json
from pathlib import Path

import pytest

from asm.orchestrator import Workbench
from asm.run_store import digest
from tests.unit.test_orchestrator import configuration, local_asset, workbench_root  # noqa: F401


def test_review_is_persistent_idempotent_and_separate_from_permissions(workbench_root):  # noqa: F811
    wb = Workbench(workbench_root, adapters={"web_visit": local_asset})
    item = wb.save_project(configuration(["http://localhost:8765"]))
    run = wb.start(item["project_id"], background=False)
    directory = Path(run["directory"])
    frozen = {p: p.read_bytes() for p in (directory / "exports").rglob("*") if p.is_file()}
    before = run["assets"][0]
    permission_hash = digest(wb.project(item["project_id"])["config"])
    reviewed = wb.review(run["run_id"], before["asset_id"], status="reviewed", note="Owned fixture evidence checked",
                         evidence_ids=before["evidence_ids"])
    assert reviewed["review_status"] == "reviewed" and reviewed["corroboration_status"] == "unconfirmed"
    assert reviewed["verification_status"] == before["verification_status"]
    assert reviewed["attribution_status"] == before["attribution_status"]
    assert digest(wb.project(item["project_id"])["config"]) == permission_hash
    count = len(wb.store.events(run["run_id"]))
    assert wb.review(run["run_id"], before["asset_id"], status="reviewed", note="Owned fixture evidence checked",
                     evidence_ids=before["evidence_ids"]) == reviewed
    assert len(wb.store.events(run["run_id"])) == count
    reopened = Workbench(workbench_root, recover=False)
    assert reopened.run(run["run_id"])["assets"][0]["manual_review"] == reviewed["manual_review"]
    excluded = wb.review(run["run_id"], before["asset_id"], status="excluded", note="Manual false-positive exclusion")
    assert excluded["scope_status"] == "in_scope"
    exported = wb.export(run["run_id"])
    assert exported["main_asset_count"] == 0 and exported["excluded_asset_count"] == 1
    assert all(p.read_bytes() == raw for p, raw in frozen.items())
    wb.review(run["run_id"], before["asset_id"], status="pending")
    assert wb.export(run["run_id"])["main_asset_count"] == 1


def test_corroboration_requires_selected_evidence_from_independent_sources(workbench_root):  # noqa: F811
    value = configuration([])
    value.update(mode_preset="passive_discovery", authorization=False, targets={"roots": ["example.invalid"]})
    value["execution"]["target_local"] = False
    value["scope_sets"]["investigation"]["include"] = ["example.invalid"]
    value["permissions"] = {"search": {"allow": True, "scope_ref": "investigation"}}
    value["plan"] = {"selection": "custom", "selected_capabilities": ["search"], "selected_tools": ["fofa", "quake"],
                     "params": {"search": {"engines": ["fofa", "quake"]}}}

    def source(ctx):
        ctx.call(ctx.step["tool"], {"domain": ctx.target}, lambda: {"fixture": True})
        return {"assets": [{"asset_id": "fixture-domain", "name": ctx.target, "domain": ctx.target,
            "sources": [ctx.step["tool"]], "confidence": "C", "verification_status": "candidate_only", "evidence_ids": [ctx.last_evidence_id]}],
            "records": ctx.records, "status": "completed"}

    wb = Workbench(workbench_root, adapters={"search": source})
    item = wb.save_project(value)
    run = wb.start(item["project_id"], background=False)
    asset = run["assets"][0]
    with pytest.raises(ValueError, match="two independently"):
        wb.review(run["run_id"], asset["asset_id"], status="reviewed", note="only one source", evidence_ids=asset["evidence_ids"][:1], corroborated=True)
    reviewed = wb.review(run["run_id"], asset["asset_id"], status="reviewed", note="Matching host observed in independent fixture sources",
                         evidence_ids=asset["evidence_ids"], corroborated=True)
    assert reviewed["corroboration_status"] == "corroborated"
    assert reviewed["confidence"] == "C" and reviewed["verification_status"] == "candidate_only"
    assert reviewed["attribution_status"] == "unconfirmed"
    with wb.store.connection() as conn:
        wb.store.upsert_asset(conn, run["run_id"], {**asset, "review_status": "pending", "corroboration_status": "unconfirmed"})
    assert wb.run(run["run_id"])["assets"][0]["corroboration_status"] == "corroborated"
    evidence = json.loads(wb.store.rows("SELECT data FROM records WHERE run=? AND id=?", (run["run_id"], asset["evidence_ids"][0]))[0]["data"])
    (Path(run["directory"]) / evidence["path"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        wb.review(run["run_id"], asset["asset_id"], status="reviewed", note="recheck", evidence_ids=asset["evidence_ids"], corroborated=True)
    with pytest.raises(ValueError):
        wb.review(run["run_id"], "outside-run", status="pending")
