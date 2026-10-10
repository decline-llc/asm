"""Strict profile loading; no implicit authorization or live target defaults."""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .utils.dns import DNSSettings


@dataclass(frozen=True)
class Config:
    data: dict
    path: Path
    root: Path

    @property
    def name(self):
        return self.data["profile"]

    @property
    def output(self):
        # Separate project databases prevent accidental cross-customer reports.
        return (self.root / self.data.get("output", {}).get("dir", "data") / self.name).resolve()

    def fingerprint(self, passive_only=False, target_local=False):
        payload = {"config": self.data, "passive_only": passive_only, "target_local": target_local}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]
        return f"{self.name}:{digest}"


def load_config(profile="default", root=None):
    root = Path(root or Path.cwd()).resolve()
    path = Path(profile)
    if not path.is_file():
        path = root / "profiles" / f"{profile}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Profile must be a mapping")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", str(data.get("profile", ""))):
        raise ValueError("profile must be a simple project identifier")
    if type(data.get("authorization", False)) is not bool:
        raise ValueError("authorization must be a YAML boolean")
    for section in ("targets", "scope", "rates", "limits", "output"):
        if not isinstance(data.get(section, {}), dict):
            raise ValueError(f"{section} must be a mapping")
    for section, keys in {"targets": ("roots", "ip_cidrs", "brands", "extra_persons"),
                          "scope": ("include", "exclude_saas"), "web": ("urls",)}.items():
        values = data.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f"{section} must be a mapping")
        for key in keys:
            value = values.get(key, [])
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                raise ValueError(f"{section}.{key} must be a list of strings")
    for section in ("rates", "limits"):
        for key, value in data.get(section, {}).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{section}.{key} must be positive")
    if data.get("rates", {}).get("fofa_min_interval", 15) < 15:
        raise ValueError("FOFA min interval must be >= 15 seconds")
    if data.get("rates", {}).get("fofa_daily", 200) > 200:
        raise ValueError("FOFA daily quota must be <= 200")
    dns_settings = DNSSettings.from_config(data)
    # Effective DNS defaults participate in resume fingerprints, including older profiles.
    data["dns"] = {"resolvers": list(dns_settings.resolvers), "preferred_resolver": dns_settings.preferred,
                   "timeout": dns_settings.timeout, "workers": dns_settings.workers,
                   "max_cname_hops": dns_settings.max_hops, "dnsx": dns_settings.dnsx,
                   "windows_verify": dns_settings.windows_verify, "reject_fake_ip": dns_settings.reject_fake_ip,
                   "takeover_probe": dns_settings.takeover_probe}
    load_dotenv(root / ".env", override=False)
    return Config(data, path.resolve(), root)
