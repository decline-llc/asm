import base64
import hashlib
import os
import re
import threading
import time

import httpx

from .base import MappingEngine, QuotaExceeded, asset_from


class RequestBudgetExceeded(RuntimeError):
    pass


class Fofa(MappingEngine):
    name = "fofa"
    fields = "host,ip,port,protocol,title,domain,server"
    # These are supported output columns; query operators have a separate grammar.
    supported_fields = frozenset(fields.split(",")) | frozenset({
        "banner", "country", "country_name", "region", "city", "longitude", "latitude",
        "as_number", "as_organization", "base_protocol", "icp", "cert", "lastupdatetime", "last_updatetime",
    })
    _account_cache = {}
    _account_lock = threading.Lock()
    account_cache_seconds = 600

    def __init__(self, db, config, *, client=None, limiter=None, clock=time.monotonic):
        super().__init__(db, config, client=client, limiter=limiter)
        self.clock = clock
        self.last_errors = []
        self.health = {"status": "not_called"}
        self._budget = None
        self.request_count = 0

    @classmethod
    def clear_account_cache(cls):
        with cls._account_lock:
            cls._account_cache.clear()

    @classmethod
    def validate_fields(cls, fields):
        values = fields.split(",") if isinstance(fields, str) else fields
        if not isinstance(values, (list, tuple)) or not values or any(not isinstance(v, str) for v in values):
            raise ValueError("FOFA fields must be a comma-separated string or list")
        values = [value.strip() for value in values]
        if len(values) > 32 or any(value not in cls.supported_fields for value in values):
            raise ValueError("Unsupported FOFA output field")
        if not {"host", "domain", "ip"}.intersection(values):
            raise ValueError("FOFA output fields need host, domain or ip")
        return ",".join(dict.fromkeys(values))

    @staticmethod
    def _safe_message(value):
        text = str(value or "")
        for key in ("FOFA_EMAIL", "FOFA_KEY"):
            credential = os.environ.get(key)
            if credential:
                text = text.replace(credential, "[REDACTED]")
        return re.sub(r"(?i)([?&](?:email|key|token|api_key)=)[^&\s]+", r"\1[REDACTED]", text)[:1000]

    @classmethod
    def _safe_payload(cls, value):
        if isinstance(value, dict):
            return {key: "[REDACTED]" if key.lower() in {"email", "key", "token", "username", "password", "secret"}
                    else cls._safe_payload(child) for key, child in value.items()}
        if isinstance(value, list):
            return [cls._safe_payload(child) for child in value]
        if isinstance(value, str):
            # Preserve full response text while removing current authentication values.
            text = value
            for key in ("FOFA_EMAIL", "FOFA_KEY"):
                credential = os.environ.get(key)
                if credential:
                    text = text.replace(credential, "[REDACTED]")
            return re.sub(r"(?i)([?&](?:email|key|token|api_key)=)[^&\s]+", r"\1[REDACTED]", text)
        return value

    def _error(self, operation, *, payload=None, exception=None, reason=""):
        payload = payload if isinstance(payload, dict) else {}
        message = self._safe_message(payload.get("errmsg", payload.get("message", reason)))
        code = payload.get("code")
        if code is None:
            found = re.search(r"\[?(\d{6})\]?", message)
            code = int(found.group(1)) if found else None
        error = {"operation": operation, "code": code, "errmsg": message,
            "exception_type": type(exception).__name__ if exception else None}
        if isinstance(exception, httpx.HTTPStatusError):
            error["http_status"] = exception.response.status_code
        self.last_errors.append(error)
        self.health["status"] = "degraded"
        return error

    def request(self, method, url, **kwargs):
        """Every physical attempt reserves the persistent limiter and local budget."""
        for attempt in range(2):
            if self._budget is not None and self._budget <= 0:
                raise RequestBudgetExceeded("FOFA per-query request budget exhausted")
            self.limiter.acquire()
            self.request_count += 1
            if self._budget is not None:
                self._budget -= 1
            reply = self.client.request(method, url, **kwargs)
            if reply.status_code == 429 and attempt == 0:
                try:
                    wait = float(reply.headers.get("Retry-After", 5))
                except ValueError:
                    wait = 5
                getattr(self.limiter, "sleeper", time.sleep)(min(60, max(1, wait)))
                continue
            try:
                reply.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise httpx.HTTPStatusError(f"FOFA HTTP status {reply.status_code}",
                    request=httpx.Request(method, self._safe_message(url)), response=reply) from exc
            payload = reply.json()
            if not isinstance(payload, dict):
                raise ValueError("FOFA response must be a mapping")
            # Errors can echo authentication values too; redact before the workbench records them.
            return self._safe_payload(payload)
        raise RuntimeError("FOFA persistent rate limit")

    def _account(self, auth):
        fingerprint = hashlib.sha256((auth["email"] + "\0" + auth["key"]).encode()).hexdigest()
        with self._account_lock:
            cached = self._account_cache.get(fingerprint)
            if cached and 0 <= self.clock() - cached["at"] < self.account_cache_seconds:
                self.health["account"] = {**cached["health"], "cached": True}
                if cached.get("error"):
                    self.last_errors.append({**cached["error"], "cached": True})
                    self.health["status"] = "degraded"
                return
            account_health = {"status": "healthy", "cached": False}
            error = None
            try:
                payload = self.request("GET", "https://fofa.info/api/v1/info/my", params=auth)
                if payload.get("error"):
                    error = self._error("account_info", payload=payload)
                    account_health["status"] = "degraded"
            except QuotaExceeded:
                raise
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                error = self._error("account_info", exception=exc, reason=type(exc).__name__)
                account_health["status"] = "degraded"
            self._account_cache[fingerprint] = {"at": self.clock(), "health": account_health, "error": error}
            self.health["account"] = account_health

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
            if not isinstance(item, dict):
                raise ValueError("FOFA result row must be an array or mapping")
            asset = asset_from(item.get("host") or item.get("domain"), item.get("ip"), item.get("port", 443),
                               title=item.get("title", ""), service=item.get("protocol", ""),
                               product=item.get("server", ""))
            if asset:
                yield asset

    def search(self, query, *, max_pages=20, size=50, fields=None, check_account=None,
               max_requests=None, fallback_fields=False):
        if type(max_pages) is not int or not 1 <= max_pages <= 200:
            raise ValueError("FOFA max_pages must be between 1 and 200")
        if type(size) is not int or not 1 <= size <= 1000:
            raise ValueError("FOFA size must be between 1 and 1000")
        if max_requests is not None and (type(max_requests) is not int or not 1 <= max_requests <= 200):
            raise ValueError("FOFA max_requests must be between 1 and 200")
        if type(fallback_fields) is not bool:
            raise ValueError("FOFA fallback_fields must be boolean")
        settings = self.config.get("fofa", {})
        check_account = settings.get("check_account", True) if check_account is None else check_account
        if type(check_account) is not bool:
            raise ValueError("FOFA check_account must be boolean")
        selected_fields = self.validate_fields(fields if fields is not None else settings.get("fields", self.fields))
        auth = {"email": os.environ.get("FOFA_EMAIL", ""), "key": os.environ.get("FOFA_KEY", "")}
        if not all(auth.values()):
            raise ValueError("FOFA credentials missing")
        self.last_errors = []
        self.health = {"status": "healthy", "pages_requested": 0, "rows_returned": 0,
            "total_estimate": None, "truncated": False, "fields": selected_fields, "account": {"status": "not_requested"}}
        self._budget = max_requests if max_requests is not None else min(200, max_pages + 1)
        start_requests = self.request_count
        seen = set()
        try:
            if check_account:
                self._account(auth)
            for page in range(1, max_pages + 1):
                params = {**auth, "qbase64": base64.b64encode(query.encode()).decode(), "page": page,
                          "size": size, "fields": selected_fields}
                try:
                    self.health["pages_requested"] += 1
                    payload = self.request("GET", "https://fofa.info/api/v1/search/all", params=params)
                    if payload.get("error"):
                        self._error("search", payload=payload)
                        if fallback_fields and selected_fields != self.fields:
                            selected_fields = self.fields
                            params["fields"] = selected_fields
                            self.health["fields"] = selected_fields
                            payload = self.request("GET", "https://fofa.info/api/v1/search/all", params=params)
                            if payload.get("error"):
                                self._error("search", payload=payload)
                                return
                        else:
                            return
                    if not isinstance(payload.get("results", []), list):
                        raise ValueError("FOFA results must be a list")
                    total = payload.get("size", payload.get("total"))
                    if type(total) is int and total >= 0:
                        self.health["total_estimate"] = total
                    self.health["rows_returned"] += len(payload.get("results", []))
                    parsed_payload = {**payload, "fields": payload.get("fields", selected_fields)}
                    for asset in self.parse(parsed_payload):
                        key = (asset.host, asset.port, asset.proto)
                        if key not in seen:
                            seen.add(key)
                            yield asset
                    if len(payload.get("results", [])) < size:
                        break
                    if page == max_pages:
                        self.health.update(truncated=True, stop_reason="max_pages", status="degraded")
                except QuotaExceeded:
                    self.health.update(status="quota-exhausted", truncated=True, stop_reason="quota")
                    raise
                except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                    self._error("search", exception=exc, reason=type(exc).__name__)
                    self.health.update(truncated=True, stop_reason="request_budget" if isinstance(exc, RequestBudgetExceeded) else "source_error")
                    return
        except QuotaExceeded:
            self.health.update(status="quota-exhausted", truncated=True, stop_reason="quota")
            raise
        finally:
            self.health["requests_used"] = self.request_count - start_requests
            total = self.health.get("total_estimate")
            if total is not None and self.health["rows_returned"] < total and self.health["status"] != "quota-exhausted":
                self.health.update(truncated=True, status="degraded")
            self.health["errors"] = list(self.last_errors)
            self._budget = None
