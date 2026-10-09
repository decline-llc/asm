import base64
import os

from .base import MappingEngine, asset_from


class Fofa(MappingEngine):
    name = "fofa"
    fields = "host,ip,port,protocol,title,domain,server"

    @staticmethod
    def domain_query(domain):
        return f'domain="{domain}" && title!="-" && title!="404"'

    @staticmethod
    def cert_query(value, *, organization=False):
        return 'cert.subject.' + ('org' if organization else 'cn') + '="' + value.replace('"', '\\"') + '"'

    @staticmethod
    def parse(payload):
        fields = payload.get("fields", Fofa.fields)
        if isinstance(fields, str):
            fields = fields.split(",")
        for values in payload.get("results", []):
            item = dict(zip(fields, values)) if isinstance(values, list) else values
            asset = asset_from(item.get("host") or item.get("domain"), item.get("ip"), item.get("port", 443),
                               title=item.get("title", ""), service=item.get("protocol", ""),
                               product=item.get("server", ""))
            if asset:
                yield asset

    def search(self, query, *, max_pages=20):
        auth = {"email": os.environ["FOFA_EMAIL"], "key": os.environ["FOFA_KEY"]}
        self.request("GET", "https://fofa.info/api/v1/info/my", params=auth)
        for page in range(1, max_pages + 1):
            payload = self.request("GET", "https://fofa.info/api/v1/search/all", params={
                **auth, "qbase64": base64.b64encode(query.encode()).decode(), "page": page,
                "size": 50, "fields": self.fields})
            if payload.get("error"):
                raise RuntimeError("FOFA API rejected query or credentials")
            yield from self.parse(payload)
            if len(payload.get("results", [])) < 50:
                break
