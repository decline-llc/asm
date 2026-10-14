"""Encrypted-resolver (DoH) trusted path and hijacked-answer handling.

Every network interaction here is a local httpx MockTransport: no test reaches a real
resolver or target.
"""
import base64
import json
from types import SimpleNamespace

import dns.flags
import dns.message
import dns.rcode
import dns.rdatatype
import dns.resolver
import httpx
import pytest

from asm.models import Domain
from asm.scope import Scope
from asm.stages import s4_subdomain, s5_dns_cdn
from asm.stages.s5_dns_cdn import ingest
from asm.stages.s6_port import selected_targets
from asm.utils.dns import DEFAULT_RESOLVERS, DNSSettings, doh_endpoint, doh_query

ENDPOINT = "https://223.5.5.5/dns-query"


def context(db, tmp_path, *, passive=True, settings=None, target_local=False):
    scope = Scope({"authorization": True, "targets": {"roots": ["example.invalid"],
                  "ip_cidrs": ["192.0.2.0/24"]}}, passive_only=passive)
    def note(kind, target, evidence):
        db.finding({"kind": kind, "url": target, "evidence": evidence, "status": "review"})
    return SimpleNamespace(db=db, scope=scope, config=settings or {}, passive_only=passive,
                           target_local=target_local, note=note,
                           write=lambda name, value: (tmp_path / name).write_text(json.dumps(value)))


def wire(domain, rtype, values, *, rcode=dns.rcode.NOERROR, truncated=False, extra=()):
    query = dns.message.make_query(domain + ".", dns.rdatatype.from_text(rtype))
    if rcode == dns.rcode.NXDOMAIN:
        response = dns.message.make_response(query)
        response.set_rcode(rcode)
    else:
        response = dns.message.make_response(query)
        response.set_rcode(rcode)
        if values:
            response.answer.append(dns.rrset.from_text_list(domain + ".", 60, "IN", rtype, values))
    for rrset in extra:
        response.answer.append(rrset)
    if truncated:
        response.flags |= dns.flags.TC
    return response.to_wire()


def client_for(payload, *, status=200, content_type="application/dns-message", log=None, raises=None):
    def handler(request):
        if log is not None:
            log.append(request)
        if raises is not None:
            raise raises
        return httpx.Response(status, content=payload, headers={"content-type": content_type})
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def test_encrypted_endpoint_validation():
    assert doh_endpoint("https://223.5.5.5/dns-query") == "https://223.5.5.5/dns-query"
    assert doh_endpoint("https://223.5.5.5:443/dns-query") == "https://223.5.5.5/dns-query"
    assert doh_endpoint("  https://223.5.5.5:8443/dns-query ") == "https://223.5.5.5:8443/dns-query"
    assert doh_endpoint("https://[2606:4700:4700::1111]/dns-query") == "https://[2606:4700:4700::1111]/dns-query"
    for value in ("http://223.5.5.5/dns-query", "https://dns.alidns.com/dns-query", "https://223.5.5.5",
                  "https://user:pass@223.5.5.5/dns-query", "https://223.5.5.5/dns-query?x=1",
                  "https://223.5.5.5/dns-query#f", "https://223.5.5.5:0/dns-query", "", "not a url"):
        with pytest.raises(ValueError):
            doh_endpoint(value)


def test_encrypted_resolver_configuration():
    settings = DNSSettings.from_config({"dns": {"resolvers": ["223.5.5.5"], "doh_resolvers":
                                      [ENDPOINT, ENDPOINT, "https://1.12.12.12:443/dns-query"]}})
    assert settings.doh_resolvers == (ENDPOINT, "https://1.12.12.12/dns-query")
    assert settings.doh_trusted is True
    assert DNSSettings().doh_resolvers == () and DNSSettings().doh_trusted is True
    for values in ({"doh_resolvers": "https://223.5.5.5/dns-query"},
                   {"doh_resolvers": ["https://223.5.5.5/dns-query"] * 5},
                   {"doh_resolvers": ["223.5.5.5"]}, {"doh_resolvers": [1]}, {"doh_trusted": "false"}):
        with pytest.raises(ValueError):
            DNSSettings.from_config({"dns": values})


def test_encrypted_query_wire_format_and_record_types():
    log = []
    client = client_for(wire("app.example.invalid", "A", ["192.0.2.20"]), log=log)
    try:
        result = doh_query("app.example.invalid", "A", ENDPOINT, client=client)
    finally:
        client.close()
    assert result["source"] == "doh" and result["resolver"] == ENDPOINT
    assert result["status"] == "NOERROR" and result["answers"] == [
        {"name": "app.example.invalid", "rtype": "A", "value": "192.0.2.20"}]
    request = log[0]
    assert request.method == "GET" and request.headers["accept"] == "application/dns-message"
    assert "dns=" in str(request.url)
    encoded = httpx.QueryParams(str(request.url).split("?", 1)[1])["dns"]
    sent = dns.message.from_wire(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert str(sent.question[0].name) == "app.example.invalid." and sent.question[0].rdtype == dns.rdatatype.A


@pytest.mark.parametrize("rtype,values,expected", [
    ("A", ["192.0.2.20"], "192.0.2.20"),
    ("AAAA", ["2001:db8::20"], "2001:db8::20"),
    ("MX", ["10 mail.example.invalid."], "10 mail.example.invalid"),
    ("NS", ["ns1.example.invalid."], "ns1.example.invalid"),
    ("CNAME", ["edge.example.invalid."], "edge.example.invalid"),
])
def test_encrypted_query_supported_record_types(rtype, values, expected):
    client = client_for(wire("app.example.invalid", rtype, values))
    try:
        result = doh_query("app.example.invalid", rtype, ENDPOINT, client=client)
    finally:
        client.close()
    assert [answer["value"] for answer in result["answers"]] == [expected]


def test_encrypted_query_negative_and_error_responses():
    client = client_for(wire("absent.example.invalid", "A", [], rcode=dns.rcode.NXDOMAIN))
    try:
        assert doh_query("absent.example.invalid", "A", ENDPOINT, client=client)["status"] == "NXDOMAIN"
    finally:
        client.close()
    client = client_for(wire("app.example.invalid", "A", [], rcode=dns.rcode.SERVFAIL))
    try:
        failed = doh_query("app.example.invalid", "A", ENDPOINT, client=client)
    finally:
        client.close()
    assert (failed["status"], failed["error"]) == ("ERROR", "SERVFAIL")
    client = client_for(b"", status=503)
    try:
        assert doh_query("app.example.invalid", "A", ENDPOINT, client=client)["error"] == "HTTP 503"
    finally:
        client.close()


def test_encrypted_query_rejects_unusable_payloads():
    cases = [
        (client_for(wire("app.example.invalid", "A", ["192.0.2.20"]), content_type="text/html"), "UnexpectedContentType"),
        (client_for(b"\x00" * 70000), "ResponseTooLarge"),
        (client_for(wire("app.example.invalid", "A", ["192.0.2.20"], truncated=True)), "Truncated"),
        (client_for(wire("other.example.invalid", "A", ["192.0.2.20"])), "QuestionMismatch"),
    ]
    try:
        for client, error in cases:
            result = doh_query("app.example.invalid", "A", ENDPOINT, client=client)
            assert (result["status"], result["error"]) == ("ERROR", error)
    finally:
        for client, _ in cases:
            client.close()
    # An undecodable body reports the dnspython failure class rather than a fabricated status.
    client = client_for(b"not-a-dns-message")
    try:
        malformed = doh_query("app.example.invalid", "A", ENDPOINT, client=client)
    finally:
        client.close()
    assert malformed["status"] == "ERROR" and malformed["error"] and malformed["answers"] == []
    client = client_for(b"", raises=httpx.ConnectTimeout("timed out"))
    try:
        assert doh_query("app.example.invalid", "A", ENDPOINT, client=client)["error"] == "ConnectTimeout"
    finally:
        client.close()


def test_encrypted_query_ignores_unrelated_and_unsupported_answers():
    unrelated = dns.rrset.from_text_list("outside.invalid.", 60, "IN", "A", ["192.0.2.99"])
    cname = dns.rrset.from_text_list("app.example.invalid.", 60, "IN", "CNAME", ["edge.example.invalid."])
    target = dns.rrset.from_text_list("edge.example.invalid.", 60, "IN", "A", ["192.0.2.30"])
    client = client_for(wire("app.example.invalid", "A", [], extra=(unrelated, cname, target)))
    try:
        result = doh_query("app.example.invalid", "A", ENDPOINT, client=client)
    finally:
        client.close()
    assert [answer["value"] for answer in result["answers"]] == ["192.0.2.30"]
    client = client_for(wire("app.example.invalid", "A", ["192.0.2.20"]))
    try:
        assert doh_query("app.example.invalid", "SOA", ENDPOINT, client=client)["error"] == "UnsupportedQueryType"
    finally:
        client.close()


def test_encrypted_query_client_hardening(monkeypatch):
    captured = {}
    real = httpx.Client
    def factory(**kwargs):
        captured.update(kwargs)
        return real(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=wire("app.example.invalid", "A", ["192.0.2.20"]),
                                           headers={"content-type": "application/dns-message"})), **kwargs)
    monkeypatch.setattr(httpx, "Client", factory)
    result = doh_query("app.example.invalid", "A", ENDPOINT, timeout=5)
    assert result["status"] == "NOERROR"
    assert captured["follow_redirects"] is False and captured["trust_env"] is False and captured["timeout"] == 5


def test_stage5_prefers_encrypted_answers_over_hijacked_plaintext(db, tmp_path):
    db.domain(Domain("app.example.invalid"))
    config = {"dns": {"resolvers": ["1.1.1.1"], "preferred_resolver": "1.1.1.1",
                      "doh_resolvers": [ENDPOINT]}}
    ctx = context(db, tmp_path, settings=config)
    observations = [
        {"domain": "app.example.invalid", "resolver": "1.1.1.1", "source": "dig", "rtype": "A",
         "status": "NOERROR", "answers": [{"rtype": "A", "value": "198.18.0.8"}]},
        {"domain": "app.example.invalid", "resolver": ENDPOINT, "source": "doh", "rtype": "A",
         "status": "NOERROR", "answers": [{"rtype": "A", "value": "192.0.2.44"}]},
    ]
    result = ingest(ctx, observations, DNSSettings.from_config(config))
    evidence = db.get_fact("dns:app.example.invalid")
    assert evidence["selected"]["A"] == ["192.0.2.44"]
    assert evidence["doh_verification"]["trusted"] is True
    assert evidence["doh_verification"]["selected_from"] == "doh"
    assert evidence["doh_verification"]["status"] == "unavailable"  # plaintext yielded nothing usable
    assert selected_targets(ctx) == ["192.0.2.44"]
    assert result.status == "completed"


def test_stage5_records_disagreement_between_paths(db, tmp_path):
    db.domain(Domain("app.example.invalid"))
    config = {"dns": {"resolvers": ["1.1.1.1"], "preferred_resolver": "1.1.1.1", "doh_resolvers": [ENDPOINT]}}
    ctx = context(db, tmp_path, settings=config)
    observations = [
        {"domain": "app.example.invalid", "resolver": "1.1.1.1", "source": "dig", "rtype": "A",
         "status": "NOERROR", "answers": [{"rtype": "A", "value": "192.0.2.10"}]},
        {"domain": "app.example.invalid", "resolver": ENDPOINT, "source": "doh", "rtype": "A",
         "status": "NOERROR", "answers": [{"rtype": "A", "value": "192.0.2.50"}]},
    ]
    result = ingest(ctx, observations, DNSSettings.from_config(config))
    evidence = db.get_fact("dns:app.example.invalid")
    assert evidence["doh_verification"] == {"resolvers": [ENDPOINT], "trusted": True, "compared": ["A"],
                                           "differences": ["A"], "selected_from": "doh", "status": "mismatch"}
    assert evidence["selected"]["A"] == ["192.0.2.50"] and result.status == "partial"
    assert {row["kind"] for row in db.rows("SELECT kind FROM findings")} == {"dns_doh_mismatch"}


def test_stage5_falls_back_when_encrypted_path_fails(db, tmp_path):
    db.domain(Domain("app.example.invalid"))
    config = {"dns": {"resolvers": ["1.1.1.1"], "preferred_resolver": "1.1.1.1", "doh_resolvers": [ENDPOINT]}}
    ctx = context(db, tmp_path, settings=config)
    observations = [
        {"domain": "app.example.invalid", "resolver": "1.1.1.1", "source": "dig", "rtype": "A",
         "status": "NOERROR", "answers": [{"rtype": "A", "value": "192.0.2.10"}]},
        {"domain": "app.example.invalid", "resolver": ENDPOINT, "source": "doh", "rtype": "A",
         "status": "ERROR", "error": "ConnectTimeout", "answers": []},
    ]
    ingest(ctx, observations, DNSSettings.from_config(config))
    evidence = db.get_fact("dns:app.example.invalid")
    assert evidence["selected"]["A"] == ["192.0.2.10"]
    assert evidence["doh_verification"]["trusted"] is False
    assert evidence["doh_verification"]["status"] == "unavailable"
    assert evidence["doh_verification"]["selected_from"] == "plaintext"


def test_stage5_without_encrypted_resolvers_is_unchanged(db, tmp_path):
    db.domain(Domain("app.example.invalid"))
    ctx = context(db, tmp_path, settings={"dns": {"resolvers": ["1.1.1.1"], "preferred_resolver": "1.1.1.1"}})
    observations = [{"domain": "app.example.invalid", "resolver": "1.1.1.1", "source": "dig", "rtype": "A",
                     "status": "NOERROR", "answers": [{"rtype": "A", "value": "192.0.2.10"}]}]
    ingest(ctx, observations, DNSSettings.from_config(ctx.config))
    evidence = db.get_fact("dns:app.example.invalid")
    assert evidence["selected"]["A"] == ["192.0.2.10"]
    assert evidence["doh_verification"]["status"] == "disabled"
    assert evidence["doh_verification"]["selected_from"] == "plaintext"


def test_stage5_rejects_loopback_answers_for_public_targets(db, tmp_path):
    db.domain(Domain("app.example.invalid"))
    ctx = context(db, tmp_path)
    observations = [{"domain": "app.example.invalid", "resolver": "114.114.114.114", "source": "windows",
                     "rtype": "A", "status": "NOERROR", "answers": [{"rtype": "A", "value": "127.0.0.1"}]}]
    result = ingest(ctx, observations, DNSSettings())
    evidence = db.get_fact("dns:app.example.invalid")
    assert evidence["selected"]["A"] == [] and evidence["rejected"][0]["reason"] == "loopback"
    assert selected_targets(ctx) == [] and result.status == "partial"
    assert {row["kind"] for row in db.rows("SELECT kind FROM findings")} == {"dns_loopback_answer"}
    assert db.rows("SELECT value FROM dns_records") == []


def test_stage5_allows_loopback_for_the_local_lab_profile(db, tmp_path):
    db.domain(Domain("localhost"))
    scope = Scope({"authorization": True, "targets": {"roots": ["localhost"], "ip_cidrs": ["127.0.0.1/32"]}},
                  target_local=True)
    ctx = SimpleNamespace(db=db, scope=scope, config={}, passive_only=False, target_local=True,
                          note=lambda *args: None, write=lambda name, value: None)
    observations = [{"domain": "localhost", "resolver": "fixture", "source": "fixture", "rtype": "A",
                     "status": "NOERROR", "answers": [{"rtype": "A", "value": "127.0.0.1"}]}]
    ingest(ctx, observations, DNSSettings())
    assert db.get_fact("dns:localhost")["selected"]["A"] == ["127.0.0.1"]


def test_collect_encrypted_queries_covers_every_domain_and_type(monkeypatch):
    calls = []
    def fake_query(domain, rtype, endpoint, timeout):
        calls.append((domain, rtype, endpoint))
        return {"domain": domain, "rtype": rtype, "resolver": endpoint, "source": "doh",
                "status": "NOERROR", "answers": [], "error": ""}
    monkeypatch.setattr(s5_dns_cdn, "doh_query", fake_query)
    settings = DNSSettings.from_config({"dns": {"doh_resolvers": [ENDPOINT, "https://1.12.12.12/dns-query"]}})
    observations = s5_dns_cdn.collect_doh(["a.example.invalid"], settings)
    assert len(observations) == 10 and len(calls) == 10
    assert {call[2] for call in calls} == set(settings.doh_resolvers)
    assert s5_dns_cdn.collect_doh(["a.example.invalid"], DNSSettings()) == []


def test_stage4_resolution_never_inherits_host_resolver_configuration(monkeypatch):
    seen = {}
    class FakeResolver:
        def __init__(self, configure=True):
            seen["configure"] = configure
            self.nameservers, self.port, self.timeout, self.lifetime = [], 53, None, None
        def resolve(self, domain, rtype, search=True):
            seen.update(nameservers=list(self.nameservers), port=self.port, domain=domain,
                        rtype=rtype, search=search)
            return ["192.0.2.70", "192.0.2.71."]
    monkeypatch.setattr(dns.resolver, "Resolver", FakeResolver)
    assert s4_subdomain.resolve("app.example.invalid", "A", "114.114.114.114:5353") == ["192.0.2.70", "192.0.2.71"]
    assert seen["configure"] is False and seen["nameservers"] == ["114.114.114.114"]
    assert seen["port"] == 5353 and seen["search"] is False
    assert s4_subdomain.resolve("app.example.invalid", "A") == ["192.0.2.70", "192.0.2.71"]
    assert seen["nameservers"] == [DEFAULT_RESOLVERS[1]]


def test_encrypted_resolvers_stay_out_of_existing_fingerprints(tmp_path):
    from asm.conf import load_config
    legacy = {"profile": "legacy-fixture", "authorization": False,
              "dns": {"resolvers": ["223.5.5.5"], "preferred_resolver": "223.5.5.5"}}
    profile = tmp_path / "legacy.yaml"
    profile.write_text(json.dumps(legacy), encoding="utf-8")
    config = load_config(str(profile), root=tmp_path)
    # The effective DNS block keeps the historical key set, so resume fingerprints of
    # existing projects are not reported as changed by this feature.
    assert set(config.data["dns"]) == {"resolvers", "preferred_resolver", "timeout", "workers",
                                      "max_cname_hops", "dnsx", "windows_verify", "reject_fake_ip",
                                      "takeover_probe"}
    enabled = {**legacy, "profile": "doh-fixture", "dns": {**legacy["dns"],
               "doh_resolvers": ["https://223.5.5.5/dns-query"]}}
    profile.write_text(json.dumps(enabled), encoding="utf-8")
    encrypted = load_config(str(profile), root=tmp_path)
    assert encrypted.data["dns"]["doh_resolvers"] == [ENDPOINT]
    assert encrypted.data["dns"]["doh_trusted"] is True
    assert encrypted.snapshot() != config.snapshot()


def test_encrypted_resolvers_flow_through_the_policy_plan(tmp_path, project):
    from asm.conf import load_config
    from asm.policy import effective_config
    modes = project / "profiles/modes.yaml"
    base = {"schema_version": 2, "profile": "doh-plan", "authorization": False, "mode_preset": "passive_discovery",
            "dns": {"resolvers": ["223.5.5.5"], "preferred_resolver": "223.5.5.5",
                    "doh_resolvers": [ENDPOINT], "doh_trusted": False}}
    expanded = effective_config(base, modes)
    assert expanded["plan"]["params"]["dns_recursive"]["doh_resolvers"] == [ENDPOINT]
    assert expanded["plan"]["params"]["dns_recursive"]["doh_trusted"] is False
    profile = tmp_path / "doh-plan.yaml"
    profile.write_text(json.dumps(base), encoding="utf-8")
    config = load_config(str(profile), root=project)
    assert DNSSettings.from_config(config.data).doh_trusted is False


def test_stage4_trusted_resolver_discards_hijacked_dictionary_answers():
    poisoned = lambda domain, rtype="A", nameserver=None: ["127.0.0.1"]  # noqa: E731
    assert s4_subdomain.trusted_resolver(DNSSettings(), resolver=poisoned)("api.example.invalid") == []
    mixed = lambda domain, rtype="A", nameserver=None: ["192.0.2.5", "198.18.0.9", "0.0.0.0"]  # noqa: E731
    assert s4_subdomain.trusted_resolver(DNSSettings(), resolver=mixed)("api.example.invalid") == ["192.0.2.5"]


def test_stage4_hijacked_answers_cannot_manufacture_subdomains():
    poisoned = lambda domain, rtype="A", nameserver=None: ["127.0.0.1"]  # noqa: E731
    lookup = s4_subdomain.trusted_resolver(DNSSettings(), resolver=poisoned)
    assert s4_subdomain.wildcard("example.invalid", lookup) is False
    wild, records = s4_subdomain.enumerate_dns("example.invalid", resolver=lookup)
    assert wild is False and records == []