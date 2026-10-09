from dataclasses import dataclass
from datetime import datetime, timezone


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Company:
    cid: str
    name: str
    brand: str = ""
    parent_cid: str | None = None
    share_pct: float | None = None
    level: int = 0
    source: str = "seed"
    website: str | None = None
    email_suffix: str | None = None
    note: str = ""


@dataclass
class Domain:
    domain: str
    registrable: str = ""
    cid: str | None = None
    tag5: str = "有解析未验证"
    confidence: str = "A"
    wildcard: int = 0
    first_seen: str = ""
    last_seen: str = ""
    sources: str = "seed"


@dataclass
class Asset:
    host: str = ""
    ip: str = ""
    port: int = 443
    proto: str = "tcp"
    service: str = ""
    product: str = ""
    version: str = ""
    title: str = ""
    tech: str = ""
    cdn: int = 0
    cid: str | None = None
    source: str = ""
    confidence: str = "A"
    ts: str = ""


@dataclass
class Finding:
    kind: str
    url: str
    evidence: str
    asset_id: int | None = None
    severity: str = "info"
    status: str = "review"


@dataclass
class Person:
    name: str
    role: str = ""
    cid: str | None = None
    email: str = ""
    phone: str = ""
    qq: str = ""
    weibo: str = ""
    source: str = ""


@dataclass
class Job:
    jobid: str
    stage: str
    tool: str
    cmd: str
    status: str = "pending"
    rc: int | None = None
    started: str = ""
    finished: str = ""
    log_path: str = ""
    result_dir: str = ""
