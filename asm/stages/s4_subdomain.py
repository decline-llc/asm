import concurrent.futures
import json
import secrets

import dns.resolver
import httpx

from ..models import Domain
from ..panel.fofa import Fofa
from ..panel.quake import Quake
from ..pipeline import StageResult
from ..scope import is_local, normalize_host
from ..utils.constants import DNS_PREFIXES


def resolve(domain, rtype="A", nameserver=None):
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 4
    if nameserver:
        resolver.nameservers = [nameserver]
    try:
        return [str(v).rstrip(".") for v in resolver.resolve(domain, rtype)]
    except dns.exception.DNSException:
        return []


def wildcard(root, resolver=resolve):
    samples = [set(resolver("asm-" + secrets.token_hex(4) + "." + root)) for _ in range(2)]
    return bool(samples[0] and samples[1] and samples[0] & samples[1])


def enumerate_dns(root, *, resolver=resolve, threads=60):
    if wildcard(root, resolver):
        return True, []
    candidates = [prefix + "." + root for prefix in DNS_PREFIXES]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(60, int(threads))) as executor:
        records = [(domain, answers) for domain, answers in zip(candidates, executor.map(resolver, candidates))
                   if answers]
    return False, records


def run(ctx):
    count, notes = 0, []
    collected = []
    def accept(domain, source):
        nonlocal count
        try:
            domain = normalize_host(domain.removeprefix("*."))
        except ValueError:
            return
        if not ctx.scope.contains(domain):
            return
        ctx.db.domain(Domain(domain, sources=source))
        collected.append({"domain": domain, "source": source})
        count += 1
    if ctx.dry_run:
        data = json.loads((ctx.profile.root / "tests/fixtures/subdomains.json").read_text(encoding="utf-8"))
        for item in data:
            accept(item["domain"], item["source"])
    else:
        for root in sorted(ctx.scope.roots):
            if is_local(root) or ctx.target_local:
                accept(root, "seed")
                continue
            try:
                handle = ctx.jobs.run("subfinder", ["-d", root, "-silent", "-duc", "-o", "{job}/subdomains.txt"],
                    stage="4", timeout=ctx.config.get("limits", {}).get("subfinder_timeout", 900),
                    idempotent=True)
                ctx.jobs.wait(handle)
                result_path = ctx.jobs.result_dir(handle) / "subdomains.txt"
                if handle.rc == 0 and result_path.exists():
                    for domain in result_path.read_text(encoding="utf-8").splitlines():
                        accept(domain, "subfinder")
            except RuntimeError as exc:
                notes.append("subfinder: " + str(exc))
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                for source, url, params in (
                    ("crt.sh", "https://crt.sh/", {"q": "%." + root, "output": "json"}),
                    ("hackertarget", "https://api.hackertarget.com/hostsearch/", {"q": root}),
                    ("wayback", "https://web.archive.org/cdx/search/cdx", {"url": "*." + root + "/*",
                         "output": "json", "collapse": "urlkey", "filter": "statuscode:200", "limit": 1000}),
                ):
                    try:
                        response = client.get(url, params=params)
                        response.raise_for_status()
                        if source == "crt.sh":
                            for cert in response.json():
                                for domain in cert.get("name_value", "").splitlines():
                                    accept(domain, source)
                        elif source == "hackertarget":
                            for line in response.text.splitlines():
                                accept(line.split(",")[0], source)
                        else:
                            from urllib.parse import urlsplit
                            entries = response.json()
                            if entries:
                                index = entries[0].index("original")
                                for row in entries[1:]:
                                    accept(urlsplit(row[index]).hostname or "", source)
                    except (ValueError, httpx.HTTPError) as exc:
                        notes.append(f"{source}: {type(exc).__name__}")
            import os
            for engine, key, query in ((Quake, "QUAKE_TOKEN", f'domain:"{root}"'),
                                       (Fofa, "FOFA_KEY", Fofa.domain_query(root))):
                if not os.getenv(key):
                    continue
                panel = engine(ctx.db, ctx.config)
                try:
                    for asset in panel.search(query):
                        panel.ingest([asset], query, exact=True)
                        accept(asset.host, panel.name)
                finally:
                    panel.close()
            if ctx.scope.authorized and not ctx.passive_only:
                wild, records = enumerate_dns(root, threads=ctx.config.get("rates", {}).get("dns_threads", 60))
                ctx.db.domain(Domain(root, wildcard=int(wild), sources="dns"))
                for domain, _ in records:
                    accept(domain, "dns_brute")
    ctx.write("subdomains.json", collected)
    return StageResult("partial" if notes else "completed", count, notes)
