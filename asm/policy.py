"""Configuration expansion and per-action authorization for the Workbench.

This module never resolves a name, reads credentials or performs a request.
An execution plan is a selection, not authorization. Runtime checks always use
the latest explicitly submitted permission/scope revision when supplied.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .scope import Scope, ScopeError, is_local, normalize_host


PASSIVE = frozenset({"search", "company_lookup", "passive_subdomains", "osint", "passive_supply_chain"})
CAPABILITIES = PASSIVE | frozenset({
    "dns_recursive", "tcp_scan", "service_probe", "web_visit", "tls_inspect", "screenshot",
    "dns_enum", "udp_scan", "deep_service_probe", "web_crawl", "js_analysis", "web_path_enum",
    "exposure_check", "vulnerability_check", "takeover_probe", "auth_audit",
})
INTERNAL_STEPS = ("evidence_normalize", "ownership_review", "coverage_summary", "dual_reports")
SECRET_KEY = re.compile(r"(?:^|_)(?:api_?key|secret|password|passwd|credential|token|access_key|private_key)(?:$|_)", re.I)


class PolicyDenied(ScopeError):
    """An action was rejected before any transport or tool launch."""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    capability: str
    target: str
    scope_ref: str = ""
    permission_version: str = ""

    def __bool__(self):
        return self.allowed


def merge(base, overlay):
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _secret_key(key):
    key = str(key).replace("-", "_")
    return bool(SECRET_KEY.search(key)) or key.casefold() in {
        "key", "fofa_key", "fofa_email", "authorization_header", "cookie", "cookies",
    }


def _reject_secrets(value, prefix="configuration"):
    if isinstance(value, dict):
        for key, child in value.items():
            if _secret_key(key) or (str(key).casefold() in {"authorization", "proxy-authorization"} and isinstance(child, str)):
                raise ValueError(f"Secrets must be configured in backend credential storage, not {prefix}")
            _reject_secrets(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for child in value:
            _reject_secrets(child, prefix)
    elif isinstance(value, str) and value.startswith(("http://", "https://")):
        parsed = urlsplit(value)
        if parsed.username or parsed.password or any(_secret_key(k) for k, _ in parse_qsl(parsed.query)):
            raise ValueError("Credential-bearing URLs are not accepted in project configuration")


def redacted_snapshot(value):
    """Defense in depth for exports, including legacy caller-created Configs."""
    if isinstance(value, dict):
        return {k: "[REDACTED]" if _secret_key(k) or (str(k).casefold() in {"authorization", "proxy-authorization"} and isinstance(v, str))
                else redacted_snapshot(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redacted_snapshot(v) for v in value]
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        parsed = urlsplit(value)
        if parsed.username or parsed.password or any(_secret_key(k) for k, _ in parse_qsl(parsed.query)):
            return "[REDACTED URL]"
    return deepcopy(value)


def configuration_hash(value):
    return hashlib.sha256(json.dumps(redacted_snapshot(value), sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def permission_hash(value):
    return configuration_hash({k: value.get(k) for k in
                               ("authorization", "authorization_details", "permissions", "scope_sets")})


def _mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _strings(value, name):
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise ValueError(f"{name} must be a list of strings")
    return value


def _capabilities(values, name):
    values = _strings(values, name)
    if set(values) - CAPABILITIES:
        raise ValueError(f"Unknown capability in {name}")
    return list(dict.fromkeys(values))


def _expand_inheritance(items, name, kind, visiting=()):
    if not isinstance(name, str) or name not in items:
        raise ValueError(f"Unknown {kind}: {name}")
    if name in visiting:
        raise ValueError(f"Cyclic {kind} inheritance")
    item = _mapping(items[name], kind)
    base = _expand_inheritance(items, item["extends"], kind, (*visiting, name)) if item.get("extends") else {}
    result = merge(base, {k: v for k, v in item.items() if k != "extends"})
    field = "capabilities" if kind == "mode" else "steps"
    additional = "add_capabilities" if kind == "mode" else "add_steps"
    inherited = item.get(field, base.get(field, []))
    result[field] = _capabilities(list(inherited) + list(item.get(additional, [])), f"{kind}.{field}")
    if kind == "plan":
        result["optional_steps"] = _capabilities(result.get("optional_steps", []), "plan.optional_steps")
    result.pop(additional, None)
    return result


class ScopeSet:
    """Exact typed subject/brand/query matching and explicit host/network matching."""

    def __init__(self, data):
        data = _mapping(data, "scope_set")
        self.domain_match = data.get("domain_match", "subdomains")
        if self.domain_match not in {"exact", "subdomains"}:
            raise ValueError("domain_match must be exact or subdomains")
        self.domains, self.networks = self._hosts(data.get("include", []), "scope.include")
        self.excluded_domains, self.excluded_networks = self._hosts(data.get("exclude", []), "scope.exclude")
        self.words = {key: {self._word(v) for v in _strings(data.get(key, []), f"scope.{key}")}
                      for key in ("subjects", "brands", "queries")}
        self.excluded_words = {self._word(v) for v in _strings(data.get("exclude_queries", []), "scope.exclude_queries")}

    @staticmethod
    def _word(value):
        return " ".join(value.strip().casefold().split())

    @staticmethod
    def _hosts(values, name):
        domains, networks = [], []
        for value in _strings(values, name):
            if "://" in value:
                raise ValueError("Scope entries must be bare hosts or IP/CIDR ranges")
            try:
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                if "/" in value:
                    raise ValueError("Invalid scope CIDR") from None
                wildcard = value.startswith("*.")
                host = normalize_host(value.removeprefix("*."))
                # Scope validates public suffix boundaries without a network lookup.
                Scope({"targets": {"roots": [host]}})
                domains.append((host, wildcard))
        return domains, networks

    def contains(self, target, target_kind="host"):
        if target_kind in {"subject", "brand", "query"}:
            key = {"subject": "subjects", "brand": "brands", "query": "queries"}[target_kind]
            word = self._word(str(target))
            return bool(word) and word in self.words[key] and word not in self.excluded_words
        if target_kind != "host":
            return False
        try:
            host = normalize_host(target)
            address = ipaddress.ip_address(host)
        except ValueError:
            try:
                host = normalize_host(target)
            except ValueError:
                return False
            address = None
        if address is not None:
            if any(address.version == net.version and address in net for net in self.excluded_networks):
                return False
            return any(address.version == net.version and address in net for net in self.networks)
        if any(host == root or host.endswith("." + root) for root, _ in self.excluded_domains):
            return False
        return any((host.endswith("." + root) if wildcard else
                    host == root or (self.domain_match == "subdomains" and host.endswith("." + root)))
                   for root, wildcard in self.domains)


def _validate_params(params):
    _mapping(params, "plan.params")
    if set(params) - (CAPABILITIES | {"feedback"}):
        raise ValueError("Unknown capability in plan.params")
    positive = {"timeout_seconds", "host_timeout_seconds", "packets_per_second", "requests_per_second",
                "workers", "max_response_bytes", "max_redirects", "max_depth", "max_urls_per_host",
                "max_requests_per_host", "max_urls_total", "max_files_per_host", "max_bytes_per_file", "max_cname_hops",
                "max_candidates_per_root", "max_attempts_per_account", "max_pages_per_query", "max_rounds"}
    for capability, values in params.items():
        _mapping(values, f"params.{capability}")
        if "tool_options" in values:
            options = _mapping(values["tool_options"], f"params.{capability}.tool_options")
            for tool, overrides in options.items():
                _mapping(overrides, f"tool_options.{tool}")
                if "tool_options" in overrides:
                    raise ValueError("Nested tool_options are not supported")
                _validate_params({capability: overrides})
        for key, value in values.items():
            if key in positive and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
                raise ValueError(f"params.{capability}.{key} must be positive")
        if values.get("follow_out_of_scope") is True or values.get("inferred_scope_auto_add") is True:
            raise ValueError("Out-of-scope findings require manual scope addition")
        if values.get("claim_external_resource") is True:
            raise ValueError("Resource claiming is not a supported evidence check")
        if any(values.get(key) is False for key in ("recheck_redirect_scope", "recheck_each_request_scope")):
            raise ValueError("Request scope rechecks cannot be disabled")
        for key in ("approved_checks", "approved_probes", "approved_providers", "approved_script_categories"):
            if key in values:
                _strings(values[key], f"params.{capability}.{key}")
        if capability in {"tcp_scan", "udp_scan"} and "ports" in values:
            ports = values["ports"]
            if not isinstance(ports, str):
                raise ValueError("Scan ports must be an explicit comma/range string")
            for section in ports.split(",") if ports else []:
                bounds = section.split("-")
                if len(bounds) > 2 or any(not n.isdigit() or not 1 <= int(n) <= 65535 for n in bounds):
                    raise ValueError("Scan ports must be between 1 and 65535")
                if len(bounds) == 2 and int(bounds[0]) > int(bounds[1]):
                    raise ValueError("Invalid port range")


def effective_config(project, modes_path):
    """Expand schema 2; legacy configurations retain their original permissions."""
    project = deepcopy(_mapping(project, "Profile"))
    _reject_secrets(project)
    schema = project.get("schema_version", 1)
    if type(schema) is not int or schema not in {1, 2}:
        raise ValueError("Unsupported schema_version")
    if schema == 1:
        if any(key in project for key in ("mode_preset", "permissions", "scope_sets", "plan")):
            raise ValueError("New policy fields require schema_version: 2")
        source = _mapping(project.get("execution", {}), "execution").get("source", "live")
        if source not in {"live", "replay"}:
            raise ValueError("execution.source must be live or replay")
        return project
    modes = deepcopy(modes_path) if isinstance(modes_path, dict) else yaml.safe_load(Path(modes_path).read_text(encoding="utf-8"))
    modes = _mapping(modes, "modes")
    _reject_secrets(modes)
    catalog = _mapping(modes.get("capability_catalog"), "capability_catalog")
    if set(catalog) != CAPABILITIES:
        raise ValueError("Capability catalog does not match supported policy capabilities")
    mode_name = project.get("mode_preset")
    preset = _expand_inheritance(_mapping(modes.get("presets"), "presets"), mode_name, "mode")
    plan_template = _expand_inheritance(_mapping(modes.get("plans"), "plans"), preset["default_plan"], "plan")
    defaults = _mapping(modes.get("defaults", {}), "defaults")
    params = merge(defaults.get("params", {}), preset.get("default_params", {}))
    plan = _mapping(project.get("plan", {}), "plan")
    # Existing project parameters remain project overrides during migration.
    legacy_params = {}
    ports = _mapping(project.get("ports", {}), "ports")
    for capability, field in (("tcp_scan", "tcp"), ("udp_scan", "udp")):
        if field in ports:
            legacy_params.setdefault(capability, {})["ports"] = ports[field]
        if "engine" in ports:
            legacy_params.setdefault(capability, {})["engine"] = ports["engine"]
    web = _mapping(project.get("web", {}), "web")
    legacy_params["web_visit"] = {k: v for k, v in web.items() if k in {"urls", "max_response_bytes"}}
    limits = _mapping(project.get("limits", {}), "limits")
    if "http_timeout" in limits:
        legacy_params["web_visit"]["timeout_seconds"] = limits["http_timeout"]
    dns = _mapping(project.get("dns", {}), "dns")
    dns_keys = {"resolvers": "resolvers", "timeout": "timeout_seconds", "workers": "workers",
                "max_cname_hops": "max_cname_hops", "reject_fake_ip": "reject_fake_ip",
                "doh_resolvers": "doh_resolvers", "doh_trusted": "doh_trusted"}
    legacy_params["dns_recursive"] = {to: dns[key] for key, to in dns_keys.items() if key in dns}
    params = merge(params, legacy_params)
    params = merge(params, plan.get("params", {}))
    _validate_params(params)
    selection = plan.get("selection", "auto")
    if selection not in {"auto", "custom"}:
        raise ValueError("plan.selection must be auto or custom")
    tools = merge(defaults.get("tools", {}), project.get("tools", {}))
    if set(tools) - CAPABILITIES:
        raise ValueError("Unknown capability in tools")
    known_tools = {tool for entry in catalog.values() for tool in entry.get("adapter_candidates", [])}
    if any(not isinstance(tool, str) or tool not in known_tools for tool in tools.values()):
        raise ValueError("Unknown tool selection")
    selected_tools = _strings(plan.get("selected_tools", []), "plan.selected_tools")
    if set(selected_tools) - known_tools:
        raise ValueError("Unknown tool in plan.selected_tools")
    selected = _capabilities(plan.get("selected_capabilities", []), "plan.selected_capabilities")
    if set(selected) - set(preset["capabilities"]):
        raise ValueError("Selected capability is not supported by this mode")
    if selection == "custom":
        if not selected:
            selected = [c for c in plan_template["steps"] if
                        set(catalog[c].get("adapter_candidates", [])) & set(selected_tools)]
        if not selected:
            raise ValueError("Custom plan requires selected capabilities or tools")
        steps = selected
    else:
        steps = list(plan_template["steps"])
        for optional in plan_template.get("optional_steps", []):
            if optional in selected:
                steps.append(optional)
    if selected_tools:
        steps = [c for c in steps if set(catalog[c].get("adapter_candidates", [])) & set(selected_tools)]
    tool_lists = {}
    for capability in steps:
        candidates = catalog[capability].get("adapter_candidates", [])
        if selected_tools:
            candidates = [v for v in candidates if v in selected_tools]
        explicit_tool = project.get("tools", {}).get(capability)
        explicit_engine = plan.get("params", {}).get(capability, {}).get("engine") or legacy_params.get(capability, {}).get("engine")
        if explicit_tool and explicit_engine and explicit_tool != explicit_engine:
            raise ValueError("Tool choice conflicts with explicit engine parameter")
        if capability in {"search", "passive_subdomains"}:
            key = "engines" if capability == "search" else "sources"
            requested = [explicit_tool or explicit_engine] if explicit_tool or explicit_engine else params.get(capability, {}).get(key, candidates)
            requested = _strings(requested, f"params.{capability}.{key}")
            if set(requested) - set(catalog[capability].get("adapter_candidates", [])):
                raise ValueError("Unknown source tool for selected capability")
            chosen = [value for value in dict.fromkeys(requested) if value in candidates]
            if not chosen:
                raise ValueError("Selected capability has no selected source tool")
            tool_lists[capability] = chosen
            tools[capability] = chosen[0]
            continue
        if selected_tools and not (explicit_tool or explicit_engine):
            # Each selected tool owns its own step, receipt and evidence. A
            # single capability must not silently discard additional choices.
            tool_lists[capability] = list(dict.fromkeys(candidates))
            tools[capability] = candidates[0] if candidates else None
            continue
        preferred = explicit_tool or explicit_engine or tools.get(capability) or params.get(capability, {}).get("engine")
        if (explicit_tool or explicit_engine) and preferred not in candidates:
            raise ValueError("Explicit tool is not selected or does not support this capability")
        tools[capability] = preferred if preferred in candidates else (candidates[0] if candidates else None)
        tool_lists[capability] = [tools[capability]] if tools[capability] else []
        if "engine" in params.get(capability, {}):
            params[capability]["engine"] = tools[capability]
    scopes = _mapping(project.get("scope_sets", {}), "scope_sets")
    for name, scope in scopes.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name):
            raise ValueError("Invalid scope set name")
        ScopeSet(scope)
    permissions = _mapping(project.get("permissions", {}), "permissions")
    if set(permissions) - CAPABILITIES:
        raise ValueError("Unknown capability in permissions")
    for name, permission in permissions.items():
        _mapping(permission, f"permissions.{name}")
        if type(permission.get("allow")) is not bool:
            raise ValueError("permissions.allow must be a YAML boolean")
        if permission.get("scope_ref") not in scopes:
            raise ValueError(f"Unknown scope_ref in permissions.{name}")
    execution = merge({"source": "live", "target_local": False}, project.get("execution", {}))
    if execution["source"] not in {"live", "replay"} or type(execution["target_local"]) is not bool:
        raise ValueError("Invalid execution source or target_local flag")
    if type(project.get("authorization", False)) is not bool:
        raise ValueError("authorization must be a YAML boolean")
    authorization_details = _mapping(project.get("authorization_details", {}), "authorization_details")
    window = _mapping(authorization_details.get("window", {}), "authorization_details.window")
    for key in ("start", "end"):
        if window.get(key):
            _timestamp(window[key], window.get("timezone", "UTC"))
    if window.get("start") and window.get("end") and _timestamp(window["start"], window.get("timezone", "UTC")) >= _timestamp(window["end"], window.get("timezone", "UTC")):
        raise ValueError("Authorization window end must follow start")
    budgets = merge(defaults.get("budgets", {}), project.get("budgets", {}))
    for key, value in budgets.items():
        if key.startswith("max_") and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
            raise ValueError(f"budgets.{key} must be positive")
    reports = merge(modes.get("reports", {}), project.get("reports", {}))
    if set(reports.get("variants", [])) != {"professional", "user_custom"} or set(reports.get("formats", [])) != {"csv", "html", "md"}:
        raise ValueError("Both report variants and CSV/HTML/Markdown formats are mandatory")
    if reports.get("snapshot_policy") != "immutable":
        raise ValueError("Report snapshots must be immutable")
    result = merge(project, {"mode_capabilities": preset["capabilities"], "mode_version": str(modes.get("version", "")),
                            "capability_catalog": catalog, "execution": execution, "tools": tools, "tool_lists": tool_lists, "budgets": budgets,
                            "reports": reports, "plan": merge(plan, {"selection": selection, "steps": steps,
                            "selected_tools": selected_tools, "params": params, "internal_steps": list(INTERNAL_STEPS)})})
    result["permission_version"] = str(project.get("permission_version") or permission_hash(result))
    # Project plan parameters also drive legacy tools during incremental migration.
    if "tcp_scan" in params:
        result.setdefault("ports", {})["tcp"] = params["tcp_scan"].get("ports", result.get("ports", {}).get("tcp", ""))
        result["ports"]["engine"] = tools.get("tcp_scan", result["ports"].get("engine", "nmap"))
    if "udp_scan" in params:
        result.setdefault("ports", {})["udp"] = params["udp_scan"].get("ports", result.get("ports", {}).get("udp", ""))
    visit = params.get("web_visit", {})
    result.setdefault("web", {}).update({k: v for k, v in visit.items() if k in {"urls", "max_response_bytes"}})
    result.setdefault("limits", {})["http_timeout"] = visit.get("timeout_seconds", 15)
    recursive = params.get("dns_recursive", {})
    result.setdefault("dns", {}).update({key: recursive[value] for key, value in dns_keys.items()
                                        if value in recursive})
    # Changing resolver overrides must also choose a valid preferred resolver.
    if result["dns"].get("preferred_resolver") not in result["dns"].get("resolvers", []):
        result["dns"]["preferred_resolver"] = result["dns"].get("resolvers", ["114.114.114.114"])[0]
    result["effective_config_hash"] = configuration_hash(result)
    return result


def _timestamp(value, zone):
    if not isinstance(value, str):
        raise ValueError("Authorization timestamps must be ISO 8601 strings")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            try:
                tz = ZoneInfo(zone)
            except ZoneInfoNotFoundError:
                if zone != "Asia/Shanghai":
                    raise ValueError("Unknown authorization timezone") from None
                tz = timezone(timedelta(hours=8))
            timestamp = timestamp.replace(tzinfo=tz)
        return timestamp.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid authorization timestamp or timezone") from exc


class ExecutionPolicy:
    """A stable run plan plus dynamic submitted authorization/scope revision."""

    def __init__(self, config, *, current_config=None, passive_only=False, target_local=False):
        self.config = config.data if hasattr(config, "data") else config
        self.current_config = current_config
        self.passive_only = passive_only
        self.target_local = target_local or self.config.get("execution", {}).get("target_local", False)

    def _current(self):
        value = self.current_config() if self.current_config else self.config
        return value.data if hasattr(value, "data") else value

    def selected(self, capability):
        if self.config.get("schema_version", 1) == 1:
            return capability in CAPABILITIES
        return capability in self.config.get("plan", {}).get("steps", [])

    def params(self, capability, tool=None):
        params = deepcopy(self.config.get("plan", {}).get("params", {}).get(capability, {}))
        options = params.pop("tool_options", {})
        if tool and isinstance(options, dict):
            params = merge(params, options.get(tool, {}))
        return params

    def tool_for(self, capability):
        return self.config.get("tools", {}).get(capability)

    def tools_for(self, capability):
        return list(self.config.get("tool_lists", {}).get(capability) or [self.tool_for(capability)])

    def contains(self, scope_ref, target, target_kind="host"):
        current = self._current()
        if current.get("schema_version", 1) == 1:
            return target_kind == "host" and Scope(current, target_local=self.target_local).contains(target)
        scope = current.get("scope_sets", {}).get(scope_ref)
        return bool(scope is not None and ScopeSet(scope).contains(target, target_kind))

    def check(self, capability, target, *, target_kind="host", tool=None, network=True,
              now=None, budget_available=True, adapter_available=True):
        current = self._current()
        permission = current.get("permissions", {}).get(capability, {})
        scope_ref = permission.get("scope_ref", "")
        version = str(current.get("permission_version") or permission_hash(current))

        def decision(allowed, reason):
            return Decision(allowed, reason, capability, str(target), scope_ref, version)

        if capability not in CAPABILITIES:
            return decision(False, "unknown_capability")
        if network and self.config.get("execution", {}).get("source", "live") == "replay":
            return decision(False, "replay_network_forbidden")
        if not self.selected(capability):
            return decision(False, "not_selected")
        if not adapter_available:
            return decision(False, "adapter_unavailable")
        if not budget_available:
            return decision(False, "budget_exhausted")
        active = capability not in PASSIVE
        if self.config.get("schema_version", 1) == 1:
            if target_kind != "host":
                return decision(False, "legacy_typed_scope_unavailable")
            try:
                Scope(current, passive_only=self.passive_only, target_local=self.target_local).assert_in_scope(target, active=active)
            except ValueError:
                return decision(False, "legacy_scope_or_authorization_denied")
            return decision(True, "legacy_approved_scope")
        if capability not in self.config.get("mode_capabilities", []):
            return decision(False, "mode_capability_denied")
        if permission.get("allow") is not True:
            return decision(False, "function_permission_denied")
        selected_tools = self.config.get("plan", {}).get("selected_tools", [])
        if tool is not None and (tool not in self.tools_for(capability) or (selected_tools and tool not in selected_tools)):
            return decision(False, "tool_not_selected")
        if active and target_kind != "host":
            return decision(False, "active_requires_host_scope")
        if active and (current.get("authorization") is not True or self.passive_only):
            return decision(False, "global_authorization_denied")
        if not self.contains(scope_ref, target, target_kind):
            return decision(False, "outside_function_scope")
        if target_kind == "host" and self.target_local and not is_local(target):
            return decision(False, "target_local_only")
        if active:
            details = current.get("authorization_details", {})
            window = details.get("window", {})
            external = not is_local(target)
            if external and (not details.get("authority") or not details.get("reference") or
                             not window.get("start") or not window.get("end")):
                return decision(False, "external_authorization_metadata_required")
            instant = now or datetime.now(timezone.utc)
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=timezone.utc)
            try:
                if window.get("start") and instant < _timestamp(window["start"], window.get("timezone", "UTC")):
                    return decision(False, "authorization_not_started")
                if window.get("end") and instant >= _timestamp(window["end"], window.get("timezone", "UTC")):
                    return decision(False, "authorization_expired")
            except ValueError:
                return decision(False, "invalid_authorization_window")
        return decision(True, "approved")

    def require(self, capability, target, **kwargs):
        decision = self.check(capability, target, **kwargs)
        if not decision.allowed:
            raise PolicyDenied(f"{capability}: {decision.reason}")
        return decision
