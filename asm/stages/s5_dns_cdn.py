import concurrent.futures
import hashlib
import ipaddress
import json
from pathlib import Path

import httpx

from ..models import utcnow
from ..pipeline import StageResult
from ..scope import ScopeError
from ..utils.constants import TAKEOVER_FINGERPRINTS
from ..utils.dns import DNSSettings, RTYPES, dns_name, record_value, windows_query
from ..utils.http import TargetHTTP
from .s4_subdomain import resolve


def cdn_fingerprint(cnames=(), headers=None):
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    markers = ("gccdn.net", "cloudfront.net", "cloudflare.net", "akamaiedge.net", "alicdn.com", "cdn.dnsv1.com")
    return (any(any(name == suffix or name.endswith("." + suffix) for suffix in markers) for name in cnames)
            or headers.get("server", "").upper() == "PWS"
            or headers.get("via", "").startswith("PS-") or any(k.startswith("x-px") for k in headers))


def scan_ports(cdn, default="1-65535"):
    return "3000-9200" if cdn else default


def corrected_answers(by_resolver, preferred="114.114.114.114", *, reject_fake_ip=True):
    clean = {}
    for resolver, values in by_resolver.items():
        clean[resolver] = []
        for value in values:
            try:
                ip = ipaddress.ip_address(value)
                clean[resolver].append(record_value("A" if ip.version == 4 else "AAAA", value,
                                                     reject_fake_ip=reject_fake_ip))
            except ValueError:
                continue
    return sorted(set(clean.get(preferred) or [ip for values in clean.values() for ip in values]))


def takeover_provider(cname, status, body):
    if status == 403:
        return None
    for provider, suffix, code, text in TAKEOVER_FINGERPRINTS:
        if (cname == suffix or cname.endswith("." + suffix)) and status == code and text.lower() in body.lower():
            return provider
    return None


def cname_chain(domain, resolver=resolve, *, max_hops=16):
    chain, seen = [], {domain}
    for _ in range(max_hops):
        records = resolver(domain, "CNAME")
        if not records:
            return chain
        domain = records[0].rstrip(".").lower()
        if domain in seen:
            return chain
        chain.append(domain)
        seen.add(domain)
    return chain


def parse_dnsx(path, resolver, allowed):
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            domain = dns_name(row.get("host", ""))
        except (ValueError, AttributeError):
            continue
        if domain not in allowed:
            continue
        answers = []
        for rtype in RTYPES:
            values = row.get(rtype.lower(), [])
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            answers.extend({"name": domain, "rtype": rtype, "value": str(value)} for value in values)
        yield {"domain": domain, "rtype": "BATCH", "resolver": resolver, "source": "dnsx",
               "status": row.get("status_code", "NOERROR" if answers else "NOANSWER"),
               "answers": answers, "error": ""}


def collect_wsl(ctx, domains, settings):
    observations, notes, pending = [], [], []
    input_data = {"domains": domains, "resolvers": list(settings.resolvers), "timeout": settings.timeout,
                  "workers": settings.workers, "max_hops": settings.max_hops}
    inputs = {"dns_probe.py": (ctx.profile.root / "tools/dns_probe.py").read_text(encoding="utf-8"),
              "dns_support.py": (Path(__file__).parents[1] / "utils/dns.py").read_text(encoding="utf-8"),
              "targets.json": json.dumps(input_data)}
    timeout = ctx.config.get("limits", {}).get("dns_timeout", 900)
    try:
        handle = ctx.jobs.run("python3", ["{job}/dns_probe.py", "--input", "{job}/targets.json",
            "--output", "{job}/dig.jsonl"], stage="5", timeout=timeout, background=True, inputs=inputs)
        pending.append(("dig", "", handle, "dig.jsonl"))
        if settings.dnsx:
            for resolver in settings.resolvers:
                handle = ctx.jobs.run("dnsx", ["-l", "{job}/domains.txt", "-a", "-aaaa", "-mx", "-ns",
                    "-cname", "-j", "-silent", "-nc", "-duc", "-retry", "1", "-t", str(settings.workers),
                    "-rl", "60", "-timeout", f"{settings.timeout}s", "-r", resolver,
                    "-o", "{job}/dnsx.jsonl"], stage="5", timeout=timeout, background=True,
                    inputs={"domains.txt": "\n".join(domains) + "\n"})
                pending.append(("dnsx", resolver, handle, "dnsx.jsonl"))
    except RuntimeError as exc:
        notes.append(f"DNS tool submission failed: {exc}")
    for tool, resolver, handle, filename in pending:
        ctx.jobs.wait(handle)
        if handle.rc != 0:
            notes.append(f"{tool} failed, resolver={resolver}, rc={handle.rc}")
            continue
        path = ctx.jobs.result_dir(handle) / filename
        if not path.is_file():
            notes.append(f"{tool} did not produce {filename}")
            continue
        if tool == "dnsx":
            observations.extend(parse_dnsx(path, resolver, set(domains)))
        else:
            observations.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return observations, notes


def probe_takeover(ctx, domain, terminal):
    client = TargetHTTP(ctx.scope, timeout=ctx.config.get("limits", {}).get("http_timeout", 15))
    try:
        for scheme in ("https", "http"):
            try:
                reply = client.get(f"{scheme}://{domain}/")
            except (httpx.HTTPError, ScopeError):
                continue
            provider = takeover_provider(terminal, reply.status, reply.text)
            if provider:
                marker = next(text for name, _, _, text in TAKEOVER_FINGERPRINTS if name == provider)
                ctx.db.upsert("takeovers", {"domain": domain, "kind": "CNAME", "provider": provider,
                    "evidence": json.dumps({"terminal": terminal, "url": reply.url, "status": reply.status,
                        "matched_text": marker, "body_sha256": hashlib.sha256(reply.text.encode()).hexdigest()}),
                    "status": "review"},
                    ("domain", "kind", "provider"))
                return
    finally:
        client.close()


def ingest(ctx, observations, settings, notes=None):
    notes, records, evidence = list(notes or []), [], {}
    allowed = {row["domain"] for row in ctx.db.rows("SELECT domain FROM domains") if ctx.scope.contains(row["domain"])}
    for domain in allowed:
        evidence[domain] = {"by_source": {}, "responses": {}, "chains": {}, "rejected": [], "statuses": {}}
    for observation in observations:
        domain = observation.get("origin", observation.get("domain"))
        if domain not in evidence:
            continue
        source, resolver = observation.get("source", "fixture"), observation.get("resolver", "fixture")
        item = evidence[domain]
        if observation.get("kind") == "cname_chain":
            item["chains"][resolver] = {key: observation[key] for key in ("chain", "terminal", "status")}
            continue
        if observation.get("origin"):
            continue  # Terminal names are evidence, never added as new scoped domains.
        query_type, status = observation.get("rtype", "BATCH"), observation.get("status", "ERROR")
        item["statuses"][f"{source}@{resolver}:{query_type}"] = status
        responses = item["responses"].setdefault(resolver, {}).setdefault(source, {})
        for rtype in RTYPES if query_type == "BATCH" else (query_type,):
            responses[rtype] = status
        if status not in ("NOERROR", "NXDOMAIN", "NOANSWER"):
            notes.append(f"DNS {source}/{resolver} {domain}: {status}")
            continue
        by_type = item["by_source"].setdefault(resolver, {}).setdefault(source, {})
        for answer in observation.get("answers", []):
            rtype = answer.get("rtype")
            try:
                value = record_value(rtype, answer.get("value", ""), reject_fake_ip=settings.reject_fake_ip)
            except (ValueError, TypeError):
                item["rejected"].append({"source": source, "resolver": resolver, **answer})
                ctx.note("dns_unusable_answer", domain, json.dumps({"resolver": resolver, **answer}))
                continue
            by_type.setdefault(rtype, set()).add(value)
            records.append({"domain": domain, "rtype": rtype, "value": value,
                            "resolver": f"{source}@{resolver}", "ts": utcnow()})
    for domain, item in evidence.items():
        if not item["statuses"]:
            notes.append(f"No DNS observations for {domain}")
        item["by_source"] = {resolver: {source: {rtype: sorted(values) for rtype, values in types.items()}
                            for source, types in sources.items()} for resolver, sources in item["by_source"].items()}
        item["by_resolver"], item["selected_sources"], item["source_differences"] = {}, {}, {}
        for resolver, responses in item["responses"].items():
            types, chosen, differences = {}, {}, {}
            for rtype in RTYPES:
                sources = {source: item["by_source"].get(resolver, {}).get(source, {}).get(rtype, [])
                           for source, statuses in responses.items()
                           if statuses.get(rtype) in ("NOERROR", "NXDOMAIN", "NOANSWER")}
                source = next((source for source in ("dig", "windows", "dnsx", "fixture") if source in sources), None)
                if source:
                    types[rtype], chosen[rtype] = sources[source], source
                differences[rtype] = len({tuple(values) for values in sources.values()}) > 1
            item["by_resolver"][resolver], item["selected_sources"][resolver] = types, chosen
            item["source_differences"][resolver] = differences
        preferred_responses = item["responses"].get(settings.preferred, {})
        comparable = [rtype for rtype in RTYPES if all(preferred_responses.get(source, {}).get(rtype)
                      in ("NOERROR", "NXDOMAIN", "NOANSWER") for source in ("dig", "windows"))]
        preferred_sources = item["by_source"].get(settings.preferred, {})
        mismatches = [rtype for rtype in comparable if preferred_sources.get("dig", {}).get(rtype, [])
                      != preferred_sources.get("windows", {}).get(rtype, [])]
        item["windows_verification"] = {"resolver": settings.preferred, "compared": comparable,
            "differences": mismatches, "status": "disabled" if not settings.windows_verify else
            "mismatch" if mismatches else "match" if len(comparable) == len(RTYPES) else "unavailable"}
        if mismatches:
            ctx.note("dns_verification_mismatch", domain, json.dumps(item["windows_verification"]))
            notes.append(f"Windows/dig DNS verification differs for {domain}: {','.join(mismatches)}")
        selected = {rtype: corrected_answers({resolver: values.get(rtype, []) for resolver, values in
                    item["by_resolver"].items()}, settings.preferred, reject_fake_ip=settings.reject_fake_ip)
                    for rtype in ("A", "AAAA")}
        differences = {rtype: len({tuple(values.get(rtype, [])) for values in item["by_resolver"].values()}) > 1
                       for rtype in ("A", "AAAA")}
        item.update(selected=selected, differences=differences, preferred_resolver=settings.preferred)
        if not selected["A"] and not selected["AAAA"] and any(
                entry.get("rtype") in ("A", "AAAA") for entry in item["rejected"]):
            notes.append(f"Only unusable DNS addresses for {domain}")
        cnames = [v for types in item["by_resolver"].values() for v in types.get("CNAME", [])]
        cnames.extend(v for chain in item["chains"].values() for v in chain["chain"])
        cdn = cdn_fingerprint(cnames)
        ctx.db.fact("cdn:" + domain, cdn)
        ctx.db.fact("dns:" + domain, item)
        ctx.db.execute("UPDATE assets SET cdn=? WHERE host=?", (int(cdn), domain))
        ips = selected["A"] + selected["AAAA"]
        tag = "有解析未验证" if not ips else "云部署" if cdn else "内网" if all(
            ipaddress.ip_address(ip).is_private for ip in ips) else "公开"
        ctx.db.execute("UPDATE domains SET tag5=? WHERE domain=?", (tag, domain))
        for resolver, chain in item["chains"].items():
            if chain["status"] in ("loop", "max_hops", "error", "invalid"):
                ctx.note("cname_chain_incomplete", domain, json.dumps({"resolver": resolver, **chain}))
                notes.append(f"CNAME chain {chain['status']} for {domain} via {resolver}")
            elif chain["status"] == "nxdomain" and chain["chain"]:
                ctx.note("dangling_cname_candidate", domain, json.dumps({"resolver": resolver, **chain}))
        if settings.takeover_probe and ctx.scope.authorized and not ctx.passive_only:
            for terminal in set(chain["terminal"] for chain in item["chains"].values()
                                if chain["chain"] and chain["status"] in ("complete", "nxdomain")):
                probe_takeover(ctx, domain, terminal)
    for domain, item in evidence.items():
        if item["statuses"]:
            ctx.db.execute("DELETE FROM dns_records WHERE domain=?", (domain,))
    for record in records:
        ctx.db.upsert("dns_records", record, ("domain", "rtype", "value", "resolver"))
    ctx.write("dns.json", records)
    ctx.write("dns-evidence.json", evidence)
    ctx.write("dns-observations.json", observations)
    return StageResult("partial" if notes else "completed", len(records), sorted(set(notes)))


def run(ctx):
    settings = DNSSettings.from_config(ctx.config)
    domains = [row["domain"] for row in ctx.db.rows("SELECT domain FROM domains") if ctx.scope.contains(row["domain"])]
    if not domains:
        ctx.write("dns.json", [])
        return StageResult()
    observations, notes = [], []
    if ctx.dry_run or ctx.target_local:
        fixtures = json.loads((ctx.profile.root / "tests/fixtures/dns.json").read_text(encoding="utf-8")) if ctx.dry_run else {}
        for domain in domains:
            answers = {"A": ["127.0.0.1"]} if ctx.target_local and domain == "localhost" else fixtures.get(domain, {})
            observations.append({"domain": domain, "resolver": "fixture", "source": "fixture", "status": "NOERROR",
                "answers": [{"name": domain, "rtype": rtype, "value": value} for rtype, values in answers.items()
                            for value in values]})
    else:
        observations, notes = collect_wsl(ctx, domains, settings)
        if settings.windows_verify:
            with concurrent.futures.ThreadPoolExecutor(max_workers=settings.workers) as executor:
                futures = [executor.submit(windows_query, domain, rtype, settings.preferred, settings.timeout)
                           for domain in domains for rtype in RTYPES]
                observations.extend(future.result() for future in futures)
    return ingest(ctx, observations, settings, notes)
