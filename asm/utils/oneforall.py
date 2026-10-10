"""Portable configuration shared with the native OneForAll job wrapper."""
import ipaddress
import re
from dataclasses import dataclass

PASSIVE_MODULES = {
    "modules.certificates.certspotter": "api.certspotter.com",
    "modules.certificates.crtsh": "crt.sh",
    "modules.datasets.hackertarget": "api.hackertarget.com",
    "modules.datasets.rapiddns": "rapiddns.io",
    "modules.datasets.anubis": "jldc.me",
    "modules.intelligence.alienvault": "otx.alienvault.com",
    "modules.intelligence.threatminer": "api.threatminer.org",
}
DEFAULT_MODULES = tuple(module for module in PASSIVE_MODULES if module not in
                        ("modules.certificates.crtsh", "modules.datasets.hackertarget"))
PASSIVE_FLAGS = ("brute", "dns", "req", "alive", "takeover", "wildcard", "srv", "version_check")


def domain_name(value):
    if not isinstance(value, str):
        raise ValueError("OneForAll domains must be strings")
    value = value.strip().rstrip(".").lower().encode("idna").decode("ascii")
    if not value or len(value) > 253 or "." not in value or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in value.split(".")):
        raise ValueError("OneForAll requires a bare DNS domain")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError("OneForAll cannot collect IP addresses")


@dataclass(frozen=True)
class OneForAllSettings:
    enabled: bool = True
    modules: tuple = DEFAULT_MODULES
    module_timeout: float = 45
    request_timeout: float = 15

    @classmethod
    def from_config(cls, config):
        values = config.get("oneforall", {})
        if not isinstance(values, dict):
            raise ValueError("oneforall must be a mapping")
        if set(values) - {"enabled", "modules", "module_timeout", "request_timeout"}:
            raise ValueError("Unsupported OneForAll option; active modules are handled by other stages")
        enabled = values.get("enabled", True)
        if type(enabled) is not bool:
            raise ValueError("oneforall.enabled must be a YAML boolean")
        modules = values.get("modules", list(DEFAULT_MODULES))
        if not isinstance(modules, list) or not modules or any(
                not isinstance(module, str) or module not in PASSIVE_MODULES for module in modules):
            raise ValueError("oneforall.modules must be a nonempty list of supported passive modules")
        timeouts = []
        for key, default, maximum in (("module_timeout", 45, 300), ("request_timeout", 15, 60)):
            value = values.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= maximum:
                raise ValueError(f"oneforall.{key} must be positive and <= {maximum}")
            timeouts.append(value)
        return cls(enabled, tuple(dict.fromkeys(modules)), *timeouts)

    def as_config(self):
        return {"enabled": self.enabled, "modules": list(self.modules), "module_timeout": self.module_timeout,
                "request_timeout": self.request_timeout}
