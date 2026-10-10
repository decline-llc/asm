import json
from types import SimpleNamespace

import pytest

from asm.models import Domain
from asm.scope import Scope, ScopeError
from asm.stages.s5_dns_cdn import corrected_answers, ingest, parse_dnsx
from asm.stages.s6_port import selected_targets
from asm.utils.dns import DNSSettings, endpoint, parse_dig, record_value, windows_query
from tests.fixtures.dns_server import DNSFixture


def context(db, tmp_path, *, passive=True, settings=None):
    scope = Scope({"authorization": True, "targets": {"roots": ["example.invalid"],
                  "ip_cidrs": ["192.0.2.0/24"]}}, passive_only=passive)
    def note(kind, target, evidence):
        db.finding({"kind": kind, "url": target, "evidence": evidence, "status": "review"})
    return SimpleNamespace(db=db, scope=scope, config=settings or {}, passive_only=passive,
                           note=note, write=lambda name, value: (tmp_path / name).write_text(json.dumps(value)))


def test_resolver_configuration():
    assert endpoint("[::1]:5353") == "[::1]:5353"
    assert endpoint("1.1.1.1:53") == "1.1.1.1"
    assert DNSSettings.from_config({"dns": {"resolvers": ["127.0.0.1:5353"]}}).preferred == "127.0.0.1:5353"
    for values in ({"resolvers": []}, {"resolvers": ["dns.example.invalid"]}, {"resolvers": ["1.1.1.1:0"]},
                   {"workers": True}, {"workers": 2.5}, {"takeover_probe": "false"},
                   {"preferred_resolver": "9.9.9.9"}):
        with pytest.raises(ValueError):
            DNSSettings.from_config({"dns": values})


def test_windows_explicit_resolver_and_negative_response():
    server = DNSFixture({"app.example.invalid": {"A": ["192.0.2.20"], "AAAA": ["2001:db8::20"]}})
    try:
        resolver = f"127.0.0.1:{server.port}"
        assert windows_query("app.example.invalid", "A", resolver)["answers"][0]["value"] == "192.0.2.20"
        assert windows_query("app.example.invalid", "AAAA", resolver)["answers"][0]["value"] == "2001:db8::20"
        assert windows_query("missing.example.invalid", "A", resolver)["status"] == "NXDOMAIN"
        assert windows_query("app.example.invalid", "MX", resolver)["status"] == "NOERROR"
    finally:
        server.close()


def test_dns_parsers_and_bad_addresses(tmp_path):
    text = ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1\napp.example.invalid. 60 IN A 192.0.2.1\n"
    assert parse_dig(text)["answers"][0]["value"] == "192.0.2.1"
    path = tmp_path / "dnsx.jsonl"
    path.write_text('\n'.join(json.dumps(row) for row in [
        {"host": "app.example.invalid", "a": ["192.0.2.1"], "mx": ["mail.example.invalid"]},
        {"host": "outside.invalid", "a": ["192.0.2.2"]}]))
    rows = list(parse_dnsx(path, "1.1.1.1", {"app.example.invalid"}))
    assert len(rows) == 1 and rows[0]["answers"][1]["value"] == "mail.example.invalid"
    for value in ("0.0.0.0", "::", "198.18.0.5", "198.19.255.255"):
        with pytest.raises(ValueError):
            record_value("AAAA" if ":" in value else "A", value)
    assert record_value("A", "198.18.0.5", reject_fake_ip=False) == "198.18.0.5"
    assert record_value("MX", "0 .") == "0 ."
    assert corrected_answers({"1.1.1.1": ["0.0.0.0", "192.0.2.1"],
                             "114.114.114.114": ["192.0.2.2"]}) == ["192.0.2.2"]


def test_ingest_correction_chain_and_port_handoff(db, tmp_path, monkeypatch):
    db.domain(Domain("app.example.invalid"))
    ctx = context(db, tmp_path, settings={"dns": {"takeover_probe": True}})
    from asm.stages import s5_dns_cdn
    monkeypatch.setattr(s5_dns_cdn, "probe_takeover", lambda *args: pytest.fail("Passive mode must not probe HTTP"))
    observations = []
    for resolver, address in (("1.1.1.1", "192.0.2.1"), ("114.114.114.114", "192.0.2.2"),
                              ("8.8.8.8", "198.18.0.8")):
        observations.append({"domain": "app.example.invalid", "resolver": resolver, "source": "dig",
            "status": "NOERROR", "answers": [{"rtype": "A", "value": address}]})
    observations.append({"domain": "app.example.invalid", "resolver": "1.1.1.1", "source": "dig",
        "kind": "cname_chain", "chain": ["edge.other.invalid", "fixture.gccdn.net"],
        "terminal": "fixture.gccdn.net", "status": "complete"})
    result = ingest(ctx, observations, DNSSettings.from_config(ctx.config))
    assert result.status == "completed"
    evidence = db.get_fact("dns:app.example.invalid")
    assert evidence["selected"]["A"] == ["192.0.2.2"] and evidence["differences"]["A"]
    assert db.get_fact("cdn:app.example.invalid")
    assert selected_targets(ctx) == ["192.0.2.2"]
    assert not db.rows("SELECT * FROM dns_records WHERE value LIKE '198.18.%'")
    assert db.rows("SELECT domain FROM domains") == [{"domain": "app.example.invalid"}]
    assert db.rows("SELECT kind FROM findings") == [{"kind": "dns_unusable_answer"}]


def test_failed_resolution_and_explicit_fake_target(db, tmp_path):
    db.domain(Domain("app.example.invalid"))
    ctx = context(db, tmp_path)
    result = ingest(ctx, [], DNSSettings())
    assert result.status == "partial" and selected_targets(ctx) == []
    ctx.config = {"ports": {"targets": ["198.18.0.1"]}}
    with pytest.raises(ScopeError):
        selected_targets(ctx)


def test_same_resolver_sources_stay_separate(db, tmp_path):
    db.domain(Domain("app.example.invalid"))
    ctx = context(db, tmp_path)
    observations = [{"domain": "app.example.invalid", "resolver": "114.114.114.114", "source": source,
        "rtype": "A", "status": "NOERROR", "answers": [{"rtype": "A", "value": address}]}
        for source, address in (("dig", "192.0.2.20"), ("windows", "192.0.2.30"), ("dnsx", "192.0.2.40"))]
    result = ingest(ctx, observations, DNSSettings())
    assert result.status == "partial"
    evidence = db.get_fact("dns:app.example.invalid")
    assert evidence["selected"]["A"] == ["192.0.2.20"]
    assert evidence["by_source"]["114.114.114.114"]["windows"]["A"] == ["192.0.2.30"]
    assert evidence["source_differences"]["114.114.114.114"]["A"]
    assert evidence["windows_verification"]["differences"] == ["A"]
    assert selected_targets(ctx) == ["192.0.2.20"]
    assert len(db.rows("SELECT * FROM dns_records WHERE rtype='A'")) == 3


def test_windows_timeout_is_observable():
    server = DNSFixture({"timeout.example.invalid": {"DROP": True}})
    try:
        observation = windows_query("timeout.example.invalid", "A", f"127.0.0.1:{server.port}", timeout=0.1)
        assert observation["status"] == "ERROR" and observation["answers"] == [] and observation["error"]
    finally:
        server.close()


def test_takeover_probe_retains_fingerprint_and_uses_original_host(db, tmp_path, monkeypatch):
    from asm.stages import s5_dns_cdn
    calls = []
    class Client:
        def __init__(self, scope, timeout):
            self.scope = scope

        def get(self, url):
            self.scope.assert_in_scope(url)
            calls.append(url)
            return SimpleNamespace(status=404, text="<Error>NoSuchBucket</Error>", url=url)

        def close(self):
            pass
    monkeypatch.setattr(s5_dns_cdn, "TargetHTTP", Client)
    s5_dns_cdn.probe_takeover(context(db, tmp_path, passive=False), "app.example.invalid", "bucket.s3.amazonaws.com")
    assert calls == ["https://app.example.invalid/"]
    rows = db.rows("SELECT * FROM takeovers")
    assert len(rows) == 1 and rows[0]["status"] == "review"
    evidence = json.loads(rows[0]["evidence"])
    assert evidence["matched_text"] == "NoSuchBucket" and len(evidence["body_sha256"]) == 64
    from openpyxl import load_workbook
    from asm.stages.s8_report import write_report
    report = tmp_path / "report.xlsx"
    counts = write_report(db, report)
    book = load_workbook(report)
    assert counts["todos"] == 1 and book["todos"]["A2"].value == "takeover_candidate"
    assert book["todos"]["B2"].value == "https://app.example.invalid/"
    assert '"provider": "Amazon S3"' in book["todos"]["C2"].value
    assert book["todos"]["E2"].value == "review"
    book.close()
