"""FOFA cache/degradation/budget behavior uses only MockTransport and fake time."""
import json
import socket
import subprocess

import httpx
import pytest

from asm.panel.base import QuotaExceeded, RateLimiter
from asm.panel.fofa import Fofa
from tests.unit.test_panel import Clock


@pytest.fixture(autouse=True)
def credentials_and_no_network(monkeypatch):
    monkeypatch.setenv("FOFA_EMAIL", "fixture-account@example.invalid")
    monkeypatch.setenv("FOFA_KEY", "DUMMY_FIXTURE_API_KEY")
    Fofa.clear_account_cache()
    def forbidden(*args, **kwargs):
        raise AssertionError("FOFA test attempted external I/O")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    yield
    Fofa.clear_account_cache()


def panel(db, handler, clock, *, daily=20):
    limiter = RateLimiter(db, "fofa", daily=daily, clock=clock.time, sleeper=clock.sleep)
    return Fofa(db, {}, client=httpx.Client(transport=httpx.MockTransport(handler)), limiter=limiter, clock=clock.time)


def one_asset():
    return {"results": [["https://api.example.invalid", "192.0.2.1", 443, "https", "Fixture", "example.invalid", "nginx"]]}


def test_account_info_cached_across_queries_and_instances_then_expires(db):
    clock, calls = Clock(), []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"email": "fixture-account@example.invalid", "key": "DUMMY_FIXTURE_API_KEY"}
                              if request.url.path.endswith("/info/my") else one_asset())
    first = panel(db, handler, clock)
    assert len(list(first.search("fixture", max_pages=1))) == 1
    assert len(list(first.search("another fixture", max_pages=1))) == 1
    first.close()
    second = panel(db, handler, clock)
    assert len(list(second.search("third fixture", max_pages=1))) == 1
    assert calls.count("/api/v1/info/my") == 1
    assert second.health["account"]["cached"]
    clock.now += 601
    assert len(list(second.search("expired fixture", max_pages=1))) == 1
    assert calls.count("/api/v1/info/my") == 2
    assert db.rows("SELECT used FROM sources")[0]["used"] == 6
    second.close()


def test_account_failure_is_cached_and_does_not_block_search(db):
    clock, calls = Clock(), []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(503, json={}) if request.url.path.endswith("/info/my") else httpx.Response(200, json=one_asset())
    engine = panel(db, handler, clock)
    assert len(list(engine.search("fixture", max_pages=1))) == 1
    assert engine.last_errors[0]["operation"] == "account_info" and engine.last_errors[0]["http_status"] == 503
    assert engine.health["status"] == "degraded"
    assert len(list(engine.search("fixture again", max_pages=1))) == 1
    assert calls.count("/api/v1/info/my") == 1 and engine.last_errors[0]["cached"]
    engine.close()


def test_optional_account_info_and_requested_output_fields(db):
    clock, calls = Clock(), []
    def handler(request):
        calls.append(request)
        assert request.url.params["fields"] == "domain,port"
        assert request.url.params["size"] == "3"
        return httpx.Response(200, json={"results": [["api.example.invalid", 8443]]})
    engine = panel(db, handler, clock)
    assets = list(engine.search("fixture", fields=["domain", "port"], size=3, max_pages=1, check_account=False))
    assert len(assets) == 1 and assets[0].port == 8443
    assert len(calls) == 1 and engine.health["account"]["status"] == "not_requested"
    engine.close()


def test_820000_error_preserves_code_and_redacts_errmsg_without_raising(db):
    clock = Clock()
    engine = panel(db, lambda request: httpx.Response(200, json={"error": True,
        "errmsg": "[820000] fixture-account@example.invalid DUMMY_FIXTURE_API_KEY field unavailable"}), clock)
    assert list(engine.search("fixture", max_pages=1, check_account=False)) == []
    assert engine.last_errors[0]["code"] == 820000
    assert "field unavailable" in engine.last_errors[0]["errmsg"]
    serialized = json.dumps(engine.health)
    assert "fixture-account@example.invalid" not in serialized and "DUMMY_FIXTURE_API_KEY" not in serialized
    assert engine.health["status"] == "degraded"
    engine.close()


def test_explicit_fields_fallback_consumes_same_request_budget(db):
    clock, calls = Clock(), []
    def handler(request):
        calls.append(request.url.params["fields"])
        response = {"error": True, "errmsg": "[820000] optional field unavailable"} if "last_updatetime" in request.url.params["fields"] else one_asset()
        return httpx.Response(200, json=response)
    engine = panel(db, handler, clock)
    assets = list(engine.search("fixture", fields="host,port,last_updatetime", max_pages=1,
                               max_requests=2, check_account=False, fallback_fields=True))
    assert len(assets) == 1 and calls == ["host,port,last_updatetime", Fofa.fields]
    assert engine.health["requests_used"] == 2 and engine.last_errors[0]["code"] == 820000
    assert db.rows("SELECT used FROM sources")[0]["used"] == 2
    engine.close()


@pytest.mark.parametrize("options", [{"fields": "invented_field"}, {"fields": []}, {"fields": "title"},
    {"size": 1001}, {"size": 0}, {"max_pages": 0}, {"max_pages": True}, {"max_requests": 201}])
def test_invalid_fields_and_pagination_fail_before_request(db, options):
    clock, calls = Clock(), []
    engine = panel(db, lambda request: calls.append(request) or httpx.Response(200, json={}), clock)
    with pytest.raises(ValueError):
        list(engine.search("fixture", **options))
    assert calls == [] and db.rows("SELECT * FROM sources") == []
    engine.close()


def test_pages_are_bounded_and_truncation_is_honest(db):
    clock, pages = Clock(), []
    def handler(request):
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx.Response(200, json={"size": 10, "results": [
            [f"https://api{page}.example.invalid", "192.0.2.1", 443, "https", "Fixture", "example.invalid", "nginx"]] * 2})
    engine = panel(db, handler, clock)
    assets = list(engine.search("fixture", size=2, max_pages=2, max_requests=2, check_account=False))
    assert pages == [1, 2] and len(assets) == 2
    assert engine.health["truncated"] and engine.health["stop_reason"] == "max_pages"
    assert engine.health["rows_returned"] == 4 and engine.health["total_estimate"] == 10
    assert db.rows("SELECT used FROM sources")[0]["used"] == 2
    engine.close()


def test_physical_retry_cannot_exceed_query_request_budget(db):
    clock, calls = Clock(), []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "1"}, json={})
    engine = panel(db, handler, clock)
    assert list(engine.search("fixture", max_pages=3, max_requests=1, check_account=False)) == []
    assert len(calls) == 1 and engine.health["requests_used"] == 1
    assert engine.health["stop_reason"] == "request_budget"
    assert db.rows("SELECT used FROM sources")[0]["used"] == 1
    engine.close()


def test_account_and_search_quota_is_never_reset(db):
    clock, calls = Clock(), []
    engine = panel(db, lambda request: calls.append(request) or httpx.Response(200, json=one_asset()), clock, daily=2)
    assert len(list(engine.search("fixture", max_pages=1))) == 1
    with pytest.raises(QuotaExceeded):
        list(engine.search("new fixture", max_pages=1))
    assert len(calls) == 2 and engine.health["status"] == "quota-exhausted"
    assert db.rows("SELECT used FROM sources")[0]["used"] == 2
    engine.close()


def test_account_response_never_returns_credentials_to_trace(db):
    clock = Clock()
    engine = panel(db, lambda request: httpx.Response(200, json={"email": "fixture-account@example.invalid",
        "key": "DUMMY_FIXTURE_API_KEY", "username": "private", "vip_level": 2}), clock)
    response = engine.request("GET", "https://fofa.info/api/v1/info/my")
    assert response["email"] == "[REDACTED]" and response["key"] == "[REDACTED]"
    assert response["username"] == "[REDACTED]" and response["vip_level"] == 2
    engine.close()


def test_search_error_response_is_redacted_before_wrapper_can_record_it(db):
    clock = Clock()
    engine = panel(db, lambda request: httpx.Response(200, json={"error": True,
        "errmsg": "[820000] fixture-account@example.invalid DUMMY_FIXTURE_API_KEY",
        "nested": {"token": "DUMMY_OTHER_TOKEN"}}), clock)
    response = engine.request("GET", "https://fofa.info/api/v1/search/all")
    serialized = json.dumps(response)
    assert "DUMMY_FIXTURE_API_KEY" not in serialized and "fixture-account@example.invalid" not in serialized
    assert "DUMMY_OTHER_TOKEN" not in serialized
    engine.close()
