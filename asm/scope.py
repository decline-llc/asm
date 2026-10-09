import ipaddress
import re
from urllib.parse import urlsplit

import tldextract

_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


class ScopeError(ValueError):
    pass


def normalize_host(value: str) -> str:
    value = value.strip()
    if "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ScopeError("Only credential-free HTTP(S) URLs are accepted")
        value = parsed.hostname or ""
    value = value.rstrip(".").lower()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    try:
        ip = ipaddress.ip_address(value)
        return str(ip.ipv4_mapped or ip) if isinstance(ip, ipaddress.IPv6Address) else str(ip)
    except ValueError:
        pass
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ScopeError("Invalid IDNA host") from exc
    if len(value) > 253 or not value or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in value.split(".")
    ):
        raise ScopeError(f"Invalid host: {value!r}")
    return value


def registrable(host):
    host = normalize_host(host)
    result = _extract(host)
    return result.top_domain_under_public_suffix or host


def is_local(host):
    host = normalize_host(host)
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class Scope:
    def __init__(self, config, *, passive_only=False, target_local=False):
        self.authorized = config.get("authorization", False) is True
        self.passive_only = passive_only
        self.target_local = target_local
        targets = config.get("targets", {})
        scope = config.get("scope", {})
        self.roots = {normalize_host(v.removeprefix("*.")) for v in targets.get("roots", [])}
        self.networks = [ipaddress.ip_network(v, strict=False) for v in targets.get("ip_cidrs", [])]
        for value in scope.get("include", []):
            try:
                self.networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                self.roots.add(normalize_host(value.removeprefix("*.")))
        # Reject bare public suffixes, e.g. "com" or "co.uk".
        for host in self.roots:
            extracted = _extract(host)
            if extracted.suffix and not extracted.domain:
                raise ScopeError(f"Public suffix is not an authorization scope: {host}")
        self.excluded = {normalize_host(v.removeprefix("*.")) for v in scope.get("exclude_saas", [])}

    @staticmethod
    def _match(host, root):
        return host == root or host.endswith("." + root)

    def contains(self, host):
        host = normalize_host(host)
        if self.target_local and not is_local(host):
            return False
        if any(self._match(host, item) for item in self.excluded):
            return False
        try:
            ip = ipaddress.ip_address(host)
            return any(ip.version == net.version and ip in net for net in self.networks)
        except ValueError:
            return any(self._match(host, root) for root in self.roots)

    def assert_in_scope(self, host, *, active=True):
        if active and (not self.authorized or self.passive_only):
            raise ScopeError("Active requests require authorization=true and non-passive mode")
        if not self.contains(host):
            raise ScopeError(f"Out of scope: {host}")
        return normalize_host(host)
