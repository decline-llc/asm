"""Package one immutable delivery snapshot with its exact audit log cutoff."""
import hashlib
import json
from pathlib import Path
import re
import uuid
import zipfile


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or any(part.startswith(".env") for part in path.parts):
        raise ValueError("Invalid bundle input path")
    return path


def create_bundle(run, snapshot_id=None):
    directory = Path(run["directory"]).resolve()
    identifier = snapshot_id or (run.get("snapshot") or {}).get("snapshot_id", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", identifier) or identifier in {".", ".."}:
        raise ValueError("A valid saved snapshot is required")
    snapshot = _inside(directory, "exports/" + identifier)
    manifest_raw = (snapshot / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest["run_id"] != run["run_id"] or manifest["snapshot_id"] != identifier:
        raise ValueError("Snapshot identity does not match this run")
    payloads = {"exports/" + identifier + "/manifest.json": manifest_raw}
    for entry in manifest["files"]:
        path = _inside(snapshot, entry["path"])
        if entry.get("sha256"):
            raw = path.read_bytes()
            if _hash(raw) != entry["sha256"]:
                raise ValueError("Saved snapshot payload checksum mismatch")
            payloads["exports/" + identifier + "/" + path.relative_to(snapshot).as_posix()] = raw
        elif entry["status"] == "complete":
            raise ValueError("Completed snapshot payload has no checksum")
    audit = json.loads(payloads["exports/" + identifier + "/audit.snapshot.json"])
    for name, cutoff in audit.get("logs", {}).get("files", {}).items():
        if name not in {"events.jsonl", "tool-calls.jsonl"}:
            raise ValueError("Unknown saved audit log")
        path = _inside(directory, "logs/" + name)
        with path.open("rb") as stream:
            raw = stream.read(int(cutoff["bytes"]))
        if len(raw) != cutoff["bytes"] or _hash(raw) != cutoff["sha256"]:
            raise ValueError("Saved audit log cutoff checksum mismatch")
        payloads["logs/" + name] = raw
    reference = audit.get("ledger_reference", {})
    if reference.get("snapshot"):
        ledger_path = _inside(directory, reference["snapshot"])
        if not ledger_path.is_relative_to(directory / "logs"):
            raise ValueError("Invalid saved ledger path")
        raw = ledger_path.read_bytes()
        if _hash(raw) != reference["sha256"]:
            raise ValueError("Saved account ledger checksum mismatch")
        payloads[ledger_path.relative_to(directory).as_posix()] = raw
    metadata = {"run_id": run["run_id"], "snapshot_id": identifier, "status": manifest["status"],
        "data_cutoff": manifest["data_cutoff"], "manifest_sha256": _hash(manifest_raw),
        "payloads": {name: {"bytes": len(raw), "sha256": _hash(raw)} for name, raw in payloads.items()}}
    payloads["bundle.json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2).encode()
    payloads["README.md"] = ("# ASM Workbench delivery\n\nRun: " + run["run_id"] + "\n\nSnapshot: " + identifier +
        "\n\nDelivery status: " + manifest["status"] + "\n\nReports and shared evidence: exports/" + identifier +
        "/\n\nAudit logs include only the saved snapshot cutoff. Later actions are excluded. "
        "Use manifest.json and bundle.json to verify checksums and incomplete coverage.\n").encode()
    bundles = directory / "bundles"
    bundles.mkdir(exist_ok=True)
    path = bundles / (identifier + "-" + metadata["manifest_sha256"][:12] + ".zip")
    if path.is_file():
        with zipfile.ZipFile(path) as archive:
            if set(archive.namelist()) != set(payloads) or any(archive.read(name) != raw for name, raw in payloads.items()):
                raise ValueError("Existing bundle checksum mismatch; retained for review")
    else:
        temporary = bundles / (uuid.uuid4().hex + ".tmp")
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, raw in sorted(payloads.items()):
                    archive.writestr(name, raw)
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
    return {"run_id": run["run_id"], "snapshot_id": identifier, "status": manifest["status"],
            "path": path.relative_to(directory).as_posix(), "bytes": path.stat().st_size,
            "sha256": _hash(path.read_bytes())}
