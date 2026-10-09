import os

from .base import MappingEngine, asset_from


class Censys(MappingEngine):
    name = "censys"

    @staticmethod
    def parse(payload):
        hits = payload.get("result", {}).get("hits", payload.get("data", {}).get("hits", []))
        for item in hits:
            for service in item.get("services", []):
                asset = asset_from("", item.get("ip", ""), service.get("port", 443),
                    proto=service.get("transport_protocol", "tcp").lower(),
                    service=service.get("service_name", ""),
                    title=service.get("http", {}).get("response", {}).get("html_title", ""))
                if asset:
                    yield asset

    def search(self, query, *, max_pages=10):
        cursor = None
        for _ in range(max_pages):
            payload = self.request("GET", "https://search.censys.io/api/v2/hosts/search",
                auth=(os.environ["CENSYS_ID"], os.environ["CENSYS_SECRET"]),
                params={"q": query, "per_page": 100, **({"cursor": cursor} if cursor else {})})
            yield from self.parse(payload)
            cursor = payload.get("result", {}).get("links", {}).get("next")
            if not cursor:
                break
