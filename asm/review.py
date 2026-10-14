"""Operator review is distinct from ownership, confidence and test permission."""
import hashlib
import json
from pathlib import Path
import uuid

from .models import utcnow
from .policy import redacted_snapshot
from .run_store import atomic_json, encode


FAMILIES = {name: name for name in ("fofa", "quake", "hunter", "censys", "zoomeye", "shodan")}
FAMILIES.update({"certificate_indexes": "crt.sh", "archive_indexes": "web.archive.org",
                 "target_http": "target_http", "playwright": "target_http", "dnspython": "dns_observation"})


def review_asset(workbench, run_id, asset_id, *, status, note="", evidence_ids=None, corroborated=False):
    if status not in {"pending", "reviewed", "excluded"} or not isinstance(note, str) or len(note) > 2000 or "\x00" in note:
        raise ValueError("Invalid manual review status or note")
    if status != "pending" and not note.strip():
        raise ValueError("A review or exclusion requires an evidence-based note")
    if type(corroborated) is not bool or corroborated and status != "reviewed":
        raise ValueError("Corroboration requires an explicit reviewed decision")
    evidence_ids = evidence_ids or []
    if not isinstance(evidence_ids, list) or any(not isinstance(v, str) for v in evidence_ids):
        raise ValueError("Review evidence IDs must be a list of strings")
    evidence_ids = sorted(set(evidence_ids))
    with workbench.store.lock:
        run = workbench.run(run_id)
        matching = [asset for asset in run["assets"] if asset["asset_id"] == asset_id]
        if not matching:
            raise ValueError("Unknown asset in this run")
        asset = matching[0]
        if set(evidence_ids) - set(asset.get("evidence_ids", [])):
            raise ValueError("Review evidence must already belong to this asset")
        index = {row["evidence_id"]: row for item in workbench.store.rows(
            "SELECT data FROM records WHERE run=? AND category='evidence_index'", (run_id,))
            for row in [json.loads(item["data"])] if row.get("evidence_id")}
        root = Path(run["directory"]).resolve()
        for identifier in evidence_ids:
            row = index.get(identifier)
            if not row:
                raise ValueError("Selected evidence has no persisted provenance")
            path = (root / row["path"]).resolve()
            if not path.is_relative_to(root) or any(p.startswith(".env") for p in path.parts) or not path.is_file():
                raise ValueError("Selected review evidence is unavailable")
            if hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
                raise ValueError("Selected review evidence checksum mismatch")
        families = set()
        for event in workbench.store.events(run_id):
            data = event["data"]
            if event["kind"] == "tool_call" and data.get("status") == "completed" and data.get("call_id") in evidence_ids:
                family = FAMILIES.get(data.get("tool"))
                if family:
                    families.add(family)
        if corroborated and (len(evidence_ids) < 2 or len(families) < 2):
            raise ValueError("Corroboration requires selected matching evidence from two independently identified sources")
        decision = {"status": status, "note": note.strip(), "supporting_evidence_ids": evidence_ids,
                    "corroborated": corroborated, "source_families": sorted(families)}
        previous = asset.get("manual_review", {})
        if all(previous.get(key) == value for key, value in decision.items()):
            return asset
        identifier, now = "review-" + uuid.uuid4().hex, utcnow()
        record = {**redacted_snapshot(decision), "review_id": identifier, "asset_id": asset_id,
                  "run_id": run_id, "actor": "local_user", "knowledge": "operator_assertion", "observed_at": now}
        path = root / "evidence" / (identifier + ".json")
        atomic_json(path, record)
        evidence = {"category": "evidence_index", "evidence_id": identifier, "path": path.relative_to(root).as_posix(),
                    "kind": "manual_review", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "observed_at": now}
        asset.update(review_status=status, corroboration_status="corroborated" if corroborated else "unconfirmed",
                     review_evidence=evidence_ids, manual_review=record)
        asset["evidence_ids"] = sorted(set(asset.get("evidence_ids", [])) | {identifier})
        # Confidence, verification_status, ownership and scope remain separate.
        with workbench.store.connection() as conn:
            conn.execute("UPDATE assets SET data=? WHERE run=? AND id=?", (encode(asset), run_id, asset_id))
            conn.execute("INSERT INTO records VALUES(?,?,?,?)", (identifier, run_id, "evidence_index", encode(evidence)))
            workbench.store.event(run_id, "asset_reviewed", record, conn)
            workbench.store.event(run_id, "artifact_written", evidence, conn)
        workbench.checkpoint(run_id)
        return asset
