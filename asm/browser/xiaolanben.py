import json
from enum import Enum
from pathlib import Path


class Phase(str, Enum):
    WARMUP = "warmup"
    SEARCH = "search"
    IDENTIFY = "identify"
    DETAIL = "detail"
    EQUITY = "equity"
    EXTRACT = "extract"


class Xiaolanben:
    def __init__(self):
        self.trace = []

    def replay(self, fixture):
        records = json.loads(Path(fixture).read_text(encoding="utf-8"))
        self.trace = [p.value for p in Phase]
        by_parent = {}
        for item in records:
            by_parent.setdefault(item.get("parent_cid"), []).append(item)
        output, seen = [], set()

        def walk(parent, level):
            for item in by_parent.get(parent, []):
                if item["cid"] in seen or (parent and float(item.get("share_pct") or 0) < 51):
                    continue
                seen.add(item["cid"])
                item = dict(item, level=level, website=item.get("website") or None, source="equity_fixture")
                output.append(item)
                walk(item["cid"], level + 1)
        walk(None, 0)
        return output

    def supervised(self, page, *, detail_url, search_url, keyword, selectors):
        """Same page warms the signature SDK; selectors are configured by the operator."""
        self.trace = []
        self.trace.append(Phase.WARMUP.value)
        page.goto(detail_url, wait_until="domcontentloaded")
        self.trace.append(Phase.SEARCH.value)
        page.goto(search_url, wait_until="domcontentloaded")
        page.locator(selectors["search_input"]).fill(keyword)
        page.locator(selectors["search_submit"]).click()
        self.trace.append(Phase.IDENTIFY.value)
        links = page.locator(selectors["result_links"]).evaluate_all("els => els.map(e => e.href)")
        self.trace.append(Phase.DETAIL.value)
        self.trace.append(Phase.EQUITY.value)
        results = []
        for url in links:
            page.goto(url, wait_until="domcontentloaded")
            results.append({"url": url, "text": page.inner_text("body")})
        self.trace.append(Phase.EXTRACT.value)
        return results
