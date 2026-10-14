"""Live evidence for the trusted DNS path: encrypted resolvers vs plaintext/host resolution.

Read-only environment verification. Only the public IANA example domain is queried
against public resolvers; no configured investigation target is contacted, and the
stage ingestion runs entirely in memory.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import dns.resolver

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from asm.db import Database  # noqa: E402
from asm.models import Domain  # noqa: E402
from asm.scope import Scope  # noqa: E402
from asm.stages.s5_dns_cdn import ingest  # noqa: E402
from asm.utils.dns import DEFAULT_RESOLVERS, DOH_ENDPOINTS, DNSSettings, doh_query, windows_query  # noqa: E402

QUERY_TYPES = ("A", "AAAA")


def host_resolution(domain):
    """What the machine's own resolver configuration currently answers."""
    configured = dns.resolver.Resolver(configure=True)
    entry = {"nameservers": list(configured.nameservers), "answers": {}, "errors": {}}
    for rtype in QUERY_TYPES:
        try:
            reply = configured.resolve(domain + ".", rtype, search=False, raise_on_no_answer=False)
            entry["answers"][rtype] = sorted(str(value) for value in reply)
        except Exception as exc:  # noqa: BLE001 - evidence records the failure verbatim
            entry["errors"][rtype] = type(exc).__name__
    return entry


def stage_case(domain, observations, settings):
    """Run the real Stage 5 ingestion in memory and return its evidence."""
    written = {}
    with Database(":memory:") as db:
        db.domain(Domain(domain, sources="evidence"))
        scope = Scope({"authorization": True, "targets": {"roots": [domain]}}, passive_only=True)
        def note(kind, target, payload):
            db.finding({"kind": kind, "url": target, "evidence": payload, "status": "review"})
        ctx = SimpleNamespace(db=db, scope=scope, config={}, passive_only=True, target_local=False,
                              note=note, write=lambda name, value: written.__setitem__(name, value))
        result = ingest(ctx, observations, settings)
        fact = db.get_fact("dns:" + domain)
        return {"status": result.status, "notes": result.notes, "selected": fact["selected"],
                "doh_verification": fact["doh_verification"], "rejected": fact["rejected"],
                "findings": sorted({row["kind"] for row in db.rows("SELECT kind FROM findings")}),
                "dns_records": [row["value"] for row in db.rows(
                    "SELECT value FROM dns_records WHERE rtype IN ('A','AAAA') ORDER BY value")]}


def run(domain, resolvers, endpoints, timeout):
    evidence = {"domain": domain, "utc": datetime.now(timezone.utc).isoformat(),
                "python": sys.version.split()[0],
                "doh_endpoints": list(endpoints), "plaintext_resolvers": list(resolvers),
                "host_resolution": host_resolution(domain), "plaintext": {}, "encrypted": {}}
    observations = []
    for resolver in resolvers:
        for rtype in QUERY_TYPES:
            observation = windows_query(domain, rtype, resolver, timeout)
            evidence["plaintext"].setdefault(resolver, {})[rtype] = {
                "status": observation["status"], "error": observation["error"],
                "answers": [answer["value"] for answer in observation["answers"]]}
            observations.append(observation)
    for endpoint in endpoints:
        for rtype in QUERY_TYPES:
            observation = doh_query(domain, rtype, endpoint, timeout)
            evidence["encrypted"].setdefault(endpoint, {})[rtype] = {
                "status": observation["status"], "error": observation["error"],
                "answers": [answer["value"] for answer in observation["answers"]]}
            observations.append(observation)

    settings = DNSSettings.from_config({"dns": {"resolvers": list(resolvers),
                                                "preferred_resolver": resolvers[0],
                                                "doh_resolvers": list(endpoints)}})
    evidence["stage"] = stage_case(domain, observations, settings)

    # Control: what the pipeline would have selected if it had trusted the host resolver.
    host_observations = [{"domain": domain, "resolver": "host", "source": "windows", "rtype": rtype,
                          "status": "NOERROR", "answers": [{"rtype": rtype, "value": value} for value
                          in evidence["host_resolution"]["answers"].get(rtype, [])]}
                         for rtype in QUERY_TYPES]
    evidence["stage_host_resolver_only"] = stage_case(domain, host_observations, DNSSettings())

    usable = evidence["stage"]["selected"]["A"] + evidence["stage"]["selected"]["AAAA"]
    evidence["conclusion"] = {
        "host_resolver_answers": evidence["host_resolution"]["answers"],
        "selected_for_scanning": usable,
        "encrypted_path_used": evidence["stage"]["doh_verification"]["selected_from"] == "doh",
        "encrypted_path_recovered_real_addresses": bool(usable) and all(
            not value.startswith("127.") and not value.startswith("198.18.") for value in usable),
        "hijacked_host_answers_rejected": not any(evidence["stage_host_resolver_only"]["selected"][rtype]
                                                  for rtype in QUERY_TYPES)}
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="example.com")
    parser.add_argument("--resolvers", nargs="*", default=list(DEFAULT_RESOLVERS))
    parser.add_argument("--doh", nargs="*", default=list(DOH_ENDPOINTS))
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    evidence = run(args.domain, args.resolvers, args.doh, args.timeout)
    payload = json.dumps(evidence, indent=2, ensure_ascii=False)
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(f"evidence: {output}")
    print(payload)


if __name__ == "__main__":
    main()