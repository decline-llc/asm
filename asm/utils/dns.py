"""Validated resolver settings and portable DNS response parsers."""
import ipaddress
import re
from dataclasses import dataclass

RTYPES = ("A", "AAAA", "MX", "NS", "CNAME")
DEFAULT_RESOLVERS = ("1.1.1.1", "114.114.114.114", "8.8.8.8")
FAKE_IP = ipaddress.ip_network("198.18.0.0/15")


def parse_endpoint(value):
    value = str(value)
    if value.startswith("["):
        match = re.fullmatch(r"\[([^]]+)\](?::(\d+))?", value)
        if not match:
            raise ValueError("Invalid bracketed DNS resolver")
        host, port = match[1], int(match[2] or 53)
    else:
        try:
            return str(ipaddress.ip_address(value)), 53
        except ValueError:
            host, separator, port = value.rpartition(":")
            if not separator or not port.isdigit():
                raise ValueError("DNS resolvers must be IP addresses with an optional port") from None
            port = int(port)
    host = str(ipaddress.ip_address(host))
    if not 1 <= port <= 65535:
        raise ValueError("DNS resolver port must be between 1 and 65535")
    return host, port


def endpoint(value):
    host, port = parse_endpoint(value)
    return host if port == 53 else f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def dns_name(value):
    value = str(value).strip().rstrip(".").lower().encode("idna").decode("ascii")
    if not value or len(value) > 253 or any(not re.fullmatch(r"[a-z0-9_-]{1,63}", label)
                                          for label in value.split(".")):
        raise ValueError("Invalid DNS name")
    return value


def record_value(rtype, value, *, reject_fake_ip=True):
    value = str(value).strip()
    if rtype in ("A", "AAAA"):
        ip = ipaddress.ip_address(value)
        if ip.version != (4 if rtype == "A" else 6):
            raise ValueError("DNS address family mismatch")
        if ip.is_unspecified or (reject_fake_ip and ip.version == 4 and ip in FAKE_IP):
            raise ValueError("Unusable unspecified or proxy fake-IP address")
        return str(ip)
    if rtype == "MX":
        if len(value.split()) == 1:
            return dns_name(value)  # dnsx can omit priority; retain that evidence as-is.
        priority, name = value.split()
        priority = int(priority)
        if not 0 <= priority <= 65535:
            raise ValueError("Invalid MX priority")
        return "0 ." if priority == 0 and name == "." else f"{priority} {dns_name(name)}"
    if rtype in ("NS", "CNAME"):
        return dns_name(value)
    raise ValueError("Unsupported DNS record type")


@dataclass(frozen=True)
class DNSSettings:
    resolvers: tuple = DEFAULT_RESOLVERS
    preferred: str = "114.114.114.114"
    timeout: float = 3
    workers: int = 8
    max_hops: int = 16
    dnsx: bool = True
    windows_verify: bool = True
    reject_fake_ip: bool = True
    takeover_probe: bool = False

    @classmethod
    def from_config(cls, config):
        values = config.get("dns", {})
        if not isinstance(values, dict):
            raise ValueError("dns must be a mapping")
        resolvers = values.get("resolvers", list(DEFAULT_RESOLVERS))
        if not isinstance(resolvers, list) or not 1 <= len(resolvers) <= 10 or any(
                not isinstance(v, str) for v in resolvers):
            raise ValueError("dns.resolvers must be a list of 1 to 10 IP endpoints")
        resolvers = tuple(dict.fromkeys(endpoint(v) for v in resolvers))
        preferred = endpoint(values.get("preferred_resolver", "114.114.114.114"
                                       if "114.114.114.114" in resolvers else resolvers[0]))
        if preferred not in resolvers:
            raise ValueError("dns.preferred_resolver must be in dns.resolvers")
        numbers = {}
        for key, default, maximum in (("timeout", 3, 30), ("workers", 8, 60), ("max_cname_hops", 16, 32)):
            value = values.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= maximum:
                raise ValueError(f"dns.{key} must be positive and <= {maximum}")
            if key != "timeout" and not isinstance(value, int):
                raise ValueError(f"dns.{key} must be an integer")
            numbers[key] = value
        flags = {}
        for key, default in (("dnsx", True), ("windows_verify", True), ("reject_fake_ip", True),
                             ("takeover_probe", False)):
            value = values.get(key, default)
            if type(value) is not bool:
                raise ValueError(f"dns.{key} must be a YAML boolean")
            flags[key] = value
        return cls(resolvers, preferred, numbers["timeout"], numbers["workers"], numbers["max_cname_hops"], **flags)


def parse_dig(text):
    match = re.search(r"status:\s*([A-Z]+)", text)
    answers = []
    for line in text.splitlines():
        if not line or line.startswith(";"):
            continue
        fields = line.split(None, 4)
        if len(fields) == 5 and fields[2] == "IN" and fields[3] in RTYPES:
            answers.append({"name": fields[0].rstrip(".").lower(), "rtype": fields[3], "value": fields[4]})
    return {"status": match[1] if match else "ERROR", "answers": answers}


def windows_query(domain, rtype, resolver, timeout=3):
    import dns.exception
    import dns.resolver
    host, port = parse_endpoint(resolver)
    client = dns.resolver.Resolver(configure=False)
    client.nameservers, client.port = [host], port
    client.timeout = client.lifetime = timeout
    result = {"domain": domain, "rtype": rtype, "resolver": resolver, "source": "windows",
              "status": "NOERROR", "answers": [], "error": ""}
    try:
        reply = client.resolve(domain + ".", rtype, search=False, raise_on_no_answer=False)
        result["answers"] = [{"name": domain, "rtype": rtype, "value": str(value)} for value in reply]
    except dns.resolver.NXDOMAIN:
        result["status"] = "NXDOMAIN"
    except dns.exception.DNSException as exc:
        result["status"], result["error"] = "ERROR", type(exc).__name__
    return result
