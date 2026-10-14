"""Company/OSINT/supply adapters use explicit inputs and preserve candidate status."""
import json
import shutil
import socket
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from asm import passive_tools
from asm.orchestrator import RunControlled, Workbench
from asm.policy import ExecutionPolicy, PolicyDenied
from asm.run_store import RunStore, atomic_json


@pytest.fixture(autouse=True)
def deny_real_external(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Passive unit tests attempted real transport, DNS, subprocess or secrets")
    for name in ("getaddrinfo", "gethostbyname", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    for name in ("connect", "connect_ex", "sendto", "sendall"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr("dotenv.load_dotenv", denied)
    monkeypatch.setattr("asm.conf.load_dotenv", denied)


class Context:
    def __init__(self, root, capability, tool, *, target="example.invalid", params=None, source="live"):
        self.target, self.capability = target, capability
        self.params = params or {}
        self.records, self.calls, self.permissions, self.current_assets = [], [], [], []
        self.last_evidence_id, self.checks, self.control_after = None, 0, None
        self.step = {"tool": tool, "id": "unit-step"}
        self.output_directory = root / "evidence"
        config = {"schema_version": 2, "mode_capabilities": [capability], "execution": {"source": source},
            "scope_sets": {"investigation": {"include": ["example.invalid", "192.0.2.10/32", "::1/128"],
                "subjects": ["Fixture Parent"], "queries": ["Fixture Specialized System"], "domain_match": "subdomains"}},
            "permissions": {capability: {"allow": True, "scope_ref": "investigation"}},
            "plan": {"steps": [capability], "selected_tools": [tool]}, "tools": {capability: tool},
            "budgets": {"max_hosts": 100}}
        self.run = {"run_id": "passive-unit", "config": config, "assets": []}
        self.policy = ExecutionPolicy(config)
        self.workbench = SimpleNamespace(root=root, store=RunStore(root / "data/state.sqlite"), run=lambda _: {"assets": self.current_assets})

    def check_control(self):
        self.checks += 1
        if self.control_after is not None and self.checks >= self.control_after:
            raise RunControlled("pausing")

    def wait(self, seconds):
        self.check_control()

    def require(self, target=None, *, network=True, target_kind="host"):
        self.check_control()
        self.permissions.append((target or self.target, network, target_kind))
        return self.policy.require(self.capability, target or self.target, target_kind=target_kind,
                                   network=network, tool=self.step["tool"])

    def call(self, tool, params, operation):
        self.check_control()
        evidence_id = "captured-" + str(len(self.calls) + 1)
        self.last_evidence_id = evidence_id
        row = {"tool": tool, "params": params, "status": "running", "evidence_id": evidence_id}
        self.calls.append(row)
        try:
            value = operation()
        except BaseException as exc:
            row["status"] = "interrupted" if isinstance(exc, RunControlled) else "failed"
            atomic_json(self.output_directory / (evidence_id + ".json"), {"error_type": type(exc).__name__})
            raise
        row["status"] = "completed"
        path = self.output_directory / (evidence_id + ".json")
        atomic_json(path, value)
        self.records.append({"category": "evidence_index", "evidence_id": evidence_id, "path": path.name})
        return value

    def saved(self):
        return "\n".join(p.read_text(encoding="utf-8") for p in self.output_directory.glob("*.json"))


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return name


def equity_rows():
    return [
        {"cid": "root", "name": "Fixture Parent", "website": "https://example.invalid", "password": "DUMMY_EXPORT_SECRET"},
        {"cid": "child", "name": "Fixture Controlled", "parent_cid": "root", "share_pct": 51, "website": "https://child.example.invalid"},
        {"cid": "grandchild", "name": "Fixture Grandchild", "parent_cid": "child", "share_pct": 80, "website": "grand.example.invalid"},
        {"cid": "minority", "name": "Fixture Minority", "parent_cid": "root", "share_pct": 50, "website": "minority.invalid"},
        {"cid": "orphan", "name": "Fixture Orphan", "parent_cid": "missing", "share_pct": 99, "website": "orphan.invalid"},
        {"cid": "other", "name": "Unrelated Export Root", "website": "other.invalid"}]


def test_equity_links_requested_subject_control_path_without_claiming_ownership(tmp_path):
    filename = write(tmp_path, "inputs/equity.json", equity_rows())
    ctx = Context(tmp_path, "company_lookup", "stage_2a", target="Fixture Parent", params={"equity_files": [filename]})
    result = passive_tools.company_lookup(ctx)
    assert result["status"] == "completed" and len(ctx.calls) == 1
    assert {a["domain"] for a in result["assets"]} == {"example.invalid", "child.example.invalid", "grand.example.invalid"}
    organizations = [r for r in result["records"] if r["category"] == "organizations_relationships"]
    assert len(organizations) == 6
    controls = [r for r in organizations if r["relationship"] == "equity_control_candidate"]
    assert {r["organization_id"] for r in controls} == {"child", "grandchild"}
    assert all(r["knowledge"] == "inference" and r["attribution_status"] == "unconfirmed" for r in controls)
    assert all(a["verification_status"] == "candidate_only" and a["confidence"] == "C" for a in result["assets"])
    assert all(not network for _, network, _ in ctx.permissions)
    assert "DUMMY_EXPORT_SECRET" not in ctx.saved()
    captured = json.loads((ctx.output_directory / "captured-1.json").read_text(encoding="utf-8"))
    assert captured["source_sha256"] and captured["content_policy"] == "parsed_fields_only"


def test_equity_include_controlled_entities_and_threshold_affect_leads(tmp_path):
    filename = write(tmp_path, "equity.json", equity_rows())
    root_only = Context(tmp_path, "company_lookup", "stage_2a", target="Fixture Parent",
                        params={"equity_files": [filename], "include_controlled_entities": False})
    assert [a["domain"] for a in passive_tools.company_lookup(root_only)["assets"]] == ["example.invalid"]
    stricter = Context(tmp_path, "company_lookup", "stage_2a", target="Fixture Parent",
                       params={"equity_files": [filename], "min_control_share_pct": 60})
    assert [a["domain"] for a in passive_tools.company_lookup(stricter)["assets"]] == ["example.invalid"]


def test_equity_tool_never_reads_unselected_icp_input(tmp_path):
    filename = write(tmp_path, "equity.json", equity_rows())
    ctx = Context(tmp_path, "company_lookup", "stage_2a", target="Fixture Parent",
                  params={"equity_files": [filename], "icp_files": [".env"]})
    assert passive_tools.company_lookup(ctx)["status"] == "completed"
    assert len(ctx.calls) == 1 and ctx.calls[0]["params"]["kind"] == "equity"


@pytest.mark.parametrize("percentage", ["NaN", -1, 101])
def test_invalid_equity_percentages_are_failed_evidence_not_controlled_entities(tmp_path, percentage):
    rows = equity_rows()
    rows[1]["share_pct"] = percentage
    filename = write(tmp_path, "invalid-equity.json", rows)
    ctx = Context(tmp_path, "company_lookup", "stage_2a", target="Fixture Parent", params={"equity_files": [filename]})
    with pytest.raises(ValueError, match="percentages"):
        passive_tools.company_lookup(ctx)
    assert ctx.calls[0]["status"] == "failed"


def test_icp_saved_response_parsing_emits_observed_numbers_and_unverified_related_leads(tmp_path):
    filename = write(tmp_path, "icp.json", [{"domain": "example.invalid", "status": 200,
        "text": "示ICP备00000000号-1 示ICP备00000000号-2", "related_domains": ["supplier.invalid"]},
        {"domain": "empty.example.invalid", "status": 403, "text": "Denied"}])
    ctx = Context(tmp_path, "company_lookup", "stage_2b", target="Fixture Parent", params={"icp_files": [filename]})
    result = passive_tools.company_lookup(ctx)
    assert result["status"] == "completed" and len(ctx.calls) == 1
    associations = [r for r in result["records"] if r["category"] == "organizations_relationships"]
    assert len(associations[0]["numbers"]) == 2 and len(associations[0]["number_groups"]) == 1
    assert associations[1]["saved_response_branch"] == "snapshot"
    assert {a["domain"] for a in result["assets"]} == {"example.invalid", "empty.example.invalid", "supplier.invalid"}
    assert not ctx.policy.contains("investigation", "supplier.invalid")
    assert all(a["verification_status"] == "candidate_only" for a in result["assets"])
    assert all(not network for _, network, _ in ctx.permissions)


@pytest.mark.parametrize("filename", ["../outside.json", ".env", "inputs/.Env.saved"])
def test_import_boundary_rejects_secrets_and_outside_workspace(tmp_path, filename):
    ctx = Context(tmp_path, "company_lookup", "stage_2a", target="Fixture Parent", params={"equity_files": [filename]})
    with pytest.raises(ValueError, match="workspace|secret"):
        passive_tools.company_lookup(ctx)
    assert ctx.calls == []


@pytest.mark.parametrize("capability,tool,adapter", [("company_lookup", "stage_2a", passive_tools.company_lookup),
    ("osint", "stage_p1", passive_tools.osint), ("passive_supply_chain", "stage_p2", passive_tools.passive_supply_chain)])
def test_missing_inputs_are_truthful_and_replay_never_invokes_live_adapters(tmp_path, capability, tool, adapter):
    replay = Context(tmp_path, capability, tool, target="Fixture Parent", source="replay")
    assert adapter(replay)["reason"] == "replay_uses_saved_replay_adapter" and replay.calls == []
    if capability != "passive_supply_chain":
        live = Context(tmp_path, capability, tool, target="Fixture Parent")
        assert adapter(live)["status"] == "blocked" and live.calls == []


def sourcegraph_fixture(secret="DUMMY_SNIPPET_SECRET", *, count=1):
    matches = [{"type": "content", "repository": "github.com/fixture/example", "path": f"config/example{n}.env",
                "lineMatches": [{"line": "password=" + secret, "lineNumber": 1}]} for n in range(count)]
    return "event: matches\ndata: " + json.dumps(matches) + '\n\nevent: progress\ndata: {"done":true,"matchCount":1}\n\n'


def mock_sourcegraph(monkeypatch, handler):
    original = httpx.Client
    requests = []
    def checked(request):
        requests.append(request)
        assert str(request.url).startswith(passive_tools.SOURCEGRAPH_URL)
        return handler(request)
    monkeypatch.setattr(passive_tools.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(checked), **kwargs))
    return requests


def test_sourcegraph_real_adapter_uses_explicit_provider_shared_ledger_and_sanitized_locations(tmp_path, monkeypatch):
    requests = mock_sourcegraph(monkeypatch, lambda request: httpx.Response(200, text=sourcegraph_fixture()))
    ctx = Context(tmp_path, "osint", "sourcegraph_stream", params={"max_results_per_source": 7})
    result = passive_tools.osint(ctx)
    assert result["status"] == "completed" and len(requests) == 1 and len(ctx.calls) == 1
    assert "count:7" in requests[0].url.params["q"]
    findings = [r for r in result["records"] if r["category"] == "findings"]
    assert len(findings) == 1 and findings[0]["status"] == "review" and findings[0]["knowledge"] == "candidate"
    assert "DUMMY_SNIPPET_SECRET" not in ctx.saved() and "lineMatches" not in ctx.saved()
    assert result["assets"] == []
    import sqlite3
    with sqlite3.connect(tmp_path / "data/account-rate-ledger.sqlite") as connection:
        assert connection.execute("SELECT source,used FROM sources").fetchall() == [("sourcegraph:public", 1)]


def test_sourcegraph_result_limit_marks_truncation_instead_of_complete(tmp_path, monkeypatch):
    requests = mock_sourcegraph(monkeypatch, lambda request: httpx.Response(200, text=sourcegraph_fixture(count=3)))
    ctx = Context(tmp_path, "osint", "sourcegraph_stream", params={"max_results_per_source": 1})
    result = passive_tools.osint(ctx)
    assert len(requests) == 1 and result["status"] == "partial"
    assert sum(r["category"] == "findings" for r in result["records"]) == 1
    assert next(r for r in result["records"] if r["category"] == "tool_health")["truncated"]


def test_sourcegraph_error_does_not_hide_selected_tender_fallback(tmp_path, monkeypatch):
    requests = mock_sourcegraph(monkeypatch, lambda request: httpx.Response(429, text="DUMMY_FAILURE_SECRET"))
    tender = write(tmp_path, "tender.txt", "项目名称：Fixture System\n供应商：Fixture Vendor\n部署地址：https://portal.example.invalid\n")
    ctx = Context(tmp_path, "osint", "stage_p1", params={"sources": ["sourcegraph", "tender_files"], "tender_files": [tender]})
    result = passive_tools.osint(ctx)
    assert result["status"] == "partial" and len(requests) == 1
    assert [r["status"] for r in ctx.calls] == ["failed", "completed"]
    assert [a["domain"] for a in result["assets"]] == ["portal.example.invalid"]
    assert "DUMMY_FAILURE_SECRET" not in ctx.saved()
    assert any(r["category"] == "tool_health" and r["status"] == "failed" for r in result["records"])


def test_sourcegraph_out_of_scope_keyword_is_denied_before_request_or_ledger(tmp_path, monkeypatch):
    requests = mock_sourcegraph(monkeypatch, lambda request: httpx.Response(200, text=sourcegraph_fixture()))
    ctx = Context(tmp_path, "osint", "sourcegraph_stream", params={"keywords": ["supplier.invalid"]})
    with pytest.raises(PolicyDenied, match="outside_function_scope"):
        passive_tools.osint(ctx)
    assert requests == [] and ctx.calls == [] and not (tmp_path / "data/account-rate-ledger.sqlite").exists()


def test_sourcegraph_uses_current_function_typed_scope_for_brand_keyword(tmp_path, monkeypatch):
    requests = mock_sourcegraph(monkeypatch, lambda request: httpx.Response(200, text=sourcegraph_fixture()))
    ctx = Context(tmp_path, "osint", "sourcegraph_stream", target="FixtureBrand", params={"keywords": ["FixtureBrand"]})
    ctx.run["config"]["scope_sets"]["osint_only"] = {"include": [], "brands": ["FixtureBrand"]}
    ctx.run["config"]["permissions"]["osint"]["scope_ref"] = "osint_only"
    result = passive_tools.osint(ctx)
    assert result["status"] == "completed" and len(requests) == 1
    assert all(kind == "brand" for _, _, kind in ctx.permissions)


def test_selected_osint_import_tool_cannot_switch_to_network_source(tmp_path):
    ctx = Context(tmp_path, "osint", "osint_evidence_import", params={"sources": ["sourcegraph"]})
    with pytest.raises(ValueError, match="selected tool"):
        passive_tools.osint(ctx)
    assert ctx.calls == []


def test_osint_saved_sse_and_tender_collect_candidates_without_transport(tmp_path):
    sse = write(tmp_path, "inputs/source.sse", sourcegraph_fixture())
    tender = write(tmp_path, "inputs/tender.txt", "项目名称：Fixture Asset System\n供应商：Fixture Vendor\n部署地址：https://portal.example.invalid\nIP：192.0.2.10\n招标编号：UNIT-1\n")
    ctx = Context(tmp_path, "osint", "osint_evidence_import", params={"sse_files": [sse], "tender_files": [tender]})
    result = passive_tools.osint(ctx)
    assert result["status"] == "completed" and len(ctx.calls) == 2
    assert {a["domain"] or a["ip"] for a in result["assets"]} == {"portal.example.invalid", "192.0.2.10"}
    assert all(a["verification_status"] == "candidate_only" for a in result["assets"])
    assert "DUMMY_SNIPPET_SECRET" not in ctx.saved() and all(not network for _, network, _ in ctx.permissions)


def test_selected_but_missing_osint_source_is_reported_partial(tmp_path):
    sse = write(tmp_path, "input.sse", sourcegraph_fixture())
    ctx = Context(tmp_path, "osint", "osint_evidence_import", params={"sse_files": [sse]})
    result = passive_tools.osint(ctx)
    assert result["status"] == "partial"
    assert any(r["category"] == "tool_health" and r["source"] == "tender_files" and r["status"] == "blocked" for r in result["records"])


def test_pause_during_sourcegraph_stream_preserves_interrupted_call(tmp_path, monkeypatch):
    requests = mock_sourcegraph(monkeypatch, lambda request: httpx.Response(200, text=sourcegraph_fixture()))
    ctx = Context(tmp_path, "osint", "sourcegraph_stream")
    ctx.control_after = 5
    with pytest.raises(RunControlled):
        passive_tools.osint(ctx)
    assert len(requests) == 1 and ctx.calls[-1]["status"] == "interrupted"


def add_record(ctx, key, row):
    with ctx.workbench.store.connection() as connection:
        connection.execute("INSERT INTO records VALUES(?,?,?,?)", (key, ctx.run["run_id"], row["category"], json.dumps(row)))


def test_supply_certificates_organizations_neighbors_are_inferences_with_bounded_scope(tmp_path):
    ctx = Context(tmp_path, "passive_supply_chain", "stage_p2", params={"certificate_domain_limit": 2, "neighbor_ip_limit": 2,
        "vendor_list": ["Operator Supplier"]})
    add_record(ctx, "cert", {"category": "tls_observations", "certificate": {"subjectAltName": [
        ["DNS", "portal.example.invalid"], ["DNS", "*.supplier.invalid"], ["DNS", "third.invalid"]]}, "evidence_ids": ["prior-cert"]})
    add_record(ctx, "org", {"category": "organizations_relationships", "organization": "Fixture Parent", "related_organization": "Fixture Subsidiary",
        "relationship": "equity_control_candidate", "domains": ["subsidiary.invalid"], "evidence_ids": ["prior-org"]})
    ctx.current_assets = [{"asset_id": "prior-ip", "ip": "192.0.2.10", "evidence_ids": ["prior-ip-evidence"]}]
    result = passive_tools.passive_supply_chain(ctx)
    names = {a["name"] for a in result["assets"]}
    assert names == {"portal.example.invalid", "supplier.invalid", "subsidiary.invalid", "192.0.2.11", "192.0.2.12"}
    assert all(a["knowledge"] == "inference" and a["verification_status"] == "candidate_only" and a["confidence"] == "D" for a in result["assets"])
    assert all("captured-1" in a["evidence_ids"] for a in result["assets"])
    outside = [r for r in result["records"] if r["category"] == "out_of_scope_leads"]
    assert {r["name"] for r in outside} == names - {"portal.example.invalid"}
    assert all(not network for _, network, _ in ctx.permissions)
    assert not (tmp_path / "data/account-rate-ledger.sqlite").exists()


def test_supply_dimension_selection_and_ipv6_neighbor_family_are_preserved(tmp_path):
    ctx = Context(tmp_path, "passive_supply_chain", "saved_supply_analysis", params={"dimensions": ["neighbor_ips"], "neighbor_ip_limit": 2})
    add_record(ctx, "cert", {"category": "certificates", "sans": ["supplier.invalid"], "evidence_ids": []})
    ctx.current_assets = [{"asset_id": "v6", "ip": "::1", "evidence_ids": []}]
    result = passive_tools.passive_supply_chain(ctx)
    assert {a["ip"] for a in result["assets"]} == {"::2", "::3"}
    assert all(not a["domain"] for a in result["assets"])


def test_supply_inference_cannot_expand_scope_and_unsupported_tools_do_not_fallback(tmp_path):
    ctx = Context(tmp_path, "passive_supply_chain", "stage_p2", params={"inferred_scope_auto_add": True})
    with pytest.raises(ValueError, match="expand scope"):
        passive_tools.passive_supply_chain(ctx)
    unknown = Context(tmp_path, "company_lookup", "invented_provider", target="Fixture Parent")
    assert passive_tools.company_lookup(unknown)["status"] == "blocked" and unknown.calls == []


def test_company_profile_fields_reuse_parser_without_contact_or_target_requests(tmp_path):
    name = write(tmp_path, "profile.txt", "公司名称：Fixture Parent\n注册资本：100万\n法人：Example Person\n邮箱：DUMMY_CONTACT@fixture.invalid\n")
    ctx = Context(tmp_path, "company_lookup", "company_evidence_import", target="Fixture Parent", params={"company_profile_files": [name]})
    result = passive_tools.company_lookup(ctx)
    profile = next(r["profile"] for r in result["records"] if r["category"] == "organizations_relationships")
    assert profile["company"] == "Fixture Parent" and profile["capital"] == "100万"
    assert "email" not in profile and "DUMMY_CONTACT" not in ctx.saved()


def test_adapters_cover_three_capabilities():
    assert set(passive_tools.adapters()) == {"company_lookup", "osint", "passive_supply_chain"}


@pytest.mark.parametrize("subject", ["Fixture Parent", "ExampleCo", "虚构样例公司"])
def test_company_exports_run_through_real_workbench_trace_reports_scope_and_resume(tmp_path, project, subject):
    (tmp_path / "profiles").mkdir()
    shutil.copy(project / "profiles/modes.yaml", tmp_path / "profiles/modes.yaml")
    exported = equity_rows()
    exported[0]["name"] = subject
    exported[0]["domains"] = ["example.invalid", "https://example.invalid"]
    filename = write(tmp_path, "inputs/equity.json", exported)
    config = {"schema_version": 2, "profile": "company_unit", "mode_preset": "passive_discovery", "authorization": False,
        "execution": {"source": "live"}, "targets": {"company": subject, "roots": []},
        "scope_sets": {"investigation": {"include": ["example.invalid"], "subjects": [subject]}},
        "permissions": {"company_lookup": {"allow": True, "scope_ref": "investigation"}},
        "plan": {"selection": "custom", "selected_capabilities": ["company_lookup"], "selected_tools": ["stage_2a"],
                 "params": {"company_lookup": {"equity_files": [filename]}}}}
    wb = Workbench(tmp_path, adapters=passive_tools.adapters(), recover=False)
    wb.save_project(config)
    run = wb.start(config["profile"], background=False)
    assert run["status"] == "completed" and len(run["assets"]) == 3
    assert all(a["scope_status"] == "in_scope" and a["verification_status"] == "candidate_only" for a in run["assets"])
    assert run["snapshot"]["status"] == "complete" and run["snapshot"]["main_asset_count"] == 3
    traces = [event for event in wb.store.events(run["run_id"]) if event["kind"] == "tool_call"]
    assert len(traces) == 1 and traces[0]["data"]["tool"] == "stage_2a"
    assert sum(event["kind"] == "asset_found" for event in wb.store.events(run["run_id"])) == 3
    first_id = run["snapshot"]["snapshot_id"]
    resumed = Workbench(tmp_path, adapters=passive_tools.adapters(), recover=False).resume(run["run_id"], background=False)
    assert len([event for event in wb.store.events(run["run_id"]) if event["kind"] == "tool_call"]) == 1
    assert resumed["run_id"] == run["run_id"] and resumed["snapshot"]["snapshot_id"] != first_id
