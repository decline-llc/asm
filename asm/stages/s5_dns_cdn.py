import ipaddress
import json

from ..models import utcnow
from ..pipeline import StageResult
from ..utils.constants import TAKEOVER_FINGERPRINTS
from .s4_subdomain import resolve


def cdn_fingerprint(cnames=(), headers=None):
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    markers = ("gccdn.net", "cloudfront.net", "cloudflare.net", "akamaiedge.net", "alicdn.com", "cdn.dnsv1.com")
    return (any(any(name == suffix or name.endswith("." + suffix) for suffix in markers) for name in cnames)
            or headers.get("server", "").upper() == "PWS"
            or headers.get("via", "").startswith("PS-") or any(k.startswith("x-px") for k in headers))


def scan_ports(cdn, default="1-65535"):
    return "3000-9200" if cdn else default


def corrected_answers(by_resolver):
    domestic = [ip for ip in by_resolver.get("114.114.114.114", []) if ip != "0.0.0.0"]
    return sorted(set(domestic or [ip for values in by_resolver.values() for ip in values if ip != "0.0.0.0"]))


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


def run(ctx):
    rows = ctx.db.rows("SELECT domain FROM domains")
    records = []
    fixtures = json.loads((ctx.profile.root / "tests/fixtures/dns.json").read_text(encoding="utf-8")) if ctx.dry_run else {}
    for row in rows:
        domain = row["domain"]
        if ctx.target_local:
            answers = {"A": ["127.0.0.1"]} if domain == "localhost" else {}
        elif ctx.dry_run:
            answers = fixtures.get(domain, {})
        else:
            answers = {rtype: resolve(domain, rtype) for rtype in ("A", "AAAA", "MX", "NS", "CNAME")}
        for rtype, values in answers.items():
            for value in values:
                record = {"domain": domain, "rtype": rtype, "value": value,
                          "resolver": "fixture" if ctx.dry_run else "system", "ts": utcnow()}
                ctx.db.upsert("dns_records", record, ("domain", "rtype", "value", "resolver"))
                records.append(record)
        cdn = cdn_fingerprint(answers.get("CNAME", []))
        ctx.db.fact("cdn:" + domain, cdn)
        for value in answers.get("A", []) + answers.get("AAAA", []):
            try:
                ip = ipaddress.ip_address(value)
                tag = "内网" if ip.is_private else "云部署" if cdn else "公开"
                ctx.db.execute("UPDATE domains SET tag5=? WHERE domain=?", (tag, domain))
            except ValueError:
                pass
    ctx.write("dns.json", records)
    return StageResult(count=len(records))
