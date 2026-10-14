"""One execution chain for CLI and UI, with durable action receipts and revocable policy."""
import copy
import ipaddress
import json
import re
import hashlib
import sqlite3
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from .conf import load_config
from .models import utcnow
from .policy import ExecutionPolicy, PolicyDenied
from .run_store import RunStore, atomic_json, digest, encode
from .run_lock import LeaseBusy
from .scope import normalize_host
from .project_catalog import project_purpose, profile_directory, PURPOSE_DIRECTORIES


class RunControlled(RuntimeError):
    pass


def parse_target(value):
    value = value.strip()
    if not value or len(value) > 253 or any(c in value for c in '\r\n\x00'):
        raise ValueError("Invalid target")
    try:
        network = ipaddress.ip_network(value, strict=False)
        return {"kind": "ip", "value": str(network.network_address) if network.num_addresses == 1 else str(network)}
    except ValueError:
        pass
    if "." in value or value == "localhost" or "://" in value:
        return {"kind": "domain", "value": normalize_host(value)}
    return {"kind": "subject", "value": value}


class Workbench:
    def __init__(self, root, *, adapters=None, recover=True, validation=False):
        self.root = Path(root).resolve()
        self.validation = validation
        state = self.root / "data" / ("validation" if validation else "") / "workbench.sqlite"
        self.store = RunStore(state)
        self.threads = {}
        self.lock = threading.RLock()
        self.adapters = adapters
        if recover:
            self.store.recover()
            # Restart creates an honest partial export before explicit user resume.
            for row in self.store.rows("SELECT id,status,snapshot FROM runs WHERE status IN ('interrupted','stopped')"):
                try:
                    saved = json.loads(row["snapshot"]) if row["snapshot"] else {}
                    if saved.get("run_status") == row["status"]:
                        continue
                    self.export(row["id"])
                except (OSError, ValueError, ImportError):
                    pass

    def project(self, project_id):
        rows = self.store.rows("SELECT * FROM projects WHERE id=?", (project_id,))
        if not rows:
            raise ValueError("Unknown project")
        row = rows[0]
        config = load_config(row["path"], root=self.root, load_secrets=False)
        return {"project_id": row["id"], "path": row["path"], "revision": row["revision"],
                "config": config.snapshot(), "updated_at": row["updated"],
                "purpose": project_purpose(config.data, row["id"], row["path"])}

    def projects(self, purpose="all"):
        if purpose != "all" and purpose not in PURPOSE_DIRECTORIES:
            raise ValueError("Unknown project purpose")
        result = []
        for row in self.store.rows("SELECT id,path FROM projects ORDER BY updated DESC"):
            try:
                project = self.project(row["id"])
                project["runs"] = self.store.rows("SELECT id,status,started,finished,directory,snapshot FROM runs WHERE project=? ORDER BY started DESC", (row["id"],))
                if purpose == "all" or project["purpose"] == purpose:
                    result.append(project)
            except (OSError, ValueError) as exc:
                category = project_purpose({}, row["id"], row["path"])
                if purpose == "all" or category == purpose:
                    result.append({"project_id": row["id"], "purpose": category,
                                   "status": "invalid_config", "reason": str(exc)})
        return result

    def import_project(self, profile):
        config = load_config(profile, root=self.root, load_secrets=False)
        with self.store.connection() as conn:
            row = conn.execute("SELECT revision FROM projects WHERE id=?", (config.name,)).fetchone()
            revision = row[0] if row else 1
            conn.execute("INSERT INTO projects VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path,data=excluded.data,updated=excluded.updated",
                         (config.name, str(config.path), revision, encode(config.snapshot()), utcnow()))
        return self.project(config.name)

    def save_project(self, data, *, project_id=None):
        with self.store.lock:
            return self._save_project_locked(data, project_id=project_id)

    def _save_project_locked(self, data, *, project_id=None):
        data = copy.deepcopy(data)
        project_id = project_id or data.get("profile") or "project_" + uuid.uuid4().hex[:12]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", project_id):
            raise ValueError("Invalid project identifier")
        data["profile"] = project_id
        if self.validation:
            data["project_purpose"] = "validation"
        purpose = project_purpose(data, project_id)
        path = profile_directory(self.root, purpose) / ("local-" + project_id + ".yaml")
        previous = self.store.rows("SELECT revision,path FROM projects WHERE id=?", (project_id,))
        if previous:
            path = Path(previous[0]["path"])
        # Validate in memory before replacing the project YAML; never store credentials.
        from .policy import effective_config
        effective = effective_config(data, self.root / "profiles/modes.yaml")
        revision = (previous[0]["revision"] + 1) if previous else 1
        data["permission_revision"] = revision
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        tmp.replace(path)
        with self.store.connection() as conn:
            conn.execute("INSERT INTO projects VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path,revision=excluded.revision,data=excluded.data,updated=excluded.updated",
                         (project_id, str(path), revision, encode(effective), utcnow()))
            for row in conn.execute("SELECT id FROM runs WHERE project=?", (project_id,)):
                self.store.event(row["id"], "policy_updated", {"revision": revision, "permission_version": digest(data.get("permissions", {}))}, conn)
        return self.project(project_id)

    def add_scope(self, project_id, value, *, scope_ref="investigation"):
        if scope_ref != "investigation":
            raise ValueError("Adding a lead changes investigation scope only; edit active permissions separately")
        project = self.project(project_id)
        data = yaml.safe_load(Path(project["path"]).read_text(encoding="utf-8"))
        target = parse_target(value)
        scope = data.setdefault("scope_sets", {}).setdefault("investigation", {})
        key = "subjects" if target["kind"] == "subject" else "include"
        scope[key] = sorted(set(scope.get(key, [])) | {target["value"]})
        result = self.save_project(data, project_id=project_id)
        for row in self.store.rows("SELECT id FROM runs WHERE project=? ORDER BY started DESC LIMIT 1", (project_id,)):
            self.store.event(row["id"], "scope_updated", {"scope_ref": scope_ref, "added": target, "revision": result["revision"], "actor": "local_user"})
            run = self.run(row["id"])
            self._enqueue_targets(run, [target["value"]], 1, passive_only=True)
            self.checkpoint(run["run_id"])
        return result

    def _policy(self, run):
        return ExecutionPolicy(run["config"], current_config=lambda: self.project(run["project_id"])["config"])

    def _targets(self, config, capability):
        roots = list(config.get("targets", {}).get("roots", []))
        ips = list(config.get("ports", {}).get("targets", []))
        for value in config.get("targets", {}).get("ip_cidrs", []):
            net = ipaddress.ip_network(value, strict=False)
            import itertools
            limit = int(config.get("budgets", {}).get("max_hosts", 1000))
            ips.extend(str(ip) for ip in itertools.islice(net.hosts(), limit))
        if capability in {"tcp_scan", "udp_scan", "service_probe", "deep_service_probe"}:
            return list(dict.fromkeys(ips))
        if capability in {"web_visit", "screenshot", "web_crawl", "js_analysis", "web_path_enum", "exposure_check", "vulnerability_check", "takeover_probe", "auth_audit", "tls_inspect"}:
            params = config.get("plan", {}).get("params", {})
            return params.get(capability, {}).get("urls") or params.get("web_visit", {}).get("urls") or config.get("web", {}).get("urls", []) or ["https://" + host for host in roots]
        if capability == "company_lookup":
            return config.get("scope_sets", {}).get("investigation", {}).get("subjects", []) or ([config["targets"]["company"]] if config.get("targets", {}).get("company") else [])
        if capability in {"search", "osint", "passive_supply_chain"}:
            return roots + ips + config.get("scope_sets", {}).get("investigation", {}).get("subjects", [])
        return roots

    def _enqueue(self, run, capability, target, round_number):
        policy = self._policy(run)
        tools = policy.tools_for(capability)
        if target == "__evidence_package__":
            tools = tools[:1]
        for tool in tools:
            self._enqueue_tool(run, capability, target, round_number, tool)

    def _enqueue_tool(self, run, capability, target, round_number, tool):
        policy = self._policy(run)
        params = policy.params(capability, tool)
        key = digest([run["run_id"], capability, target, tool])[:32]
        with self.store.connection() as conn:
            def host_key(value):
                try:
                    return normalize_host(value)
                except ValueError:
                    return value
            distinct = {host_key(r[0]) for r in conn.execute("SELECT DISTINCT target FROM steps WHERE run=? AND target!=''", (run["run_id"],))}
            if host_key(target) not in distinct and len(distinct) >= int(run["config"].get("budgets", {}).get("max_hosts", 1000)):
                self.store.event(run["run_id"], "coverage_gap", {"capability": capability, "target": target, "reason": "max_hosts_budget_exhausted"}, conn)
                return
            conn.execute("INSERT OR IGNORE INTO steps(id,run,capability,target,tool,params,round,status) VALUES(?,?,?,?,?,?,?,?)",
                         (key, run["run_id"], capability, target, tool or capability, encode(params), round_number, "pending"))

    def _enqueue_targets(self, run, targets, round_number, passive_only=False):
        config = run["config"]
        # A saved package already contains its historical feedback. Re-importing
        # the whole package for each discovered asset repeats events and coverage.
        if config["execution"]["source"] == "replay" and config["execution"].get("evidence_dir"):
            return
        policy = self._policy(run)
        passive = {"search", "passive_subdomains", "osint", "passive_supply_chain", "company_lookup"}
        max_rounds = int(config.get("budgets", {}).get("max_rounds", 3))
        if round_number > max_rounds:
            return
        for target in targets:
            try:
                host = normalize_host(target)
                kind = "host"
            except ValueError:
                host, kind = target, "subject"
            if not policy.contains("investigation", host, target_kind=kind):
                continue
            for cap in config["plan"]["steps"]:
                if passive_only and cap not in passive:
                    continue
                if cap in {"search", "osint", "passive_supply_chain"} or (cap == "passive_subdomains" and kind == "host" and "." in host):
                    self._enqueue(run, cap, host, round_number)
                elif not passive_only and cap not in passive and kind == "host":
                    active_target = host
                    try:
                        ipaddress.ip_address(host)
                        is_ip = True
                    except ValueError:
                        is_ip = False
                    if cap in {"tcp_scan", "udp_scan", "service_probe", "deep_service_probe"} and not is_ip:
                        continue
                    if cap in {"dns_recursive", "dns_enum"} and is_ip:
                        continue
                    if cap in {"web_visit", "tls_inspect", "screenshot", "web_crawl", "js_analysis", "web_path_enum", "exposure_check", "vulnerability_check", "takeover_probe", "auth_audit"}:
                        existing = self.store.rows("SELECT target FROM steps WHERE run=? AND capability=?", (run["run_id"], cap))
                        def same_endpoint(value):
                            if "://" not in target:
                                return normalize_host(value) == host
                            original, candidate = urlsplit(value), urlsplit(target)
                            return (original.scheme, original.hostname, original.port or (443 if original.scheme == "https" else 80)) == (candidate.scheme, candidate.hostname, candidate.port or (443 if candidate.scheme == "https" else 80))
                        if any(same_endpoint(s["target"]) for s in existing if s["target"]):
                            continue
                        active_target = target if "://" in target else "https://" + ("[" + host + "]" if ":" in host else host)
                    if policy.check(cap, active_target, network=False).allowed:
                        self._enqueue(run, cap, active_target, round_number)

    def plan(self, project_id):
        from .preflight import dependency_status
        config = self.project(project_id)["config"]
        policy = ExecutionPolicy(config)
        package = config["execution"]["source"] == "replay" and config["execution"].get("evidence_dir")
        steps = []
        seen_hosts = set()
        maximum_hosts = int(config["budgets"].get("max_hosts", 1000))
        for capability in (["search"] if package else config["plan"]["steps"]):
            targets = ["__evidence_package__"] if package else self._targets(config, capability) or [""]
            tools = policy.tools_for(capability)[:1] if package else policy.tools_for(capability)
            for target in targets:
                for tool in tools:
                    try:
                        host = normalize_host(target) if target and target != "__evidence_package__" else target
                    except ValueError:
                        host = target
                    if target and host not in seen_hosts and len(seen_hosts) >= maximum_hosts:
                        continue
                    if target:
                        seen_hosts.add(host)
                    kind = "subject" if capability == "company_lookup" else "host"
                    if capability in {"search", "osint", "passive_supply_chain"}:
                        ref = config.get("permissions", {}).get(capability, {}).get("scope_ref", "investigation")
                        for candidate in ("subject", "query", "brand"):
                            if policy.contains(ref, target, target_kind=candidate):
                                kind = candidate
                                break
                    decision = policy.check(capability, target, target_kind=kind, tool=tool, network=False)
                    dependencies = dependency_status(config, capability, tool)
                    steps.append({"capability": capability, "target": target, "tool": tool, "params": policy.params(capability, tool),
                        "status": "planned", "permitted": bool(package or target and decision.allowed),
                        "reason": "saved_evidence_import_only" if package else "no_targets_or_required_input" if not target else decision.reason,
                        "dependencies": dependencies, "can_execute": bool((package or target and decision.allowed) and dependencies["status"] != "blocked"),
                        "scope_ref": decision.scope_ref})
        return {"project_id": project_id, "config_hash": digest(config), "permission_version": config.get("permission_version"),
            "mode_version": config.get("mode_version"), "source": config["execution"]["source"], "steps": steps,
            "budgets": config["budgets"], "note": "This is a plan preview. Each action rechecks current permissions, scope, dependencies and budgets."}

    def start(self, project_id, *, source=None, background=True, selected_capabilities=None, passive_only=False, target_local=False):
        project = self.project(project_id)
        config = copy.deepcopy(project["config"])
        if source:
            if source not in {"live", "replay"}:
                raise ValueError("Unknown execution source")
            config["execution"]["source"] = source
        policy = ExecutionPolicy(config)
        if selected_capabilities is not None:
            if not isinstance(selected_capabilities, list) or set(selected_capabilities) - set(config["mode_capabilities"]):
                raise ValueError("Unknown or unsupported selected capability")
            config["plan"]["steps"] = [c for c in config["plan"]["steps"] if c in selected_capabilities]
        if passive_only:
            from .policy import PASSIVE
            config["plan"]["steps"] = [c for c in config["plan"]["steps"] if c in PASSIVE]
        if target_local:
            config["execution"]["target_local"] = True
        run_id = uuid.uuid4().hex
        lease = self.store.run_lease(run_id)
        try:
            return self._create_run(project_id, project, config, policy, run_id, background, lease)
        except BaseException:
            lease.close()
            raise

    def _create_run(self, project_id, project, config, policy, run_id, background, lease):
        purpose = project.get("purpose", "investigation")
        directory = self.root / "report" / PURPOSE_DIRECTORIES[purpose] / (project_id + "_delivery") / "runs" / run_id
        directory.mkdir(parents=True, exist_ok=False)
        for subdir in ("evidence", "logs", "checkpoints"):
            (directory / subdir).mkdir()
        (directory / "run-config.redacted.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
        with self.store.connection() as conn:
            conn.execute("INSERT INTO runs(id,project,status,config,directory,started) VALUES(?,?,?,?,?,?)",
                         (run_id, project_id, "pending", encode(config), str(directory), utcnow()))
            self.store.event(run_id, "run_state", {"state": "pending", "config_hash": digest(config), "permission_revision": project["revision"]}, conn)
        run = self.run(run_id)
        if config["execution"]["source"] == "replay" and config["execution"].get("evidence_dir"):
            self._enqueue(run, "search", "__evidence_package__", 0)
        else:
            for capability in config["plan"]["steps"]:
                if policy.selected(capability):
                    targets = self._targets(config, capability)
                    if not targets:
                        self._enqueue(run, capability, "", 0)
                    for target in targets:
                        self._enqueue(run, capability, target, 0)
        self.checkpoint(run_id)
        self._launch(run_id, background, lease=lease)
        return self.run(run_id)

    def run(self, run_id):
        rows = self.store.rows("SELECT * FROM runs WHERE id=?", (run_id,))
        if not rows:
            raise ValueError("Unknown run")
        row = rows[0]
        steps = self.store.rows("SELECT * FROM steps WHERE run=? ORDER BY round,rowid", (run_id,))
        delivery = self.store.rows("SELECT kind,data FROM events WHERE run=? AND kind IN ('report_exported','report_export_failed') ORDER BY id DESC LIMIT 1", (run_id,))
        delivery_error = json.loads(delivery[0]["data"]) if delivery and delivery[0]["kind"] == "report_export_failed" else None
        return {"run_id": row["id"], "project_id": row["project"], "status": row["status"], "delivery_error": delivery_error,
            "config": json.loads(row["config"]), "directory": row["directory"], "started_at": row["started"],
            "finished_at": row["finished"], "snapshot": json.loads(row["snapshot"]) if row["snapshot"] else None,
            "steps": [{**s, "params": json.loads(s["params"])} for s in steps],
            "assets": [json.loads(a["data"]) for a in self.store.rows("SELECT data FROM assets WHERE run=? ORDER BY id", (run_id,))]}

    def _state(self, run_id, state, reason=""):
        with self.store.connection() as conn:
            conn.execute("UPDATE runs SET status=? WHERE id=?", (state, run_id))
            self.store.event(run_id, "run_state", {"state": state, "reason": reason}, conn)
        self.checkpoint(run_id)

    def control(self, run_id, action):
        run = self.run(run_id)
        if action == "pause":
            if run["status"] not in {"running", "pending"}:
                raise ValueError("Run is not running")
            self._state(run_id, "pausing", "finish_current_action_then_pause")
        elif action == "stop":
            if run["status"] in {"completed", "stopped"}:
                return run
            self._state(run_id, "stopping", "cancel_current_action_and_keep_evidence")
            try:
                lease = self.store.run_lease(run_id)
            except LeaseBusy:
                pass
            else:
                with lease:
                    self._state(run_id, "stopped")
                    self.export(run_id)
        elif action == "resume":
            return self.resume(run_id)
        else:
            raise ValueError("Unknown control action")
        return self.run(run_id)

    def resume(self, run_id, *, background=True):
        lease = self.store.run_lease(run_id)
        try:
            return self._resume_owned(run_id, background=background, lease=lease)
        except BaseException:
            lease.close()
            raise

    def _resume_owned(self, run_id, *, background, lease):
        run = self.run(run_id)
        if run["status"] not in {"paused", "interrupted", "stopped", "partial", "completed"}:
            raise ValueError("Run cannot be resumed in its current state")
        with self.store.connection() as conn:
            conn.execute("UPDATE steps SET status='pending' WHERE run=? AND status='interrupted'", (run_id,))
        # Reconcile a crash during initial plan insertion. IDs retain all completed receipts.
        if run["config"]["execution"]["source"] == "replay" and run["config"]["execution"].get("evidence_dir"):
            self._enqueue(run, "search", "__evidence_package__", 0)
        else:
            for cap in run["config"]["plan"]["steps"]:
                for target in self._targets(run["config"], cap) or [""]:
                    self._enqueue(run, cap, target, 0)
        self._state(run_id, "pending", "resume_original_run_with_current_permissions")
        self._launch(run_id, background, lease=lease)
        return self.run(run_id)

    def _launch(self, run_id, background, *, lease=None):
        with self.lock:
            old = self.threads.get(run_id)
            if old and old.is_alive():
                raise ValueError("Run already has a worker")
            lease = lease or self.store.run_lease(run_id)
            if background:
                worker = threading.Thread(target=self.execute, args=(run_id,), kwargs={"lease": lease}, daemon=True, name="asm-" + run_id)
                self.threads[run_id] = worker
                worker.start()
            else:
                self.execute(run_id, lease=lease)

    def check_control(self, run_id):
        state = self.store.rows("SELECT status FROM runs WHERE id=?", (run_id,))[0]["status"]
        if state in {"pausing", "stopping", "paused", "stopped", "interrupted"}:
            raise RunControlled(state)

    def execute(self, run_id, *, lease=None):
        with lease or self.store.run_lease(run_id):
            return self._execute_owned(run_id)

    def _execute_owned(self, run_id):
        from .workbench_tools import ExecutionContext, tool_registry
        adapters = self.adapters or tool_registry()
        try:
            with self.store.connection() as conn:
                state = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()[0]
                if state in {"pausing", "stopping", "paused", "stopped"}:
                    raise RunControlled(state)
                conn.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
                self.store.event(run_id, "run_state", {"state": "running"}, conn)
            self.checkpoint(run_id)
            while True:
                self.check_control(run_id)
                self._drain_feedback(run_id)
                run = self.run(run_id)
                pending = [s for s in run["steps"] if s["status"] == "pending"]
                if not pending:
                    break
                step = pending[0]
                receipt = Path(step["receipt"]) if step["receipt"] else None
                if receipt and receipt.is_file():
                    self._merge(run, step, json.loads(receipt.read_text(encoding="utf-8")))
                    continue
                receipt = Path(run["directory"]) / "checkpoints" / (step["id"] + "-" + str(step["attempt"] + 1) + ".receipt.json")
                with self.store.connection() as conn:
                    # Reserve the receipt location before execution so a crash after write can recover it.
                    conn.execute("UPDATE steps SET status='running',attempt=attempt+1,receipt=? WHERE id=?", (str(receipt), step["id"]))
                    self.store.event(run_id, "stage_transition", {"step_id": step["id"], "capability": step["capability"], "state": "running"}, conn)
                ctx = ExecutionContext(self, run, step)
                try:
                    if run["config"]["execution"]["source"] == "replay":
                        from .replay import replay_step
                        result = replay_step(ctx)
                    else:
                        if not step["target"]:
                            result = {"status": "skipped", "reason": "no_targets_or_required_input", "assets": [], "records": []}
                        elif step["capability"] not in adapters:
                            result = {"status": "blocked", "reason": "adapter_not_integrated", "assets": [], "records": []}
                        else:
                            ctx.require(step["target"], network=False)
                            result = adapters[step["capability"]](ctx)
                except PolicyDenied as exc:
                    result = {"status": "quota-exhausted" if "budget" in str(exc) else "skipped", "reason": str(exc), "assets": [], "records": []}
                except RunControlled:
                    with self.store.connection() as conn:
                        conn.execute("UPDATE steps SET status='interrupted' WHERE id=?", (step["id"],))
                    raise
                except Exception as exc:
                    # Exceptions from HTTP libraries may contain credential-bearing URLs.
                    result = {"status": "failed", "reason": type(exc).__name__, "assets": [], "records": []}
                atomic_json(receipt, result)
                self._merge(run, step, result)
            run = self.run(run_id)
            gap = any(e["kind"] == "coverage_gap" for e in self.store.events(run_id))
            state = "partial" if gap or any(s["status"] in {"failed", "partial", "blocked", "quota-exhausted"} for s in run["steps"]) else "completed"
            self._state(run_id, state)
        except RunControlled as exc:
            self._state(run_id, "stopped" if str(exc) in {"stopping", "stopped"} else "paused")
        except BaseException:
            with self.store.connection() as conn:
                conn.execute("UPDATE steps SET status='interrupted' WHERE run=? AND status='running'", (run_id,))
            self._state(run_id, "interrupted", "worker_interrupted")
            raise
        finally:
            with self.store.connection() as conn:
                conn.execute("UPDATE runs SET finished=? WHERE id=?", (utcnow(), run_id))
            self.checkpoint(run_id)
            self.export(run_id)

    def _merge(self, run, step, result):
        policy = self._policy(run)
        next_targets = []
        with self.store.connection() as conn:
            for row in result.get("assets", []):
                row = copy.deepcopy(row)
                target = row.get("domain") or row.get("name") or row.get("host") or row.get("ip")
                try:
                    in_scope = policy.contains("investigation", normalize_host(target))
                except (TypeError, ValueError):
                    in_scope = False
                row["scope_status"] = "in_scope" if in_scope else "out_of_scope"
                row.setdefault("verification_status", "candidate_only")
                row.setdefault("attribution_status", "unconfirmed")
                row.setdefault("observed_at", utcnow())
                self.store.upsert_asset(conn, run["run_id"], row)
                if in_scope:
                    next_targets.append(row.get("url") or target)
                    port = int(row.get("port") or 0)
                    if port and row.get("proto", row.get("protocol", "tcp")) == "tcp" and not row.get("url"):
                        service = str(row.get("service", "")).lower()
                        if port in {80, 443, 8000, 8080, 8081, 8443, 8888, 9000, 9443} or "http" in service:
                            scheme = "https" if port in {443, 8443, 9443} or "ssl" in service else "http"
                            authority = "[" + target + "]" if ":" in target else target
                            next_targets.append(scheme + "://" + authority + ":" + str(port) + "/")
                    if row.get("ip") and policy.contains("investigation", row["ip"]):
                        next_targets.append(row["ip"])
                else:
                    self.store.event(run["run_id"], "out_of_scope", {"lead": target, "category": row.get("lead_category", "unclassified"), "evidence": row.get("evidence_ids", [])}, conn)
            for row in result.get("records", []):
                key = row.get("record_id") or row.get("evidence_id") or digest([step["id"], row])
                conn.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?)", (key, run["run_id"], row.get("category", "observations"), encode(row)))
            status = result.get("status", "completed")
            for target in next_targets:
                key = digest([run["run_id"], step["id"], target])
                conn.execute("INSERT OR IGNORE INTO feedback VALUES(?,?,?,?,?)", (key, run["run_id"], target, step["round"] + 1, "pending"))
            conn.execute("UPDATE steps SET status=?,reason=? WHERE id=?", (status, result.get("reason", ""), step["id"]))
            self.store.event(run["run_id"], "stage_transition", {"step_id": step["id"], "capability": step["capability"], "state": status, "reason": result.get("reason", "")}, conn)
        self._drain_feedback(run["run_id"])
        self.checkpoint(run["run_id"])

    def _drain_feedback(self, run_id):
        run = self.run(run_id)
        for row in self.store.rows("SELECT * FROM feedback WHERE run=? AND status='pending'", (run_id,)):
            self._enqueue_targets(run, [row["target"]], row["round"])
            with self.store.connection() as conn:
                conn.execute("UPDATE feedback SET status='completed' WHERE id=?", (row["id"],))

    def checkpoint(self, run_id):
        with self.store.lock:
            return self._checkpoint_locked(run_id)

    def _checkpoint_locked(self, run_id):
        run = self.run(run_id)
        self.store.flush_logs(run_id, run["directory"])
        atomic_json(Path(run["directory"]) / "observations.json", run["assets"])
        atomic_json(Path(run["directory"]) / "checkpoints/current.json", {"run_id": run_id,
            "status": run["status"], "steps": run["steps"], "project_revision": self.project(run["project_id"])["revision"],
            "config_hash": digest(run["config"]), "ledger": str(self.root / "data/account-rate-ledger.sqlite"), "updated_at": utcnow()})

    def export(self, run_id):
        with self.store.lock:
            try:
                return self._export_locked(run_id)
            except (OSError, ValueError, ImportError) as exc:
                from .delivery import save_export_failure
                failure = save_export_failure(self.run(run_id), exc)
                self.store.event(run_id, "report_export_failed", failure)
                return failure

    def _export_locked(self, run_id):
        from .reports import export_snapshot
        from .delivery import comparison_key, snapshot_changes, write_navigation
        run = self.run(run_id)
        records = [json.loads(r["data"]) for r in self.store.rows("SELECT data FROM records WHERE run=?", (run_id,))]
        tables = {}
        for record in records:
            tables.setdefault(record.get("category", "observations"), []).append(record)
        current = self.project(run["project_id"])
        self.store.flush_logs(run_id, run["directory"])
        events = self.store.events(run_id)
        log_cutoff = {"last_event_id": events[-1]["id"] if events else 0, "event_count": len(events), "files": {}}
        for name in ("events.jsonl", "tool-calls.jsonl"):
            path = Path(run["directory"]) / "logs" / name
            raw = path.read_bytes()
            log_cutoff["files"][name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        ledger = self.root / "data/account-rate-ledger.sqlite"
        usage = {"status": "no_ledger", "used": 0, "rows": []}
        ledger_reference = {"path": str(ledger), "status": "no_ledger"}
        try:
            if ledger.is_file():
                ledger_copy = Path(run["directory"]) / "logs" / ("rate-ledger-" + uuid.uuid4().hex + ".sqlite")
                with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as source, sqlite3.connect(ledger_copy) as dest:
                    source.backup(dest)
                    dest.row_factory = sqlite3.Row
                    rows = [dict(r) for r in dest.execute("SELECT * FROM sources ORDER BY day,source")]
                usage = {"status": "known", "rows": rows}
                ledger_reference = {"path": str(ledger), "snapshot": ledger_copy.relative_to(run["directory"]).as_posix(), "sha256": hashlib.sha256(ledger_copy.read_bytes()).hexdigest(), "status": "known"}
        except (OSError, sqlite3.Error):
            usage = {"status": "unknown", "used": None}
            ledger_reference["status"] = "unknown"
        coverage = [{"feature": s["capability"], "target": s["target"], "status": s["status"], "reason": s["reason"], "tool": s["tool"], "params": s["params"]} for s in run["steps"]]
        for cap in run["config"].get("capability_catalog", {}):
            if cap not in {s["capability"] for s in run["steps"]}:
                coverage.append({"feature": cap, "status": "not_selected", "reason": "not_selected_or_not_permitted"})
        tables["execution_steps"] = coverage
        snapshot = {"project_id": run["project_id"], "run_id": run_id,
            "mode": run["config"].get("mode_preset"), "execution_source": run["config"]["execution"]["source"],
            "status": run["status"], "started_at": run["started_at"], "finished_at": run["finished_at"], "data_cutoff": utcnow(),
            "config_hash": digest(run["config"]), "permission_revision": current["revision"], "scope_revision": current["revision"],
            "permissions": current["config"].get("permissions", {}), "scope": current["config"].get("scope_sets", {}),
            "target": run["config"].get("targets", {}), "budget": run["config"].get("budgets", {}), "usage": usage,
            "assets": run["assets"], "tables": tables, "coverage": coverage, "observations": records,
            "evidence": tables.get("evidence_index", []), "audit": {"logs": log_cutoff,
            "permission_version": current["config"].get("permission_version"), "scope_revision": current["revision"],
            "usage": usage, "ledger_reference": ledger_reference}}
        snapshot["comparison_key"] = comparison_key(run["config"], current["config"])
        candidates = sorted((Path(run["directory"]) / "exports").glob("*"), reverse=True)
        for older in self.store.rows("SELECT directory FROM runs WHERE project=? AND id!=? AND started<? ORDER BY started DESC", (run["project_id"], run_id, run["started_at"])):
            candidates.extend(sorted((Path(older["directory"]) / "exports").glob("*"), reverse=True))
        snapshot["changes"] = snapshot_changes(snapshot, candidates)
        manifest = export_snapshot(Path(run["directory"]), snapshot)
        with self.store.connection() as conn:
            conn.execute("UPDATE runs SET snapshot=? WHERE id=?", (encode(manifest), run_id))
            self.store.event(run_id, "report_exported", manifest, conn)
        self.store.flush_logs(run_id, run["directory"])
        atomic_json(Path(run["directory"]).parents[1] / "latest.json", {"run_id": run_id, "snapshot_id": manifest["snapshot_id"]})
        try:
            write_navigation(run, manifest, self.store.rows("SELECT id,status FROM runs WHERE project=? ORDER BY started DESC", (run["project_id"],)))
        except OSError as exc:
            self.store.event(run_id, "navigation_failed", {"reason": type(exc).__name__})
        return manifest

    def artifacts(self, run_id):
        run = self.run(run_id)
        root = Path(run["directory"])
        return [{"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size} for p in sorted(root.rglob("*")) if p.is_file()]

    def bundle(self, run_id, snapshot_id=None):
        from .bundle import create_bundle
        with self.store.lock:
            return create_bundle(self.run(run_id), snapshot_id)

    def review(self, run_id, asset_id, **decision):
        from .review import review_asset
        return review_asset(self, run_id, asset_id, **decision)

    def artifact(self, run_id, relative):
        root = Path(self.run(run_id)["directory"]).resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or any(p.startswith(".env") for p in path.parts):
            raise ValueError("Invalid artifact path")
        return path
