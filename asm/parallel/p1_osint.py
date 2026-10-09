import json
import re

import httpx

from ..pipeline import StageResult
from ..scope import normalize_host

GENERIC = {"password", "secret", "token", "admin", "login", "config", "api", "company", "公司", "登录", "管理", "系统"}


def validate_keyword(value):
    value = value.strip()
    if not value or value.lower() in GENERIC or len(value) < 4 or any(c in value for c in ("\n", "\r", '"', "\\")):
        raise ValueError("Use a full domain, email, or specific system name")
    if "@" in value:
        _, host = value.rsplit("@", 1)
        normalize_host(host)
        if "." not in host:
            raise ValueError("Email keyword requires a complete domain")
    elif "." in value:
        normalize_host(value)
    elif len(value) < 6:
        raise ValueError("System name must be specific (at least 6 characters)")
    return value


def parse_sse(lines):
    event, data = "message", []
    for line in lines:
        line = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
        line = line.rstrip("\r\n")
        if line == "":
            if data:
                payload = "\n".join(data)
                try:
                    payload = json.loads(payload)
                except ValueError:
                    pass
                yield event, payload
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        try:
            payload = json.loads("\n".join(data))
        except ValueError:
            payload = "\n".join(data)
        yield event, payload


def parse_tender(text):
    fields = {}
    patterns = {
        "system_name": r"(?:系统名称|项目名称)[:：\s]+([^\n]+)",
        "vendor": r"(?:供应商|厂商)[:：\s]+([^\n]+)",
        "version": r"(?:版本)[:：\s]+([^\n]+)",
        "deployment": r"(?:部署地址)[:：\s]+([^\n]+)",
        "person": r"(?:联系人)[:：\s]+([^\n]+)",
        "email": r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "phone": r"(?:电话)[:：\s]+([^\n]+)",
        "tender_id": r"(?:招标编号)[:：\s]+([^\n]+)",
        "ip": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "icp": r"[\u4e00-\u9fff]+ICP备\d+号(?:-\d+)?",
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, text)
        fields[name] = (match[1] if match.lastindex else match[0]).strip() if match else None
    return fields


def run(ctx):
    settings = ctx.config.get("osint", {})
    keywords = [validate_keyword(v) for v in settings.get("keywords", [])]
    if ctx.dry_run:
        events = list(parse_sse((ctx.profile.root / "tests/fixtures/sourcegraph.sse").read_text(encoding="utf-8").splitlines()))
        tender = parse_tender((ctx.profile.root / "tests/fixtures/tender.txt").read_text(encoding="utf-8"))
        ctx.db.fact("tender:fixture", tender)
        ctx.write("events.json", events)
        return StageResult(count=len(events))
    count = 0
    for keyword in keywords:
        query = f'context:global "{keyword}" (password OR secret OR config) count:100'
        with httpx.Client(timeout=45) as client:
            with client.stream("GET", "https://sourcegraph.com/.api/search/stream", params={"q": query, "v": "V3"},
                               headers={"Accept": "text/event-stream"}) as response:
                response.raise_for_status()
                for event, payload in parse_sse(response.iter_lines()):
                    if event == "matches" and isinstance(payload, list):
                        for match in payload:
                            # Store location metadata, not potential credentials from source snippets.
                            repository, path = match.get("repository", ""), match.get("path", "")
                            ctx.note("code_leak_candidate", repository + "/" + path,
                                     "Keyword match: " + keyword + "; inspect authorized public source manually", "low")
                            count += 1
    for source in settings.get("tender_files", []):
        path = ctx.profile.root / source
        data = parse_tender(path.read_text(encoding="utf-8"))
        ctx.db.fact("tender:" + path.name, data)
        if data["system_name"]:
            ctx.db.upsert("systems", {"system_name": data["system_name"], "vendor": data["vendor"],
                "version": data["version"], "urls": data["deployment"], "source": "tender"}, ("system_name",), merge=True)
        if data["person"]:
            ctx.db.upsert("people", {"name": data["person"], "email": data["email"] or "", "phone": data["phone"],
                "cid": None, "source": "tender"}, ("name", "cid", "email"), merge=True)
        count += 1
    return StageResult(count=count, notes=[] if keywords else ["No specific OSINT keywords configured"])
