import os

from .base import MappingEngine, asset_from, joined


class Quake(MappingEngine):
    name = "quake"

    @staticmethod
    def parse(payload):
        for item in payload.get("data", []):
            service = item.get("service", {})
            http = service.get("http", {}) or {}
            domains = item.get("domain") or http.get("host") or item.get("hostname") or item.get("ip")
            if isinstance(domains, list):
                domains = domains[0] if domains else item.get("ip")
            asset = asset_from(domains, item.get("ip", ""), item.get("port", 443),
                service=service.get("name", ""), title=http.get("title", ""),
                product=joined(item.get("components", [])), version=service.get("version", ""),
                tech=joined(http.get("server", "")))
            if asset:
                yield asset

    def search(self, query, *, size=100, start=0):
        payload = self.request("POST", "https://quake.360.net/api/v3/search/quake_service",
                              headers={"X-QuakeToken": os.environ["QUAKE_TOKEN"]},
                              json={"query": query, "start": start, "size": min(100, size)})
        if str(payload.get("code", 0)) not in {"0", "200"}:
            raise RuntimeError("Quake API rejected query")
        yield from self.parse(payload)

    def expanded_domain(self, domain):
        """Split saturation into child domains without promoting body matches."""
        seen = set()
        first = list(self.search(f'domain:"{domain}"'))
        for item in first:
            key = (item.host, item.port, item.proto)
            if key not in seen:
                seen.add(key)
                yield item
        if len(first) >= self.config.get("quake", {}).get("split_over", 100):
            for child in sorted({a.host for a in first if a.host.endswith("." + domain)}):
                for item in self.search(f'domain:"{child}"'):
                    key = (item.host, item.port, item.proto)
                    if key not in seen:
                        seen.add(key)
                        yield item
