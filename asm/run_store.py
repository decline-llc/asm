"""Durable project/run state. Events and completed-step receipts share a transaction."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from .models import utcnow
from .run_lock import FileLease, LeaseBusy, SharedStateLock


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(encode(value), encoding="utf-8")
    temporary.replace(path)


class RunStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = SharedStateLock(self.path.with_suffix(".state.lock"))
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, path TEXT NOT NULL,
                    revision INTEGER NOT NULL, data TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, project TEXT NOT NULL,
                    status TEXT NOT NULL, config TEXT NOT NULL, directory TEXT NOT NULL,
                    started TEXT NOT NULL, finished TEXT, snapshot TEXT);
                CREATE TABLE IF NOT EXISTS steps(id TEXT PRIMARY KEY, run TEXT NOT NULL,
                    capability TEXT NOT NULL, target TEXT NOT NULL, tool TEXT NOT NULL,
                    params TEXT NOT NULL, round INTEGER NOT NULL, status TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0, receipt TEXT, reason TEXT,
                    UNIQUE(run,capability,target,tool,round));
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL, ts TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS assets(id TEXT NOT NULL, run TEXT NOT NULL,
                    data TEXT NOT NULL, PRIMARY KEY(id,run));
                CREATE TABLE IF NOT EXISTS records(id TEXT NOT NULL, run TEXT NOT NULL,
                    category TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(id,run));
                CREATE TABLE IF NOT EXISTS action_receipts(id TEXT PRIMARY KEY,run TEXT NOT NULL,
                    step TEXT NOT NULL,path TEXT NOT NULL,evidence_id TEXT NOT NULL,sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,run TEXT NOT NULL,
                    target TEXT NOT NULL,round INTEGER NOT NULL,status TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        with self.lock:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()

    def rows(self, query, args=()):
        with self.connection() as conn:
            return [dict(r) for r in conn.execute(query, args)]

    def event(self, run_id, kind, data, conn=None):
        if conn is None:
            with self.connection() as transaction:
                return self.event(run_id, kind, data, transaction)
        cursor = conn.execute("INSERT INTO events(run,kind,data,ts) VALUES(?,?,?,?)",
                              (run_id, kind, encode(data), utcnow()))
        return cursor.lastrowid

    def events(self, run_id, after=0):
        return [{**r, "data": json.loads(r["data"])} for r in self.rows(
            "SELECT * FROM events WHERE run=? AND id>? ORDER BY id", (run_id, after))]

    def upsert_asset(self, conn, run_id, row):
        key = row.get("asset_id") or digest([row.get("name", row.get("host", "")), row.get("ip", ""),
            row.get("port", ""), row.get("protocol", row.get("proto", "tcp"))])[:24]
        row["asset_id"] = key
        previous = conn.execute("SELECT data FROM assets WHERE id=? AND run=?", (key, run_id)).fetchone()
        if previous:
            old = json.loads(previous[0])
            manual = {field: old[field] for field in ("review_status", "corroboration_status", "review_evidence", "manual_review")
                      if field in old and old.get("manual_review")}
            for field in ("sources", "evidence_ids", "finding_ids"):
                row[field] = sorted(set(old.get(field, [])) | set(row.get(field, [])))
            old.update({k: v for k, v in row.items() if v not in (None, "", [])})
            old.update(manual)
            row = old
        conn.execute("INSERT INTO assets VALUES(?,?,?) ON CONFLICT(id,run) DO UPDATE SET data=excluded.data",
                     (key, run_id, encode(row)))
        self.event(run_id, "asset_found", row, conn)

    def recover(self):
        with self.connection() as conn:
            for row in conn.execute("SELECT id,status FROM runs WHERE status IN ('pending','running','pausing','stopping')"):
                try:
                    lease = self.run_lease(row["id"])
                except LeaseBusy:
                    # A second UI/CLI instance must not interrupt a live worker.
                    continue
                with lease:
                    state = "stopped" if row["status"] == "stopping" else "interrupted"
                    conn.execute("UPDATE runs SET status=? WHERE id=?", (state, row["id"]))
                    conn.execute("UPDATE steps SET status='interrupted' WHERE run=? AND status='running'", (row["id"],))
                    self.event(row["id"], "run_state", {"state": state, "reason": "backend_restart"}, conn)

    def run_lease(self, run_id):
        import re
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Invalid run identifier")
        return FileLease(self.path.parent / "worker-leases" / (run_id + ".lock"))

    def flush_logs(self, run_id, directory):
        with self.lock:
            return self._flush_logs(run_id, directory)

    def _flush_logs(self, run_id, directory):
        directory = Path(directory)
        events = self.events(run_id)
        # These are materialized views of the authoritative append-only event table.
        for name, selected in (("events.jsonl", events), ("tool-calls.jsonl", [{"id": e["id"], **e["data"]} for e in events if e["kind"] == "tool_call"])):
            path = directory / "logs" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text("".join(encode(e) + "\n" for e in selected), encoding="utf-8")
            temporary.replace(path)
