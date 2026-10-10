import ipaddress
import xml.etree.ElementTree as ET

from ..models import Asset
from ..pipeline import StageResult
from ..scope import ScopeError
from ..utils.dns import DNSSettings, record_value
from .s5_dns_cdn import scan_ports


def parse_ports(value):
    ports = set()
    for token in value.split(","):
        if "-" in token:
            lo, hi = map(int, token.split("-"))
            if not 1 <= lo <= hi <= 65535:
                raise ValueError("Invalid port range")
            ports.update(range(lo, hi + 1))
        else:
            port = int(token)
            if not 1 <= port <= 65535:
                raise ValueError("Invalid port")
            ports.add(port)
    return ports


def parse_nmap(path):
    # XML from a local tool: reject DTD/entities rather than fetching external resources.
    raw = path.read_bytes()
    if b"<!ENTITY" in raw or b"<!DOCTYPE" in raw:
        # Nmap's harmless <!DOCTYPE nmaprun> contains no entity definitions.
        raw = raw.replace(b"<!DOCTYPE nmaprun>", b"")
        if b"<!ENTITY" in raw or b"<!DOCTYPE" in raw:
            raise ValueError("Unexpected XML DTD")
    tree = ET.fromstring(raw)
    for host in tree.findall("host"):
        address = host.find("address")
        if address is None:
            continue
        ip = address.get("addr")
        for port in host.findall("ports/port"):
            state = port.find("state")
            if state is None or state.get("state") != "open":
                continue
            service = port.find("service")
            fields = service.attrib if service is not None else {}
            yield Asset(host=ip, ip=ip, port=int(port.get("portid")), proto=port.get("protocol", "tcp"),
                service=fields.get("name", ""), product=fields.get("product", ""),
                version=fields.get("version", ""), tech=fields.get("extrainfo", ""), source="nmap")


def honeypot(open_ports, requested):
    # Small explicit port lists are local harnesses, not evidence of a honeypot.
    requested = set(requested)
    return len(requested) >= 1000 and requested <= set(open_ports)


def clusters(records):
    nets = {}
    for row in records:
        try:
            ip = ipaddress.ip_address(row["ip"])
        except (ValueError, KeyError):
            continue
        net = str(ipaddress.ip_network(f"{ip}/{'24' if ip.version == 4 else '64'}", strict=False))
        nets.setdefault(net, set()).add(row.get("host", row["ip"]))
    return {net: "核心集群" if len(hosts) >= 5 else "独立弱防护" if len(hosts) == 1 else "其他"
            for net, hosts in nets.items()}


def selected_targets(ctx):
    settings = ctx.config.get("ports", {})
    targets = list(settings.get("targets", []))
    if not targets:
        targets = [str(net.network_address) for net in ctx.scope.networks if net.num_addresses == 1]
        for row in ctx.db.rows("SELECT domain FROM domains"):
            evidence = ctx.db.get_fact("dns:" + row["domain"])
            if evidence is not None:
                targets.extend(ip for values in evidence.get("selected", {}).values() for ip in values
                               if ctx.scope.contains(ip))
            else:
                targets.extend(r["value"] for r in ctx.db.rows(
                    "SELECT DISTINCT value FROM dns_records WHERE domain=? AND rtype IN ('A','AAAA')",
                    (row["domain"],)) if ctx.scope.contains(r["value"]))
    clean = []
    reject = DNSSettings.from_config(ctx.config).reject_fake_ip
    for target in dict.fromkeys(targets):
        try:
            ip = ipaddress.ip_address(target)
            clean.append(record_value("A" if ip.version == 4 else "AAAA", target, reject_fake_ip=reject))
        except ValueError as exc:
            raise ScopeError("Port targets must be approved usable IPs; proxy fake-IP is rejected by default") from exc
    return clean


def run(ctx):
    settings = ctx.config.get("ports", {})
    targets = selected_targets(ctx)
    pending, count, notes = [], 0, []
    for target in targets:
        ctx.scope.assert_in_scope(target)
        try:
            ipaddress.ip_address(target)
        except ValueError as exc:
            raise ScopeError("Port targets must be approved bare IP addresses") from exc
        cdn = any(ctx.db.get_fact("cdn:" + row["domain"], False) for row in ctx.db.rows(
            "SELECT domain FROM dns_records WHERE value=?", (target,)))
        ports = scan_ports(cdn, settings.get("tcp", "1-65535"))
        if ctx.dry_run:
            for port in sorted(parse_ports(settings.get("tcp", "8765,8766"))):
                ctx.db.asset(Asset(host=target, ip=target, port=port, service="http", source="fixture"))
                count += 1
            continue
        engine = settings.get("engine", "nmap")
        if engine == "masscan":
            handle = ctx.jobs.run("masscan", [target, "-p" + ports, "--rate",
                str(ctx.config.get("rates", {}).get("masscan_rate", 1000)), "-oJ", "{job}/masscan.json"],
                stage="6", timeout=ctx.config.get("limits", {}).get("masscan_timeout", 14400),
                root=True, background=True)
            pending.append((target, ports, cdn, engine, handle))
        else:
            udp = settings.get("udp", "")
            if udp:
                parse_ports(udp)
            scan_args = ["-sS", "-sU"] if udp else ["-sS"]
            port_spec = f"T:{ports},U:{udp}" if udp else ports
            args = (["-6"] if ipaddress.ip_address(target).version == 6 else []) + scan_args + [
                    "-sV", "-sC", "-Pn", "-n", "--host-timeout", "120s", "-p", port_spec,
                    "-oX", "{job}/nmap.xml", target]
            handle = ctx.jobs.run("nmap", args, stage="6", root=True, timeout=180, background=True)
            pending.append((target, ports, cdn, "nmap", handle))
    ctx.jobs.wait_all()
    for target, ports, cdn, engine, handle in pending:
        if handle.rc != 0:
            notes.append(f"{engine} failed for {target}, rc={handle.rc}")
            continue
        if engine == "masscan":
            import json
            raw = json.loads((ctx.jobs.result_dir(handle) / "masscan.json").read_text(encoding="utf-8"))
            opened = sorted({int(p["port"]) for row in raw for p in row.get("ports", []) if p.get("proto") == "tcp"})
            if honeypot(opened, parse_ports(ports)):
                ctx.note("honeypot", target, "All requested ports open; subsequent probes skipped")
                continue
            if not opened:
                continue
            ctx.scope.assert_in_scope(target)
            family = ["-6"] if ipaddress.ip_address(target).version == 6 else []
            handle = ctx.jobs.run("nmap", family + ["-sS", "-sCV", "-Pn", "-n", "-p", ",".join(map(str, opened)),
                                          "-oX", "{job}/nmap.xml", target], stage="6", root=True, timeout=180)
            ctx.jobs.wait(handle)
        assets = list(parse_nmap(ctx.jobs.result_dir(handle) / "nmap.xml"))
        if honeypot([a.port for a in assets if a.proto == "tcp"], parse_ports(ports)):
            ctx.note("honeypot", target, "All requested ports open; subsequent probes skipped")
            continue
        for asset in assets:
            asset.cdn = int(cdn)
            ctx.db.asset(asset)
            count += 1
    ctx.db.fact("ip_clusters", clusters(ctx.db.rows("SELECT host,ip FROM assets WHERE ip!=''")))
    return StageResult("partial" if notes else "completed", count, notes)
