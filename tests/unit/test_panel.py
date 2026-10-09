import time

import httpx
import pytest

from asm.db import Database
from asm.panel.base import QuotaExceeded, RateLimiter
from asm.panel.censys import Censys
from asm.panel.fofa import Fofa
from asm.panel.hunter import Hunter
from asm.panel.quake import Quake
from asm.panel.shodan import Shodan
from asm.panel.zoomeye import ZoomEye


class Clock:
    def __init__(self):
        self.now = 1_700_000_000.0
        self.sleeps = []
    def time(self):
        return self.now
    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_persistent_quota_and_interval(tmp_path):
    clock = Clock()
    path = tmp_path / "quota.db"
    with Database(path) as db:
        limiter = RateLimiter(db, "fofa", min_interval=0.1, daily=2, clock=clock.time, sleeper=clock.sleep)
        limiter.acquire()
        limiter.acquire()
        assert clock.sleeps == [15]
        with pytest.raises(QuotaExceeded):
            limiter.acquire()
    with Database(path) as reopened:
        limiter = RateLimiter(reopened, "fofa", daily=2, clock=clock.time, sleeper=clock.sleep)
        with pytest.raises(QuotaExceeded):
            limiter.acquire()
    clock.now += 24 * 3600
    with Database(path) as reopened:
        RateLimiter(reopened, "fofa", daily=2, clock=clock.time, sleeper=clock.sleep).acquire()


def test_engine_parsers(db):
    fixtures = [
        (Fofa, {"results": [["https://api.example.invalid", "192.0.2.1", 443, "https", "Fixture", "example.invalid", "nginx"]]}),
        (Quake, {"data": [{"ip": "192.0.2.1", "port": 443, "domain": "api.example.invalid", "service": {"name": "http", "http": {"title": "Fixture"}}}]}),
        (Hunter, {"data": {"arr": [{"ip": "192.0.2.1", "port": 443, "domain": "api.example.invalid", "web_title": "Fixture"}]}}),
        (ZoomEye, {"data": [{"ip": "192.0.2.1", "port": 443, "domain": "api.example.invalid", "title": "Fixture"}]}),
        (Shodan, {"matches": [{"ip_str": "192.0.2.1", "port": 443, "hostnames": ["api.example.invalid"]}]}),
        (Censys, {"result": {"hits": [{"ip": "192.0.2.1", "services": [{"port": 443, "service_name": "HTTPS"}]}]}}),
    ]
    for engine, response in fixtures:
        assets = list(engine.parse(response))
        assert len(assets) == 1 and assets[0].ip == "192.0.2.1" and assets[0].port == 443
        panel = engine(db, {}, client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))))
        assert panel.ingest(assets, 'body:"Fixture"') == 1
        panel.close()
    assert db.rows("SELECT COUNT(*) n FROM assets")[0]["n"] == 0
    assert "cert.subject.cn=" in Fofa.cert_query("example.invalid")
    assert "cert.subject.org=" in Fofa.cert_query("Fixture", organization=True)


@pytest.mark.slow
def test_fofa_real_15_second_interval(db):
    limiter = RateLimiter(db, "fofa", min_interval=1, daily=2)
    calls = []
    def handle(request):
        calls.append(time.monotonic())
        return httpx.Response(200, json={"results": []})
    panel = Fofa(db, {}, client=httpx.Client(transport=httpx.MockTransport(handle)), limiter=limiter)
    panel.request("GET", "https://fixture.invalid/first")
    panel.request("GET", "https://fixture.invalid/second")
    assert calls[1] - calls[0] >= 14.99
    assert len(calls) == 2
    with pytest.raises(QuotaExceeded):
        panel.request("GET", "https://fixture.invalid/exhausted")
    assert len(calls) == 2
    panel.close()
