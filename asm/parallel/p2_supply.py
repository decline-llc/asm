import os

from ..panel.base import RateLimiter
from ..panel.fofa import Fofa
from ..pipeline import StageResult


def run(ctx):
    config = ctx.config.get("supply_chain", {})
    dimensions = {
        "domains": [r["domain"] for r in ctx.db.rows("SELECT domain FROM domains")],
        "systems": ctx.db.rows("SELECT system_name,vendor,version FROM systems"),
        "people": ctx.db.rows("SELECT name,role,cid FROM people"),
        "vendors": config.get("vendor_list", []),
        "tenders": [r["k"] for r in ctx.db.rows("SELECT k FROM facts WHERE k LIKE 'tender:%'")],
        "high_value": [a["host"] for a in ctx.db.rows("SELECT host FROM assets")
                       if any(k in a["host"] for k in ("vpn", "admin", "sso"))],
    }
    ctx.write("supply-chain.json", dimensions)
    count = 0
    if os.getenv("FOFA_KEY") and not ctx.dry_run:
        limiter = RateLimiter(ctx.db, "cert_domain", daily=min(8, config.get("cert_domain_limit", 8)))
        panel = Fofa(ctx.db, ctx.config)
        try:
            for domain in dimensions["domains"]:
                limiter.acquire()
                query = Fofa.cert_query(domain)
                # Stream observations so interruption never loses an entire query result.
                for asset in panel.search(query):
                    count += panel.ingest([asset], query, exact=True)
        finally:
            panel.close()
    for vendor in dimensions["vendors"]:
        ctx.note("supply_research", str(vendor), "Review public customer cases, tender notices and operator-supplied evidence")
    ctx.db.fact("supply_dimensions", dimensions)
    return StageResult(count=count, notes=["A: certificate/domain evidence; B: vendor/tender review cards"])
