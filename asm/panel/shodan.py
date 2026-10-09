import os

from .base import MappingEngine, asset_from, joined


class Shodan(MappingEngine):
    name = "shodan"

    @staticmethod
    def parse(payload):
        for item in payload.get("matches", []):
            hosts = item.get("hostnames", [])
            asset = asset_from(hosts[0] if hosts else "", item.get("ip_str", ""), item.get("port", 443),
                proto=item.get("transport", "tcp"), service=item.get("_shodan", {}).get("module", ""),
                product=item.get("product", ""), version=item.get("version", ""),
                title=item.get("http", {}).get("title", ""), tech=joined(item.get("http", {}).get("components", {})))
            if asset:
                yield asset

    def search(self, query, *, max_pages=10):
        for page in range(1, min(10, max_pages) + 1):
            payload = self.request("GET", "https://api.shodan.io/shodan/host/search", params={
                "key": os.environ["SHODAN_KEY"], "query": query, "page": page})
            yield from self.parse(payload)
            if len(payload.get("matches", [])) < 100:
                break
