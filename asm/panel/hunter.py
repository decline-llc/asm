import base64
import os

from .base import MappingEngine, asset_from, joined


class Hunter(MappingEngine):
    name = "hunter"

    @staticmethod
    def parse(payload):
        for item in payload.get("data", {}).get("arr", []):
            asset = asset_from(item.get("url") or item.get("domain"), item.get("ip", ""), item.get("port", 443),
                title=item.get("web_title", ""), service=item.get("protocol", ""),
                tech=joined(item.get("component", [])))
            if asset:
                yield asset

    def search(self, query, *, max_pages=10):
        for page in range(1, max_pages + 1):
            data = self.request("GET", "https://hunter.qianxin.com/openApi/search", params={
                "api-key": os.environ["HUNTER_KEY"], "search": base64.urlsafe_b64encode(query.encode()).decode(),
                "page": page, "page_size": 100, "is_web": 0})
            if data.get("code") not in (200, 0, None):
                raise RuntimeError("Hunter API rejected query")
            yield from self.parse(data)
            if len(data.get("data", {}).get("arr", [])) < 100:
                break
