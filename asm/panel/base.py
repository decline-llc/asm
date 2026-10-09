import json
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from ..models import Asset
from ..precision import classify
from ..scope import normalize_host

_rate_lock = threading.Lock()


class QuotaExceeded(RuntimeError):
    pass


class RateLimiter:
    """Atomic persistent reservation, including failed requests, across processes."""
    def __init__(self, db, source, *, min_interval=0, daily=200, clock=time.time, sleeper=time.sleep):
        if min_interval < 0 or daily < 1:
            raise ValueError("Invalid rate limits")
        self.db, self.source, self.clock, self.sleeper = db, source, clock, sleeper
        self.min_interval = max(15, min_interval) if source == "fofa" else min_interval
        self.daily = min(200, daily) if source == "fofa" else daily

    def acquire(self):
        with _rate_lock:
            while True:
                now = self.clock()
                day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
                conn = self.db.conn
                conn.execute("BEGIN IMMEDIATE")
                try:
                    row = conn.execute("SELECT used FROM sources WHERE source=? AND day=?",
                                       (self.source, day)).fetchone()
                    used = row[0] if row else 0
                    if used >= self.daily:
                        raise QuotaExceeded(f"{self.source}: daily quota {self.daily} exhausted")
                    previous = conn.execute("SELECT last_at FROM rate_state WHERE source=?",
                                            (self.source,)).fetchone()
                    remaining = (previous[0] + self.min_interval - now) if previous else 0
                    if remaining <= 0:
                        conn.execute("INSERT INTO sources VALUES(?,?,?,?) ON CONFLICT(source,day) "
                                     "DO UPDATE SET used=excluded.used,quota=excluded.quota",
                                     (self.source, day, used + 1, self.daily))
                        conn.execute("INSERT INTO rate_state VALUES(?,?) ON CONFLICT(source) "
                                     "DO UPDATE SET last_at=excluded.last_at", (self.source, now))
                        conn.commit()
                        return
                    conn.rollback()
                except Exception:
                    conn.rollback()
                    raise
                self.sleeper(remaining)


class MappingEngine:
    name = "base"
    def __init__(self, db, config, *, client=None, limiter=None):
        self.db, self.config = db, config
        rates = config.get("rates", {})
        self.limiter = limiter or RateLimiter(db, self.name,
            min_interval=rates.get(self.name + "_min_interval", 1),
            daily=int(rates.get(self.name + "_daily", 200)))
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)

    def request(self, method, url, **kwargs):
        for attempt in range(2):
            self.limiter.acquire()
            reply = self.client.request(method, url, **kwargs)
            if reply.status_code == 429 and attempt == 0:
                time.sleep(min(60, max(1, float(reply.headers.get("Retry-After", 5)))))
                continue
            reply.raise_for_status()
            return reply.json()
        raise RuntimeError(f"{self.name}: persistent rate limit")

    def ingest(self, assets, query, *, exact=False, short_name=False):
        confidence = classify(query, exact=exact, short_name=short_name)
        count = 0
        for item in assets:
            item.source, item.confidence = self.name, confidence
            if self.db.asset(item):
                count += 1
        return count

    def close(self):
        self.client.close()


def asset_from(host="", ip="", port=443, **fields):
    host = host or ip
    if not host:
        return None
    if "://" in host:
        parsed = urlsplit(host)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host = parsed.hostname
    try:
        return Asset(host=normalize_host(host), ip=ip or "", port=int(port), **fields)
    except (ValueError, TypeError):
        return None


def joined(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value or "")
