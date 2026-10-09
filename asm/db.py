"""SQLite is the only source of truth; each observation commits immediately."""
import json
import sqlite3
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .models import utcnow
from .precision import destination
from .scope import normalize_host, registrable

ASSET_FIELDS = """id INTEGER PRIMARY KEY, host TEXT NOT NULL, ip TEXT, port INTEGER NOT NULL,
proto TEXT NOT NULL, service TEXT, product TEXT, version TEXT, title TEXT, tech TEXT,
cdn INTEGER DEFAULT 0, cid TEXT, source TEXT, confidence TEXT, ts TEXT"""
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS companies(cid TEXT PRIMARY KEY, name TEXT, brand TEXT, parent_cid TEXT,
share_pct REAL, level INTEGER, source TEXT, website TEXT, email_suffix TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS domains(domain TEXT PRIMARY KEY, registrable TEXT, cid TEXT, tag5 TEXT,
confidence TEXT, wildcard INTEGER DEFAULT 0, first_seen TEXT, last_seen TEXT, sources TEXT);
CREATE TABLE IF NOT EXISTS dns_records(domain TEXT, rtype TEXT, value TEXT, resolver TEXT, ts TEXT,
UNIQUE(domain,rtype,value,resolver));
CREATE TABLE IF NOT EXISTS assets({ASSET_FIELDS}, UNIQUE(host,port,proto));
CREATE TABLE IF NOT EXISTS assets_quarantine({ASSET_FIELDS}, reason TEXT, UNIQUE(host,port,proto));
CREATE TABLE IF NOT EXISTS takeovers(id INTEGER PRIMARY KEY, domain TEXT, kind TEXT, provider TEXT,
evidence TEXT, status TEXT, UNIQUE(domain,kind,provider));
CREATE TABLE IF NOT EXISTS findings(id INTEGER PRIMARY KEY, asset_id INTEGER REFERENCES assets(id),
kind TEXT, url TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '', severity TEXT,
status TEXT, UNIQUE(kind,url,evidence));
CREATE TABLE IF NOT EXISTS people(id INTEGER PRIMARY KEY, name TEXT, role TEXT, cid TEXT,
email TEXT NOT NULL DEFAULT '', phone TEXT, qq TEXT, weibo TEXT, source TEXT,
UNIQUE(name,cid,email));
CREATE TABLE IF NOT EXISTS jobs(jobid TEXT PRIMARY KEY, stage TEXT, tool TEXT, cmd TEXT, status TEXT,
rc INTEGER, started TEXT, finished TEXT, log_path TEXT, result_dir TEXT, fingerprint TEXT);
CREATE TABLE IF NOT EXISTS pipeline_state(profile TEXT, stage TEXT, status TEXT, started TEXT,
finished TEXT, PRIMARY KEY(profile,stage));
CREATE TABLE IF NOT EXISTS sources(source TEXT, day TEXT, used INTEGER, quota INTEGER,
PRIMARY KEY(source,day));
CREATE TABLE IF NOT EXISTS rate_state(source TEXT PRIMARY KEY, last_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS facts(k TEXT PRIMARY KEY, v TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS urls(url TEXT PRIMARY KEY, asset_id INTEGER REFERENCES assets(id),
title TEXT, status INTEGER, len INTEGER, tech TEXT, screenshot TEXT);
CREATE TABLE IF NOT EXISTS systems(system_name TEXT PRIMARY KEY, cid TEXT, tags TEXT, urls TEXT,
vendor TEXT, version TEXT, source TEXT);
CREATE INDEX IF NOT EXISTS jobs_fingerprint ON jobs(fingerprint,status);
"""


def record(value):
    return asdict(value) if is_dataclass(value) else dict(value)


def merge_sources(*values):
    return ",".join(sorted({s.strip() for v in values if v for s in v.split(",") if s.strip()}))


class Database:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.columns = {
            row[0]: {r[1] for r in self.conn.execute(f"PRAGMA table_info({row[0]})")}
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def rows(self, sql, params=()):
        return [dict(r) for r in self.conn.execute(sql, params)]

    def execute(self, sql, params=()):
        with self.conn:
            return self.conn.execute(sql, params)

    def upsert(self, table, data, keys, *, merge=False):
        data = record(data)
        if table not in self.columns or not set(data) <= self.columns[table] or not set(keys) <= set(data):
            raise ValueError("Unknown table, invalid columns or missing keys")
        where = " AND ".join(f"{k} IS ?" for k in keys)
        with self.conn:
            old = self.conn.execute(f"SELECT * FROM {table} WHERE {where}", [data[k] for k in keys]).fetchone()
            if old and merge:
                for key, value in list(data.items()):
                    if key in {"source", "sources"}:
                        data[key] = merge_sources(old[key], value)
                    elif key not in {"last_seen", "ts"} and old[key] not in (None, "", 0):
                        data[key] = old[key]
            names = list(data)
            # Manual update also deduplicates keys containing SQL NULL.
            if old:
                updates = [k for k in names if k not in keys]
                if updates:
                    self.conn.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in updates)} WHERE {where}",
                                      [data[k] for k in updates] + [data[k] for k in keys])
            else:
                self.conn.execute(f"INSERT INTO {table} ({','.join(names)}) "
                                  f"VALUES ({','.join('?' for _ in names)})", list(data.values()))
            return dict(self.conn.execute(f"SELECT * FROM {table} WHERE {where}",
                                          [data[k] for k in keys]).fetchone())

    def domain(self, value):
        data = record(value)
        data["domain"] = normalize_host(data["domain"])
        data["registrable"] = data.get("registrable") or registrable(data["domain"])
        data["first_seen"] = data.get("first_seen") or utcnow()
        data["last_seen"] = utcnow()
        return self.upsert("domains", data, ("domain",), merge=True)

    def asset(self, value, evidence=None):
        data = record(value)
        host = data.get("host") or data.get("ip") or data.get("domain", "")
        if not host:
            self.finding({"kind": "invalid", "url": "", "evidence": "Missing host/ip/domain",
                          "severity": "info", "status": "rejected"})
            return None
        data["host"] = normalize_host(host)
        data.pop("domain", None)
        data.pop("id", None)
        port = int(data.get("port", 443))
        if not 1 <= port <= 65535 or data.get("proto", "tcp") not in {"tcp", "udp"}:
            raise ValueError("Invalid port or transport")
        data["port"] = port
        data.setdefault("proto", "tcp")
        table, confidence, reason = destination(data.get("confidence", "D"), evidence)
        data["confidence"] = confidence
        data["ts"] = utcnow()
        if table == "assets_quarantine":
            data["reason"] = reason
        item = self.upsert(table, data, ("host", "port", "proto"), merge=True)
        return table, item["id"]

    def finding(self, value):
        data = record(value)
        data.setdefault("url", "")
        data.setdefault("evidence", "")
        return self.upsert("findings", data, ("kind", "url", "evidence"), merge=True)

    def fact(self, key, value):
        self.upsert("facts", {"k": key, "v": json.dumps(value, ensure_ascii=False), "ts": utcnow()}, ("k",))

    def get_fact(self, key, default=None):
        row = self.conn.execute("SELECT v FROM facts WHERE k=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def state(self, profile, stage, status):
        old = self.rows("SELECT * FROM pipeline_state WHERE profile=? AND stage=?", (profile, stage))
        self.upsert("pipeline_state", {
            "profile": profile, "stage": stage, "status": status,
            "started": utcnow() if status == "running" or not old else old[0]["started"],
            "finished": "" if status == "running" else utcnow(),
        }, ("profile", "stage"))

    def completed(self, profile, stage):
        return bool(self.rows("SELECT 1 FROM pipeline_state WHERE profile=? AND stage=? AND status='completed'",
                              (profile, stage)))
