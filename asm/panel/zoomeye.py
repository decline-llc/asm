import base64
import os

from .base import MappingEngine, asset_from, joined


class ZoomEye(MappingEngine):
    name = "zoomeye"

    @staticmethod
    def parse(payload):
        for item in payload.get("data", payload.get("matches", [])):
            info = item.get("portinfo", {})
            asset = asset_from(item.get("domain") or item.get("url"), item.get("ip", ""),
                item.get("port", info.get("port", 443)), title=joined(item.get("title", info.get("title", ""))),
                service=item.get("service", info.get("service", "")),
                product=item.get("app", info.get("app", "")), version=item.get("version", info.get("version", "")))
            if asset:
                yield asset

    def search(self, query, *, max_pages=10):
        for page in range(1, max_pages + 1):
            payload = self.request("POST", "https://api.zoomeye.ai/v2/search",
                headers={"API-KEY": os.environ["ZOOEYE_KEY"]}, json={
                    "qbase64": base64.b64encode(query.encode()).decode(), "page": page, "pagesize": 100,
                    "fields": "ip,port,domain,title,service,app,version"})
            yield from self.parse(payload)
            if len(payload.get("data", [])) < 100:
                break
