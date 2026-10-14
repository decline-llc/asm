"""Independently authorized DNS, port/service and TLS execution adapters.

Native socket probes are an explicitly selected tool, never a fallback for an
unavailable scanner. Port discovery does not run service/version scripts.
"""
from dataclasses import asdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import select
import shlex
import socket
import ssl
import subprocess
import threading
import time
import uuid

import dns.exception
import dns.flags
import dns.message
import dns.rcode

from .bridge import Bridge, BridgeError, decode
from .policy import PolicyDenied
from .scope import is_local, normalize_host
from .stages.s6_port import parse_nmap, parse_ports
from .utils.dns import RTYPES, endpoint, parse_endpoint, record_value


DEEP_SCRIPTS = frozenset({"banner", "ssl-cert", "ssh-hostkey", "http-title", "http-headers", "dns-service-discovery"})
BASIC_LABELS = ("www", "api", "admin", "mail", "dev", "test", "staging", "vpn", "portal", "auth", "cdn", "static")


def _result(status="completed", reason="", assets=None, records=None):
    return {"status": status, "reason": reason, "assets": assets or [], "records": records or []}


def _tool(ctx):
    return ctx.step.get("tool") or ctx.capability


def _evidence(ctx):
    value = getattr(ctx, "last_evidence_id", None)
    return [value] if value else []


def _ports(ctx):
    value = ctx.params.get("ports", "")
    if not value and ctx.capability in {"service_probe", "deep_service_probe"}:
        target = normalize_host(ctx.target)
        known = {int(asset["port"]) for asset in ctx.run.get("assets", []) if asset.get("proto", "tcp") == "tcp"
                 and asset.get("port") and target in {asset.get("host"), asset.get("ip")}}
        return sorted(known)
    if not value:
        return []
    return sorted(parse_ports(value))


def _literal_target(ctx):
    host = normalize_host(ctx.target)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise PolicyDenied("Port probes require an explicitly approved literal IP") from None
    record_value("A" if ip.version == 4 else "AAAA", host,
                 reject_fake_ip=ctx.run["config"].get("dns", {}).get("reject_fake_ip", True))
    return host


def _native_probe(ctx):
    target = _literal_target(ctx)
    ports = _ports(ctx)
    if not ports:
        return _result("skipped", "empty_explicit_ports")
    if ctx.capability not in {"tcp_scan", "udp_scan"}:
        return _result("blocked", "native_socket_supports_port_observation_only")
    family = socket.AF_INET6 if ":" in target else socket.AF_INET
    proto = "udp" if ctx.capability == "udp_scan" else "tcp"
    timeout = float(ctx.params.get("timeout_seconds", 1))
    payload = ctx.params.get("probe_payload", "").encode("utf-8")
    if len(payload) > 4096:
        return _result("blocked", "udp_probe_payload_exceeds_budget")
    records, assets = [], []
    rate = float(ctx.params.get("packets_per_second", 100))
    if rate <= 0:
        raise ValueError("packets_per_second must be positive")
    for port in ports:
        ctx.require(target)

        def probe():
            ctx.require(target)
            with socket.socket(family, socket.SOCK_DGRAM if proto == "udp" else socket.SOCK_STREAM) as connection:
                connection.settimeout(timeout)
                try:
                    if proto == "tcp":
                        connection.connect((target, port))
                        return {"state": "open", "host": target, "port": port, "proto": proto}
                    connection.sendto(payload, (target, port))
                    reply, peer = connection.recvfrom(4096)
                    if normalize_host(peer[0]) != target or peer[1] != port:
                        return {"state": "unexpected_peer", "host": target, "port": port, "proto": proto}
                    return {"state": "open", "host": target, "port": port, "proto": proto,
                            "response_hex": reply.hex(), "response_bytes": len(reply)}
                except (TimeoutError, socket.timeout):
                    return {"state": "open_or_filtered" if proto == "udp" else "filtered_or_unreachable",
                            "host": target, "port": port, "proto": proto}
                except ConnectionRefusedError:
                    return {"state": "closed", "host": target, "port": port, "proto": proto}
                except OSError as exc:
                    return {"state": "error", "error": type(exc).__name__, "host": target, "port": port, "proto": proto}

        raw = ctx.call(_tool(ctx), {"target": target, "port": port, "protocol": proto, "timeout_seconds": timeout}, probe)
        record = {"category": "port_observations", "knowledge": "observation", **raw, "evidence_ids": _evidence(ctx)}
        records.append(record)
        if raw["state"] == "open":
            assets.append({"host": target, "ip": target, "port": port, "proto": proto,
                           "source": _tool(ctx), "verification_status": "observed", "attribution_status": "unconfirmed",
                           "evidence_ids": _evidence(ctx)})
        ctx.wait(1 / rate)
    failures = [record for record in records if record["state"] in {"error", "unexpected_peer"}]
    return _result("partial" if failures else "completed", "socket_observation_errors" if failures else "", assets, records)


def scanner_args(ctx, ports=None):
    """Return a separated scanner invocation; no implicit -sV/-sC in discovery."""
    target = _literal_target(ctx)
    ports = _ports(ctx) if ports is None else ports
    if not ports:
        return None
    tool = _tool(ctx)
    rate = float(ctx.params.get("packets_per_second", 100))
    if tool == "masscan":
        if ctx.capability != "tcp_scan" or ":" in target:
            return None
        return [target, "-p" + ",".join(map(str, ports)), "--rate", str(rate), "-oJ", "-"]
    if tool != "nmap":
        return None
    args = ["-6"] if ":" in target else []
    args += ["-sU"] if ctx.capability == "udp_scan" else ["-sT"]
    if ctx.capability == "service_probe":
        if ctx.params.get("approved_script_categories"):
            raise PolicyDenied("service_script_categories_require_deep_service_probe_with_explicit_approved_probes")
        if ctx.params.get("version_detection", True):
            args += ["-sV", "--version-intensity", str(int(ctx.params.get("version_intensity", 7)))]
    elif ctx.capability == "deep_service_probe":
        probes = ctx.params.get("approved_probes", [])
        if not probes or any(probe not in DEEP_SCRIPTS for probe in probes):
            return None
        args += ["--script", ",".join(probes)]
    elif ctx.capability not in {"tcp_scan", "udp_scan"}:
        return None
    args += ["-n", "-Pn", "--disable-arp-ping", "--max-rate", str(rate),
             "--host-timeout", str(int(ctx.params.get("host_timeout_seconds", 120))) + "s",
             "-p", ",".join(map(str, ports)), "-oX", "-", target]
    return args


def _run_scanner(ctx, args, *, executable=None, cwd=None):
    """Keep a process group so revocation/stop also terminates the WSL child."""
    tool = _tool(ctx)
    bridge = getattr(ctx, "bridge", None) or Bridge()
    timeout = float(ctx.params.get("timeout_seconds", ctx.params.get("host_timeout_seconds", 180)))
    root = tool == "masscan" or ctx.capability == "udp_scan"
    pid_path = "/tmp/asm-workbench-" + uuid.uuid4().hex + ".pid"
    process = None
    try:
        command = bridge.command(executable or tool, args, timeout=timeout)
        script = "echo $$ > " + shlex.quote(pid_path) + "; " + command
        launcher = "setsid --fork --wait bash -c " + shlex.quote(script)
        ctx.require(ctx.target)
        output_directory = Path(ctx.output_directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        attempt_id = uuid.uuid4().hex
        stdout_path = output_directory / (attempt_id + ".scanner.stdout")
        stderr_path = output_directory / (attempt_id + ".scanner.stderr")
        with stdout_path.open("w+b") as stdout, stderr_path.open("w+b") as stderr:
            process = subprocess.Popen(bridge.argv(launcher, root=root, cwd=cwd), stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr)
            deadline = time.monotonic() + timeout + 10
            while process.poll() is None:
                ctx.require(ctx.target)
                ctx.check_control()
                if time.monotonic() >= deadline:
                    raise TimeoutError("scanner_timeout")
                ctx.wait(0.2)
            stdout.seek(0)
            stderr.seek(0)
            return {"tool": tool, "args": args, "exit_code": process.returncode,
                    "stdout": decode(stdout.read(32 * 1024 * 1024)), "stderr": decode(stderr.read(65536)),
                    "stdout_path": str(stdout_path), "stderr_path": str(stderr_path), "timeout_seconds": timeout}
    except (BridgeError, FileNotFoundError) as exc:
        return {"tool": tool, "args": args, "exit_code": None, "availability": "unavailable", "error": type(exc).__name__}
    finally:
        if process is not None and process.poll() is None:
            # pid_path is generated locally. No target or user string enters this shell fragment.
            try:
                bridge.control("if test -f " + shlex.quote(pid_path) + "; then kill -TERM -- -$(cat " + shlex.quote(pid_path) + ") 2>/dev/null; fi", root=root, timeout=5, check=False)
            except BridgeError:
                pass
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        try:
            bridge.control("rm -f -- " + shlex.quote(pid_path), root=root, timeout=5, check=False)
        except BridgeError:
            pass
        # Index streamed files even when control/revocation interrupted the callback.
        if "stdout_path" in locals() and hasattr(ctx, "_evidence"):
            for path in (stdout_path, stderr_path):
                if path.is_file():
                    ctx._evidence(uuid.uuid4().hex, path, "scanner_stream")


def port_service(ctx):
    if _tool(ctx) in {"python_socket", "tcp_socket", "udp_socket"}:
        return _native_probe(ctx)
    if _tool(ctx) in {"naabu", "a_scan"}:
        from .external_tools import port_scan
        return port_scan(ctx)
    args = scanner_args(ctx)
    if args is None:
        return _result("skipped" if not _ports(ctx) or ctx.capability == "deep_service_probe" else "blocked",
                       "empty_ports_or_unapproved_probes_or_unsupported_tool")
    split = ctx.params.get("split_batches", False)
    size = ctx.params.get("batch_size", 512)
    if type(split) is not bool or isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 4096:
        raise ValueError("split_batches must be boolean; batch_size must be an integer from 1 to 4096")
    ports = _ports(ctx)
    batches = [ports[index:index + size] for index in range(0, len(ports), size)] if split else [ports]
    assets, records = [], []
    for batch_number, batch in enumerate(batches, 1):
        invocation = scanner_args(ctx, batch)
        batch_result = _scanner_batch(ctx, invocation)
        assets.extend(batch_result["assets"])
        records.extend({**record, "batch_number": batch_number, "batch_count": len(batches), "covered_ports": batch}
                       for record in batch_result["records"])
        if batch_result["status"] != "completed":
            return _result("partial" if batch_number > 1 else batch_result["status"], batch_result["reason"], assets, records)
    return _result(assets=assets, records=records)


def _scanner_batch(ctx, args):
    raw = ctx.call(_tool(ctx), {"target": ctx.target, "args": args}, lambda: _run_scanner(ctx, args))
    if raw.get("availability") == "unavailable":
        return _result("blocked", "scanner_dependency_unavailable", records=[{"category": "service_observations", **raw, "evidence_ids": _evidence(ctx)}])
    if raw["exit_code"] != 0:
        return _result("failed", "scanner_exit_" + str(raw["exit_code"]), records=[{"category": "service_observations", **raw, "evidence_ids": _evidence(ctx)}])
    if _tool(ctx) == "masscan":
        assets = [{"host": row["ip"], "ip": row["ip"], "port": int(port["port"]), "proto": port.get("proto", "tcp"),
                   "source": "masscan"} for row in json.loads(raw["stdout"]) for port in row.get("ports", []) if port.get("status", "open") == "open"]
    else:
        output_hash = hashlib.sha256(raw["stdout"].encode("utf-8")).hexdigest()
        parsed_directory = Path(ctx.run["directory"]) / "evidence/parsed-nmap" if ctx.run.get("directory") else Path(ctx.output_directory)
        path = parsed_directory / ("nmap-" + output_hash + ".xml")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            path.write_bytes(raw["stdout"].encode("utf-8"))
        elif hashlib.sha256(path.read_bytes()).hexdigest() != output_hash:
            raise ValueError("Saved parsed scanner input checksum mismatch")
        assets = [asdict(asset) for asset in parse_nmap(path)]
    for asset in assets:
        ctx.require(asset["host"], network=False)
        asset.update({"verification_status": "observed", "attribution_status": "unconfirmed", "evidence_ids": _evidence(ctx)})
    return _result(assets=assets, records=[{"category": "service_observations", "knowledge": "observation",
                                          "target": ctx.target, "tool": _tool(ctx), "args": args,
                                          "evidence_ids": _evidence(ctx)}])


def _resolvers(ctx):
    values = ctx.params.get("resolvers") or ctx.run["config"].get("dns", {}).get("resolvers")
    if not values:
        raise PolicyDenied("Explicit DNS resolvers are required")
    if not isinstance(values, (list, tuple)) or len(values) > 10 or any(not isinstance(value, str) for value in values):
        raise ValueError("DNS resolvers must contain at most 10 explicit IP endpoints")
    values = list(dict.fromkeys(endpoint(value) for value in values))
    if ctx.run["config"].get("execution", {}).get("target_local") and any(not is_local(parse_endpoint(value)[0]) for value in values):
        raise PolicyDenied("Local fixture execution forbids external DNS resolvers")
    return values


def _dns_integer(ctx, name, default, maximum, *, minimum=1):
    value = ctx.params.get(name, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


class _DNSGate:
    """One rate gate shared by workers; cached receipts never enter it."""
    def __init__(self, ctx):
        rate = ctx.params.get("requests_per_second", 10)
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 < rate <= 100000:
            raise ValueError("DNS requests_per_second must be positive and bounded")
        self.interval, self.next_start, self.lock = 1 / rate, 0, threading.Lock()

    def start(self, ctx, domain):
        while not self.lock.acquire(timeout=0.1):
            ctx.require(domain)
        try:
            ctx.wait(max(0, self.next_start - time.monotonic()))
            ctx.require(domain)
            self.next_start = time.monotonic() + self.interval
        finally:
            self.lock.release()


def _dns_ready(ctx, domain, connection, deadline, *, writing=False):
    while True:
        ctx.require(domain)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("DNS query lifetime expired")
        readers, writers, _ = select.select([] if writing else [connection], [connection] if writing else [], [], min(0.1, remaining))
        if readers or writers:
            return


def _dns_tcp(ctx, domain, query, host, port, deadline):
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        connection.setblocking(False)
        ctx.require(domain)
        connection.connect_ex((host, port))
        _dns_ready(ctx, domain, connection, deadline, writing=True)
        error = connection.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if error:
            raise OSError(error, "DNS TCP connection failed")
        wire = query.to_wire()
        remaining = memoryview(len(wire).to_bytes(2, "big") + wire)
        while remaining:
            _dns_ready(ctx, domain, connection, deadline, writing=True)
            remaining = remaining[connection.send(remaining):]
        packet = bytearray()
        needed = 2
        while len(packet) < needed:
            _dns_ready(ctx, domain, connection, deadline)
            chunk = connection.recv(needed - len(packet))
            if not chunk:
                raise OSError("DNS TCP response ended early")
            packet.extend(chunk)
            if needed == 2 and len(packet) == 2:
                needed += int.from_bytes(packet, "big")
        response = dns.message.from_wire(bytes(packet[2:]))
        if not query.is_response(response):
            raise ValueError("DNS TCP response does not match the query")
        return response


def _dns_exchange(ctx, domain, query, host, port, timeout):
    """One UDP send, optional explicit TCP fallback, with cancellable polling."""
    deadline = time.monotonic() + timeout
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as connection:
        connection.setblocking(False)
        ctx.require(domain)
        connection.sendto(query.to_wire(), (host, port))
        while True:
            _dns_ready(ctx, domain, connection, deadline)
            packet, peer = connection.recvfrom(65535)
            if normalize_host(peer[0]) != host or peer[1] != port:
                continue
            response = dns.message.from_wire(packet)
            if not query.is_response(response):
                continue
            if response.flags & dns.flags.TC:
                return _dns_tcp(ctx, domain, query, host, port, deadline)
            return response


def _dns_query(ctx, domain, rtype, resolver, gate=None):
    host, port = parse_endpoint(resolver)
    timeout = ctx.params.get("timeout_seconds", 3)
    if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not 0 < timeout <= 60:
        raise ValueError("DNS timeout_seconds must be positive and at most 60")
    ctx.require(domain)
    if gate is not None:
        gate.start(ctx, domain)
    try:
        response = _dns_exchange(ctx, domain, dns.message.make_query(domain + ".", rtype), host, port, timeout)
        status = dns.rcode.to_text(response.rcode())
        values = []
        for rrset in response.answer:
            name = dns.rdatatype.to_text(rrset.rdtype)
            for rr in rrset:
                accepted, rejection = True, ""
                try:
                    value = record_value(name, str(rr), reject_fake_ip=ctx.params.get("reject_fake_ip", True))
                except ValueError as exc:
                    value, accepted, rejection = str(rr), False, str(exc)
                values.append({"name": str(rrset.name).rstrip("."), "rtype": name, "value": value,
                               "accepted": accepted, "rejection": rejection, "ttl": rrset.ttl})
        values.sort(key=lambda item: (item["name"], item["rtype"], item["value"]))
        return {"domain": domain, "query_type": rtype, "resolver": resolver, "status": status, "answers": values}
    except TimeoutError:
        return {"domain": domain, "query_type": rtype, "resolver": resolver, "status": "LifetimeTimeout", "answers": []}
    except dns.exception.DNSException as exc:
        return {"domain": domain, "query_type": rtype, "resolver": resolver, "status": type(exc).__name__, "answers": []}
    except OSError as exc:
        return {"domain": domain, "query_type": rtype, "resolver": resolver, "status": type(exc).__name__, "answers": []}


def _query_observation(ctx, domain, rtype, resolver, gate=None):
    if _tool(ctx) in {"dnsx", "dig_probe"}:
        from .external_tools import dns_query
        raw = ctx.call(_tool(ctx), {"domain": domain, "rtype": rtype, "resolver": resolver},
                       lambda: dns_query(ctx, domain, rtype, resolver, gate))
        return {"category": "dns_observations", "knowledge": "observation", **raw, "evidence_ids": _evidence(ctx)}
    raw = ctx.call(_tool(ctx), {"domain": domain, "rtype": rtype, "resolver": resolver},
                   lambda: _dns_query(ctx, domain, rtype, resolver, gate))
    return {"category": "dns_observations", "knowledge": "observation", **raw, "evidence_ids": _evidence(ctx)}


def _dns_batch(ctx, jobs, gate):
    """Bound submissions and isolate mutable call/evidence state per real job."""
    workers = _dns_integer(ctx, "workers", 1, 32)
    def unique_jobs():
        seen = set()
        for job in jobs:
            if job not in seen:
                seen.add(job)
                yield job
    # Small adapter test doubles do not own a durable store. The real execution
    # path always uses independent contexts, including a one-worker execution.
    if not hasattr(ctx.workbench, "store"):
        return [_query_observation(ctx, *job, gate) for job in unique_jobs()]
    from .workbench_tools import ExecutionContext

    def query(job):
        child = ExecutionContext(ctx.workbench, ctx.run, ctx.step)
        record = _query_observation(child, *job, gate)
        return record, child.records

    iterator = iter(enumerate(unique_jobs()))
    active, completed = {}, {}
    exhausted = False
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="asm-dns") as executor:
        try:
            while active or not exhausted:
                ctx.check_control()
                while len(active) < workers and not exhausted:
                    try:
                        index, job = next(iterator)
                    except StopIteration:
                        exhausted = True
                        break
                    ctx.require(job[0])
                    active[executor.submit(query, job)] = index
                done, _ = wait(active, timeout=0.1, return_when=FIRST_COMPLETED)
                for future in sorted(done, key=lambda value: active[value]):
                    index = active.pop(future)
                    record, evidence = future.result()
                    completed[index] = record
                    ctx.records.extend(evidence)
        except BaseException:
            for future in active:
                future.cancel()
            raise
    return [completed[index] for index in sorted(completed)]


def dns_recursive(ctx):
    if _tool(ctx) not in {"dnspython", "dig_probe", "dnsx"}:
        return _result("blocked", "dns_tool_not_supported")
    domain = normalize_host(ctx.target)
    try:
        ipaddress.ip_address(domain)
        return _result("skipped", "dns_forward_observation_requires_domain")
    except ValueError:
        pass
    record_types = ctx.params.get("record_types", list(RTYPES))
    if not isinstance(record_types, list) or not record_types or any(rtype not in RTYPES for rtype in record_types):
        return _result("blocked", "unsupported_dns_record_type")
    record_types = list(dict.fromkeys(record_types))
    _dns_integer(ctx, "workers", 1, 32)
    maximum = _dns_integer(ctx, "max_cname_hops", 16, 32, minimum=0)
    resolvers = list(dict.fromkeys(_resolvers(ctx)))
    gate = _DNSGate(ctx)
    ctx.require(domain)
    records, assets, pending, seen = [], [], [(domain, 0, [])], set()
    while pending:
        current, pending = pending, []
        jobs, depths = [], {}
        for name, hop, basis in current:
            if name in seen:
                continue
            seen.add(name)
            if hop > maximum:
                records.append({"category": "dns_coverage_gaps", "domain": name, "reason": "max_cname_hops_exhausted", "knowledge": "candidate", "depth": hop, "evidence_ids": basis})
                continue
            ctx.check_control()
            try:
                ctx.require(name)
            except PolicyDenied as exc:
                if "outside_function_scope" not in str(exc) and "outside_scope" not in str(exc):
                    raise
                records.append({"category": "dns_scope_gaps", "domain": name, "reason": "cname_outside_function_scope", "knowledge": "candidate", "evidence_ids": basis})
                assets.append({"name": name, "domain": name, "asset_type": "domain_candidate", "lead_category": "dns_cname",
                               "verification_status": "candidate_only", "attribution_status": "unconfirmed", "knowledge": "candidate",
                               "source": _tool(ctx), "reason": "cname_outside_function_scope", "evidence_ids": basis})
                continue
            depths[name] = hop
            jobs.extend((name, rtype, resolver) for resolver in resolvers for rtype in record_types)
        batch = _dns_batch(ctx, jobs, gate)
        records.extend(batch)
        for record in batch:
            name = record["domain"]
            for item in record["answers"]:
                if not item["accepted"]:
                    continue
                if item["rtype"] in {"A", "AAAA"}:
                    assets.append({"host": name, "domain": name, "ip": item["value"], "port": 0, "source": _tool(ctx),
                                   "verification_status": "dns_observed", "attribution_status": "unconfirmed", "evidence_ids": record["evidence_ids"]})
                elif item["rtype"] == "CNAME" and item["value"] not in seen:
                    pending.append((item["value"], depths[name] + 1, record["evidence_ids"]))
    errors = [row for row in records if row.get("status") not in {None, "NOERROR", "NXDOMAIN"}]
    for rtype in record_types:
        observed = {str(row["resolver"]): sorted({item["value"] for item in row.get("answers", []) if item["rtype"] == rtype and item["accepted"]})
                    for row in records if row.get("domain") == domain and row.get("query_type") == rtype}
        if len(observed) > 1 and len({tuple(values) for values in observed.values()}) > 1:
            records.append({"category": "dns_comparison", "domain": domain, "rtype": rtype, "by_resolver": observed,
                            "knowledge": "inference", "classification": "multi_upstream_difference", "interpretation": "possible_cdn_geo_or_upstream_cache"})
    return _result("partial" if errors else "completed", "resolver_errors" if errors else "", assets, records)


def _dictionary(ctx):
    maximum = _dns_integer(ctx, "max_candidates_per_root", 1000, 100000)
    value = ctx.params.get("dictionary", "built_in_basic")
    checkpoint = None
    if isinstance(value, str) and value != "built_in_basic" and hasattr(ctx.workbench, "store"):
        checkpoint = Path(ctx.run["directory"]) / "checkpoints" / ("dns-dictionary-" + ctx.step["id"] + ".json")
        if checkpoint.is_file():
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            labels = saved.get("labels", [])
            checksum = hashlib.sha256(json.dumps(labels, separators=(",", ":")).encode()).hexdigest()
            if saved.get("source") != value or saved.get("maximum") != maximum or saved.get("labels_sha256") != checksum:
                raise ValueError("Saved DNS dictionary checkpoint is inconsistent")
            return labels
    if isinstance(value, list):
        labels = value
    elif value == "built_in_basic":
        labels = list(BASIC_LABELS)
    elif isinstance(value, str) and value.startswith("seclists:"):
        from .external_tools import frozen_dictionary
        labels = frozen_dictionary(ctx, value, BASIC_LABELS)
        raw = "\n".join(labels).encode("utf-8")
    elif isinstance(value, str) and value:
        path = (ctx.workbench.root / value).resolve()
        if not path.is_relative_to(ctx.workbench.root.resolve()) or path.name == ".env" or path.name.startswith(".env.") or not path.is_file():
            raise ValueError("Dictionary must be an existing project file")
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("DNS dictionary exceeds the 10 MiB input limit")
        raw = path.read_bytes()
        labels = raw.decode("utf-8").splitlines()
    else:
        return []
    if any(not isinstance(label, str) or not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label) for label in labels):
        raise ValueError("Dictionary entries must be single DNS labels")
    labels = list(dict.fromkeys(label.lower() for label in labels))[:maximum]
    if checkpoint is not None:
        from .run_store import atomic_json
        atomic_json(checkpoint, {"source": value, "source_sha256": hashlib.sha256(raw).hexdigest(), "maximum": maximum,
                                 "labels": labels, "labels_sha256": hashlib.sha256(json.dumps(labels, separators=(",", ":")).encode()).hexdigest()})
    return labels


def dns_enum(ctx):
    if _tool(ctx) != "dnspython_dictionary":
        return _result("blocked", "selected_dns_dictionary_tool_not_integrated")
    labels = _dictionary(ctx)
    if not labels:
        return _result("skipped", "empty_dns_dictionary")
    root = normalize_host(ctx.target)
    _dns_integer(ctx, "workers", 1, 32)
    baseline_count = _dns_integer(ctx, "wildcard_baseline_queries", 2, 8)
    resolvers = list(dict.fromkeys(_resolvers(ctx)))
    gate = _DNSGate(ctx)
    ctx.require(root)
    records, assets, baselines = [], [], {}
    baseline_jobs = []
    for resolver in resolvers:
        for index in range(baseline_count):
            identity = [ctx.run.get("run_id", ""), ctx.step["id"], root, resolver, index]
            name = "asm-" + hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()[:16] + "." + root
            ctx.check_control()
            try:
                ctx.require(name)
            except PolicyDenied as exc:
                if "outside_function_scope" not in str(exc) and "outside_scope" not in str(exc):
                    raise
                return _result("skipped", "dns_enum_child_names_not_in_function_scope", records=records)
            baseline_jobs.append((name, "A", resolver))
    for record in _dns_batch(ctx, baseline_jobs, gate):
        record["purpose"] = "wildcard_baseline"
        records.append(record)
        baselines.setdefault(record["resolver"], set()).update(item["value"] for item in record["answers"] if item["accepted"])
    jobs = ((label + "." + root, "A", resolver) for label in labels for resolver in resolvers)
    for record in _dns_batch(ctx, jobs, gate):
        values = {item["value"] for item in record["answers"] if item["accepted"]}
        wildcard = bool(values and baselines[record["resolver"]] and values == baselines[record["resolver"]])
        record.update({"purpose": "dictionary_candidate", "wildcard_match": wildcard})
        records.append(record)
        for item in record["answers"]:
            if item["accepted"] and item["rtype"] in {"A", "AAAA"}:
                assets.append({"host": record["domain"], "domain": record["domain"], "ip": item["value"], "source": _tool(ctx),
                               "verification_status": "candidate_only" if wildcard else "dns_observed",
                               "attribution_status": "unconfirmed", "wildcard_match": wildcard, "evidence_ids": record["evidence_ids"]})
    errors = [record for record in records if record.get("status") not in {"NOERROR", "NXDOMAIN"}]
    return _result("partial" if errors else "completed", "resolver_errors" if errors else "", assets, records)


def _tls_connection_target(ctx):
    from urllib.parse import urlsplit
    parsed = urlsplit(ctx.target if "://" in ctx.target else "https://" + ctx.target)
    if parsed.scheme != "https":
        return None
    host = normalize_host(parsed.hostname or "")
    port = parsed.port or int(ctx.params.get("port", 443))
    if host == "localhost":
        address = "127.0.0.1"
    else:
        try:
            address = str(ipaddress.ip_address(host))
        except ValueError:
            address = ctx.params.get("connect_ip", "")
            if not address:
                return None
            address = str(ipaddress.ip_address(address))
            ctx.require(address)
    return host, address, port


def _tls_handshake(ctx, host, address, port, version=None):
    ctx.require(ctx.target)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    if version is not None:
        context.minimum_version = context.maximum_version = version
    timeout = float(ctx.params.get("timeout_seconds", 10))
    with socket.create_connection((address, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as connection:
            certificate = connection.getpeercert(binary_form=True)
            pem = ssl.DER_cert_to_PEM_cert(certificate)
            path = Path(ctx.output_directory) / ("leaf-" + uuid.uuid4().hex + ".pem")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pem, encoding="ascii")
            cert = ssl._ssl._test_decode_cert(str(path))
            chain = [pem]
            getter = getattr(connection._sslobj, "get_unverified_chain", None)
            if ctx.params.get("collect_certificate_chain", True) and getter:
                chain = [item.public_bytes() for item in getter()]
            return {"host": host, "connect_ip": address, "port": port, "protocol": connection.version(),
                    "cipher": connection.cipher(), "certificate": cert, "certificate_pem": pem,
                    "certificate_sha256": hashlib.sha256(certificate).hexdigest(),
                    "certificate_chain_pem": chain, "chain_coverage": "peer_chain" if getter else "leaf_only_runtime_limit",
                    "trust_validation": "not_performed", "certificate_path": str(path)}


def tls_inspect(ctx):
    if _tool(ctx) != "native_tls":
        return _result("blocked", "selected_tls_tool_not_integrated")
    target = _tls_connection_target(ctx)
    if target is None:
        return _result("skipped", "https_url_and_approved_connection_address_required")
    host, address, port = target
    raw = ctx.call(_tool(ctx), {"target": ctx.target, "connect_ip": address, "port": port},
                   lambda: _tls_handshake(ctx, host, address, port))
    records = [{"category": "tls_observations", "knowledge": "observation", **raw, "evidence_ids": _evidence(ctx)}]
    evidence_ids = list(_evidence(ctx))
    if ctx.params.get("collect_protocols", True):
        for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            ctx.require(ctx.target)

            def version_probe():
                try:
                    observation = _tls_handshake(ctx, host, address, port, version)
                    return {"requested_protocol": version.name, "negotiated_protocol": observation["protocol"], "supported": True}
                except (ssl.SSLError, OSError) as exc:
                    return {"requested_protocol": version.name, "supported": None, "negotiation_status": "failed",
                            "error": type(exc).__name__}

            observation = ctx.call(_tool(ctx), {"target": ctx.target, "protocol": version.name}, version_probe)
            records.append({"category": "tls_protocols", "knowledge": "observation", **observation, "evidence_ids": _evidence(ctx)})
            evidence_ids.extend(_evidence(ctx))
    return _result(assets=[{"host": host, "ip": address, "port": port, "proto": "tcp", "service": "https",
                            "source": _tool(ctx), "verification_status": "observed", "attribution_status": "unconfirmed",
                            "certificate_sha256": raw["certificate_sha256"], "tls_protocol": raw["protocol"], "evidence_ids": evidence_ids}], records=records)


def adapters():
    return {"tcp_scan": port_service, "udp_scan": port_service, "service_probe": port_service,
            "deep_service_probe": port_service, "dns_recursive": dns_recursive, "dns_enum": dns_enum,
            "tls_inspect": tls_inspect}
