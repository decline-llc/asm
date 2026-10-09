"""Target HTTP requests validate scope before every hop and bound response size."""
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from ..scope import ScopeError, normalize_host


@dataclass
class Response:
    url: str
    status: int
    headers: dict
    body: bytes

    @property
    def text(self):
        return self.body.decode("utf-8", errors="replace")

    @property
    def title(self):
        match = re.search(r"<title[^>]*>(.*?)</title>", self.text, re.I | re.S)
        return re.sub(r"\s+", " ", match[1]).strip() if match else ""


class TargetHTTP:
    def __init__(self, scope, *, timeout=15, max_bytes=65536, client=None):
        self.scope, self.max_bytes = scope, max_bytes
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)

    def get(self, url, *, redirects=5):
        for _ in range(redirects + 1):
            parsed = urlsplit(url)
            normalize_host(url)
            self.scope.assert_in_scope(parsed.hostname or "")
            with self.client.stream("GET", url, headers={"User-Agent": "ASM-Workbench/0.1"}) as reply:
                body = bytearray()
                for chunk in reply.iter_bytes(chunk_size=min(16384, self.max_bytes)):
                    body.extend(chunk[:self.max_bytes - len(body)])
                    if len(body) >= self.max_bytes:
                        break
                response = Response(str(reply.url), reply.status_code, dict(reply.headers), bytes(body))
            if response.status in {301, 302, 303, 307, 308} and response.headers.get("location"):
                url = urljoin(url, response.headers["location"])
                continue
            return response
        raise ScopeError("Redirect limit exceeded")

    def close(self):
        self.client.close()
