import hashlib
import ipaddress

from ..models import Company, Domain
from ..pipeline import StageResult
from ..scope import normalize_host


def classify_seed(value):
    value = value.strip()
    try:
        return "ip", str(ipaddress.ip_address(value))
    except ValueError:
        pass
    try:
        if "." in value or "://" in value or value == "localhost":
            return "domain", normalize_host(value)
    except ValueError:
        pass
    return "company", value


def run(ctx):
    targets = ctx.config.get("targets", {})
    company = targets.get("company", "")
    cid = hashlib.sha256(company.encode()).hexdigest()[:16] if company else None
    if company:
        ctx.db.upsert("companies", Company(cid, company, brand=",".join(targets.get("brands", []))),
                      ("cid",), merge=True)
    seeds = [{"kind": "company", "value": company}] if company else []
    for root in targets.get("roots", []):
        domain = normalize_host(root.removeprefix("*."))
        ctx.db.domain(Domain(domain, cid=cid, sources="seed"))
        seeds.append({"kind": "domain", "value": domain})
    for ip in targets.get("ip_cidrs", []):
        seeds.append({"kind": "network", "value": str(ipaddress.ip_network(ip, strict=False))})
    for value in targets.get("seeds", []):
        kind, value = classify_seed(value)
        seeds.append({"kind": kind, "value": value})
        if kind == "domain":
            ctx.db.domain(Domain(value, cid=cid, sources="seed"))
        elif kind == "company":
            ident = hashlib.sha256(value.encode()).hexdigest()[:16]
            ctx.db.upsert("companies", Company(ident, value), ("cid",), merge=True)
    ctx.db.fact("seed_brands", targets.get("brands", []))
    ctx.db.fact("seed_persons", targets.get("extra_persons", []))
    ctx.write("seed.json", seeds)
    return StageResult(count=len(seeds))
