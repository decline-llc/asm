"""Validated resolver settings and portable DNS response parsers.

This module is also shipped into WSL as ``dns_support`` for the stdlib-only dig
worker, so it must keep module-level imports inside the standard library.
"""
import base64
import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

RTYPES = ("A", "AAAA", "MX", "NS", "CNAME")
DEFAULT_RESOLVERS = ("1.1.1.1", "114.114.114.114", "8.8.8.8")
# Encrypted resolvers verified reachable from the deployment host. Opt-in only: leaving
# dns.doh_resolvers empty keeps the plaintext UDP/TCP 53 path and every existing
# configuration fingerprint unchanged.
DOH_ENDPOINTS = ("https://223.5.5.5/dns-query", "https://1.12.12.12/dns-query")
FAKE_IP = ipaddress.ip_network("198.18.0.0/15")
LOOPBACK = (ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128"))
DOH_MAX_ENDPOINTS = 4
DOH_MAX_BYTES = 65535
DOH_MAX_ANSWERS = 32


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


def doh_endpoint(value):
    """Normalize an HTTPS DNS-over-HTTPS endpoint that needs no bootstrap lookup.

    The host must be an IP literal: a hostname would have to be resolved first, which
    is exactly the poisoned system resolver path this setting exists to avoid.
    """
    text = str(value).strip()
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid DoH endpoint") from None
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("DoH endpoints must be absolute https URLs")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("DoH endpoints must not carry credentials, query or fragment")
    if not parsed.path.startswith("/"):
        raise ValueError("DoH endpoint path must be absolute")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        raise ValueError("DoH endpoint host must be an IP literal") from None
    port = 443 if port is None else port
    if not 1 <= port <= 65535:
        raise ValueError("DoH endpoint port must be between 1 and 65535")
    literal = f"[{address}]" if address.version == 6 else str(address)
    return f"https://{literal if port == 443 else f'{literal}:{port}'}{parsed.path}"


def dns_name(value):
    value = str(value).strip().rstrip(".").lower().encode("idna").decode("ascii")
    if not value or len(value) > 253 or any(not re.fullmatch(r"[a-z0-9_-]{1,63}", label)
                                          for label in value.split(".")):
        raise ValueError("Invalid DNS name")
    return value


def record_value(rtype, value, *, reject_fake_ip=True, reject_loopback=False):
    value = str(value).strip()
    if rtype in ("A", "AAAA"):
        ip = ipaddress.ip_address(value)
        if ip.version != (4 if rtype == "A" else 6):
            raise ValueError("DNS address family mismatch")
        if ip.is_unspecified or (reject_fake_ip and ip.version == 4 and ip in FAKE_IP):
            raise ValueError("Unusable unspecified or proxy fake-IP address")
        if reject_loopback and any(ip in network for network in LOOPBACK):
            # A public name resolving to loopback means the local resolver is lying;
            # treating it as a target would scan the workstation itself.
            raise ValueError("Unusable loopback answer for a public target")
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
    doh_resolvers: tuple = ()
    doh_trusted: bool = True

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
        doh = values.get("doh_resolvers", [])
        if not isinstance(doh, list) or len(doh) > DOH_MAX_ENDPOINTS or any(
                not isinstance(v, str) for v in doh):
            raise ValueError(f"dns.doh_resolvers must be a list of up to {DOH_MAX_ENDPOINTS} HTTPS endpoints")
        doh_resolvers = tuple(dict.fromkeys(doh_endpoint(v) for v in doh))
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
                             ("takeover_probe", False), ("doh_trusted", True)):
            value = values.get(key, default)
            if type(value) is not bool:
                raise ValueError(f"dns.{key} must be a YAML boolean")
            flags[key] = value
        return cls(resolvers=resolvers, preferred=preferred, timeout=numbers["timeout"],
                   workers=numbers["workers"], max_hops=numbers["max_cname_hops"],
                   doh_resolvers=doh_resolvers, **flags)


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


def _doh_answer_values(message, domain, rtype):
    """Collect only the CNAME-reachable answers of the queried type from a DoH reply."""
    import dns.rdatatype
    wanted, chain, values = dns.rdatatype.from_text(rtype), {domain}, []
    for rrset in message.answer:
        if rrset.rdtype == dns.rdatatype.CNAME:
            chain.update(str(rr.target).rstrip(".").lower() for rr in rrset)
    for rrset in message.answer:
        if rrset.rdtype != wanted or str(rrset.name).rstrip(".").lower() not in chain:
            continue
        for record in rrset:
            if rtype in ("A", "AAAA"):
                values.append(str(record.address))
            elif rtype == "MX":
                values.append(f"{record.preference} {str(record.exchange).rstrip('.')}")
            else:
                values.append(str(record.target).rstrip("."))
            if len(values) >= DOH_MAX_ANSWERS:
                return values
    return values


def doh_query(domain, rtype, url, timeout=3, client=None):
    """Query one encrypted resolver; same observation shape as ``windows_query``.

    The endpoint is an IP literal with certificate verification on, and no environment
    proxy or HTTP redirect is honoured, so a poisoned system resolver or a transparent
    proxy cannot silently redirect the trusted path.
    """
    import dns.exception
    import dns.flags
    import dns.message
    import dns.rcode
    import dns.rdatatype
    import httpx
    url = doh_endpoint(url)
    domain = str(domain).strip().rstrip(".").lower()
    result = {"domain": domain, "rtype": rtype, "resolver": url, "source": "doh",
              "status": "NOERROR", "answers": [], "error": ""}
    if rtype not in RTYPES:
        result["status"], result["error"] = "ERROR", "UnsupportedQueryType"
        return result
    owned = client is None
    if owned:
        client = httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)
    try:
        query = dns.message.make_query(domain + ".", dns.rdatatype.from_text(rtype))
        encoded = base64.urlsafe_b64encode(query.to_wire()).rstrip(b"=").decode("ascii")
        reply = client.get(url, params={"dns": encoded}, headers={"accept": "application/dns-message"})
        if reply.status_code != 200:
            result["status"], result["error"] = "ERROR", f"HTTP {reply.status_code}"
            return result
        media = reply.headers.get("content-type", "").split(";")[0].strip().lower()
        if media and media != "application/dns-message":
            result["status"], result["error"] = "ERROR", "UnexpectedContentType"
            return result
        if len(reply.content) > DOH_MAX_BYTES:
            result["status"], result["error"] = "ERROR", "ResponseTooLarge"
            return result
        message = dns.message.from_wire(reply.content)
        questions = [str(question.name).rstrip(".").lower() for question in message.question]
        if questions != [domain] or (message.question and
                                     dns.rdatatype.to_text(message.question[0].rdtype) != rtype):
            result["status"], result["error"] = "ERROR", "QuestionMismatch"
            return result
    except dns.exception.DNSException as exc:
        result["status"], result["error"] = "ERROR", type(exc).__name__
        return result
    except httpx.HTTPError as exc:
        result["status"], result["error"] = "ERROR", type(exc).__name__
        return result
    finally:
        if owned:
            client.close()
    if message.rcode() == dns.rcode.NXDOMAIN:
        result["status"] = "NXDOMAIN"
        return result
    if message.rcode() != dns.rcode.NOERROR:
        result["status"], result["error"] = "ERROR", dns.rcode.to_text(message.rcode())
        return result
    if message.flags & dns.flags.TC:
        result["status"], result["error"] = "ERROR", "Truncated"
        return result
    result["answers"] = [{"name": domain, "rtype": rtype, "value": value}
                         for value in _doh_answer_values(message, domain, rtype)]
    return result
