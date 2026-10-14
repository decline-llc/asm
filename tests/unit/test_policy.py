"""No-network policy tests: selection, typed scope, revisions and snapshots."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from asm.conf import load_config
from asm.policy import (ExecutionPolicy, PolicyDenied, ScopeSet, configuration_hash,
                        effective_config, permission_hash, redacted_snapshot)


ROOT = Path(__file__).resolve().parents[2]
MODES = ROOT / "profiles" / "modes.yaml"


def project(**changes):
    value = {
        "schema_version": 2, "profile": "policy_test", "mode_preset": "full_asm", "authorization": True,
        "execution": {"source": "live", "target_local": False},
        "scope_sets": {
            "investigation": {"include": ["example.invalid"], "subjects": ["Example Organization"],
                              "brands": ["ExampleBrand"], "queries": ["Approved Query"], "exclude": []},
            "verification": {"include": ["localhost", "127.0.0.1/32", "::1/128"], "domain_match": "exact"},
        },
        "permissions": {"web_visit": {"allow": True, "scope_ref": "verification"},
                        "screenshot": {"allow": True, "scope_ref": "verification"},
                        "company_lookup": {"allow": True, "scope_ref": "investigation"},
                        "osint": {"allow": True, "scope_ref": "investigation"}},
        "plan": {"selection": "custom", "selected_capabilities": ["web_visit", "screenshot", "company_lookup", "osint"]},
    }
    value.update(changes)
    return value


def resolve(value=None):
    return effective_config(value or project(), MODES)


def test_three_modes_inherit_catalog_and_parameters():
    full = resolve(project(plan={"selection": "auto"}))
    assert {"tcp_scan", "udp_scan", "service_probe", "web_visit", "tls_inspect", "screenshot"} <= set(full["plan"]["steps"])
    assert "auth_audit" in full["mode_capabilities"] and "auth_audit" not in full["plan"]["steps"]
    assert full["plan"]["params"]["tcp_scan"]["ports"] == "1-65535"
    assert full["plan"]["params"]["web_visit"]["max_response_bytes"] == 65536
    verify = resolve(project(mode_preset="authorized_verify", plan={"selection": "auto"}))
    assert "tcp_scan" in verify["plan"]["steps"] and "udp_scan" not in verify["plan"]["steps"]
    passive = resolve(project(mode_preset="passive_discovery", plan={"selection": "auto"}))
    assert "web_visit" not in passive["plan"]["steps"]


def test_modes_mapping_supported_and_final_hash_matches_load_config(monkeypatch, tmp_path):
    modes = yaml.safe_load(MODES.read_text(encoding="utf-8"))
    assert effective_config(project(), modes)["plan"]["steps"] == resolve()["plan"]["steps"]
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles/modes.yaml").write_text(yaml.safe_dump(modes), encoding="utf-8")
    (tmp_path / "profiles/custom.yaml").write_text(yaml.safe_dump(project()), encoding="utf-8")
    config = load_config("custom", tmp_path, load_secrets=False)
    value = {k: v for k, v in config.data.items() if k != "effective_config_hash"}
    assert config.data["effective_config_hash"] == configuration_hash(value)


def test_merge_project_params_and_legacy_parameter_overrides():
    value = project(ports={"tcp": "1234"}, limits={"http_timeout": 7},
                    plan={"selection": "auto", "params": {"tcp_scan": {"packets_per_second": 25},
                                                          "web_visit": {"timeout_seconds": 2}}})
    data = resolve(value)
    assert data["plan"]["params"]["tcp_scan"]["ports"] == "1234"
    assert data["plan"]["params"]["tcp_scan"]["packets_per_second"] == 25
    assert data["ports"]["tcp"] == "1234"
    assert data["limits"]["http_timeout"] == 2


def test_explicit_auth_step_requires_project_selection():
    data = resolve(project(plan={"selection": "auto", "selected_capabilities": ["auth_audit"]}))
    assert "auth_audit" in data["plan"]["steps"]


def test_tools_and_capabilities_intersect():
    data = resolve(project(plan={"selection": "custom", "selected_tools": ["target_http"]}))
    assert data["plan"]["steps"] == ["web_visit"]
    assert ExecutionPolicy(data).check("web_visit", "127.0.0.1", tool="target_http").allowed
    assert ExecutionPolicy(data).check("web_visit", "127.0.0.1", tool="playwright").reason == "tool_not_selected"


@pytest.mark.parametrize("change", [
    {"mode_preset": "typo"}, {"mode_preset": []}, {"schema_version": True},
    {"permissions": {"typo": {"allow": True, "scope_ref": "verification"}}},
    {"permissions": {"web_visit": {"allow": "true", "scope_ref": "verification"}}},
    {"permissions": {"web_visit": {"allow": True, "scope_ref": "missing"}}},
    {"plan": {"selection": "custom"}}, {"plan": {"selection": "unknown"}},
    {"plan": {"selection": "auto", "selected_tools": ["unknown"]}},
    {"plan": {"selection": "custom", "selected_capabilities": ["unknown"]}},
    {"plan": {"params": {"unknown": {}}}},
    {"plan": {"params": {"tcp_scan": {"ports": "0,65536"}}}},
    {"plan": {"params": {"tcp_scan": {"ports": "100-1"}}}},
    {"plan": {"params": {"web_visit": {"timeout_seconds": -1}}}},
    {"plan": {"params": {"web_crawl": {"follow_out_of_scope": True}}}},
    {"plan": {"params": {"screenshot": {"recheck_each_request_scope": False}}}},
    {"execution": {"source": "pretend"}},
    {"reports": {"variants": ["professional"]}},
    {"reports": {"formats": ["html"]}},
    {"reports": {"snapshot_policy": "overwrite"}},
    {"budgets": {"max_hosts": 0}},
])
def test_invalid_configuration_rejected_before_start(change):
    with pytest.raises(ValueError):
        resolve(project(**change))


def test_missing_permissions_do_not_inherit_from_mode_or_tools():
    data = resolve(project(permissions={}, plan={"selection": "auto"}))
    policy = ExecutionPolicy(data)
    assert policy.check("web_visit", "127.0.0.1").reason == "function_permission_denied"
    assert policy.check("unknown", "127.0.0.1").reason == "unknown_capability"


def test_function_scope_and_global_authorization_are_independent():
    policy = ExecutionPolicy(resolve())
    assert policy.check("web_visit", "http://127.0.0.1:8765").allowed
    assert policy.check("web_visit", "api.localhost").reason == "outside_function_scope"
    assert policy.check("web_visit", "example.invalid").reason == "outside_function_scope"
    assert policy.check("company_lookup", "Example Organization", target_kind="subject").allowed
    assert not policy.check("company_lookup", "Example Organization Holding", target_kind="subject").allowed
    policy = ExecutionPolicy(resolve(project(authorization=False)))
    assert policy.check("web_visit", "localhost").reason == "global_authorization_denied"
    assert policy.check("company_lookup", "Example Organization", target_kind="subject").allowed


def test_typed_subject_brand_query_scopes_match_exactly():
    scope = ScopeSet({"include": ["example.invalid"], "subjects": ["Example Organization"],
                      "brands": ["ExampleBrand"], "queries": ["Approved Query"]})
    assert scope.contains(" example  Organization ", "subject")
    assert scope.contains("examplebrand", "brand")
    assert scope.contains("Approved Query", "query")
    assert not scope.contains("Example Organization", "host")
    assert not scope.contains("Unknown Query", "query")


def test_domain_boundary_ip_cidr_ipv6_and_exclusions():
    scope = ScopeSet({"include": ["example.invalid", "127.0.0.0/24", "::1/128"],
                      "exclude": ["blocked.example.invalid", "127.0.0.4/32"]})
    assert scope.contains("api.example.invalid") and scope.contains("127.0.0.3") and scope.contains("http://[::1]:80")
    assert not scope.contains("evil-example.invalid") and not scope.contains("example.invalid.evil.invalid")
    assert not scope.contains("blocked.example.invalid") and not scope.contains("nested.blocked.example.invalid")
    assert not scope.contains("127.0.0.4") and not scope.contains("::2")
    exact = ScopeSet({"include": ["example.invalid"], "domain_match": "exact"})
    assert exact.contains("example.invalid") and not exact.contains("api.example.invalid")
    wildcard = ScopeSet({"include": ["*.example.invalid"], "domain_match": "exact"})
    assert wildcard.contains("a.example.invalid") and not wildcard.contains("example.invalid")


@pytest.mark.parametrize("value", [{"include": ["com"]}, {"include": ["co.uk"]},
                                    {"include": ["https://example.invalid"]}, {"include": ["127.0.0.1/99"]},
                                    {"include": ["Example Organization"]}, {"domain_match": "contains"}])
def test_invalid_scope_entries(value):
    with pytest.raises(ValueError):
        ScopeSet(value)


def external_project(window=None):
    value = project(authorization_details={"authority": "asset_owner", "reference": "approval_123",
                     "window": window or {"start": "2026-10-11T10:00:00+08:00", "end": "2026-10-11T11:00:00+08:00"}})
    value["scope_sets"]["verification"]["include"] = ["example.invalid"]
    return resolve(value)


def test_external_active_window_valid_before_and_after():
    policy = ExecutionPolicy(external_project())
    assert policy.check("web_visit", "example.invalid", now=datetime(2026, 10, 11, 2, 30, tzinfo=timezone.utc)).allowed
    assert policy.check("web_visit", "example.invalid", now=datetime(2026, 10, 11, 1, tzinfo=timezone.utc)).reason == "authorization_not_started"
    assert policy.check("web_visit", "example.invalid", now=datetime(2026, 10, 11, 3, tzinfo=timezone.utc)).reason == "authorization_expired"
    data = external_project()
    data["authorization_details"]["window"] = {}
    assert ExecutionPolicy(data).check("web_visit", "example.invalid").reason == "external_authorization_metadata_required"


def test_naive_window_uses_explicit_timezone():
    policy = ExecutionPolicy(external_project({"start": "2026-10-11T10:00:00", "end": "2026-10-11T11:00:00", "timezone": "Asia/Shanghai"}))
    assert policy.check("web_visit", "example.invalid", now=datetime(2026, 10, 11, 2, 30, tzinfo=timezone.utc)).allowed


def test_resume_keeps_plan_but_uses_revoked_current_permissions():
    original = resolve()
    current = deepcopy(original)
    policy = ExecutionPolicy(original, current_config=lambda: current)
    assert policy.require("web_visit", "localhost").allowed
    current["permissions"]["web_visit"]["allow"] = False
    current["permission_version"] = "revision_2"
    assert policy.check("web_visit", "localhost").permission_version == "revision_2"
    with pytest.raises(PolicyDenied):
        policy.require("web_visit", "localhost")
    current["permissions"]["web_visit"]["allow"] = True
    current["scope_sets"]["verification"]["include"] = []
    assert policy.check("web_visit", "localhost").reason == "outside_function_scope"
    current["plan"]["steps"].append("udp_scan")
    assert not policy.selected("udp_scan")


def test_runtime_checks_budget_adapter_and_local_constraint():
    policy = ExecutionPolicy(resolve())
    assert policy.check("web_visit", "localhost", budget_available=False).reason == "budget_exhausted"
    assert policy.check("web_visit", "localhost", adapter_available=False).reason == "adapter_unavailable"
    policy = ExecutionPolicy(external_project(), target_local=True)
    assert policy.check("web_visit", "example.invalid").reason == "target_local_only"


def test_investigation_addition_does_not_grant_active_scope():
    data = resolve()
    data["scope_sets"]["investigation"]["include"].append("new.example.invalid")
    policy = ExecutionPolicy(data)
    assert policy.contains("investigation", "new.example.invalid")
    assert policy.check("web_visit", "new.example.invalid").reason == "outside_function_scope"


def test_replay_denies_transport_but_can_process_evidence():
    policy = ExecutionPolicy(resolve(project(execution={"source": "replay"})))
    assert policy.check("web_visit", "localhost").reason == "replay_network_forbidden"
    assert policy.check("company_lookup", "Example Organization", target_kind="subject").reason == "replay_network_forbidden"
    assert policy.check("web_visit", "localhost", network=False).allowed


@pytest.mark.parametrize("secret", [{"api_key": "synthetic"}, {"search": {"fofa_key": "synthetic"}},
                                    {"plan": {"params": {"web_visit": {"headers": {"Authorization": "synthetic"}}}}},
                                    {"plan": {"params": {"web_visit": {"urls": ["http://user:pass@localhost"]}}}},
                                    {"web": {"urls": ["http://localhost/?access_token=synthetic"]}}])
def test_secret_fields_rejected_without_echo(secret):
    with pytest.raises(ValueError) as caught:
        resolve(project(**secret))
    assert "synthetic" not in str(caught.value) and "user:pass" not in str(caught.value)


def test_snapshot_redaction_and_stable_hashes():
    value = {"api_key": "synthetic", "urls": ["http://u:p@localhost"], "params": {"timeout": 3}}
    snapshot = redacted_snapshot(value)
    assert snapshot["api_key"] == "[REDACTED]" and snapshot["urls"] == ["[REDACTED URL]"]
    assert configuration_hash(value) == configuration_hash({**value, "api_key": "different"})
    data = resolve()
    assert permission_hash(data) != permission_hash({**data, "authorization": False})


def test_load_config_secret_opt_out_and_replay_opt_out(monkeypatch, tmp_path):
    monkeypatch.setattr("asm.conf.load_dotenv", lambda *_args, **_kwargs: pytest.fail("dotenv must not be read"))
    (tmp_path / "profiles").mkdir()
    basic = {"profile": "offline", "authorization": False}
    path = tmp_path / "profiles" / "offline.yaml"
    path.write_text(yaml.safe_dump(basic), encoding="utf-8")
    assert load_config("offline", tmp_path, load_secrets=False).name == "offline"
    basic["execution"] = {"source": "replay"}
    path.write_text(yaml.safe_dump(basic), encoding="utf-8")
    assert load_config("offline", tmp_path).name == "offline"


def test_legacy_config_preserves_scope_and_does_not_gain_full_policy():
    legacy = effective_config({"profile": "legacy", "authorization": True,
                               "targets": {"roots": ["localhost"]}}, MODES)
    assert "mode_capabilities" not in legacy and "permissions" not in legacy
    assert ExecutionPolicy(legacy).check("web_visit", "localhost").allowed
    with pytest.raises(ValueError):
        effective_config({**legacy, "permissions": {}}, MODES)
