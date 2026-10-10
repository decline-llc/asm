"""Native WSL dig worker. Only stdlib; shared support arrives through job stdin."""
import argparse
import concurrent.futures
import json
import math
import subprocess
from pathlib import Path

from dns_support import RTYPES, dns_name, parse_dig, parse_endpoint


def query(domain, rtype, resolver, timeout):
    host, port = parse_endpoint(resolver)
    args = ["dig", "@" + host, "-p", str(port), domain + ".", rtype, "+noall", "+answer", "+comments",
            "+time=" + str(math.ceil(timeout)), "+tries=1"]
    result = {"domain": domain, "rtype": rtype, "resolver": resolver, "source": "dig", "error": ""}
    try:
        reply = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=timeout + 2)
        result.update(parse_dig(reply.stdout))
        if reply.returncode:
            result["status"], result["error"] = "ERROR", f"dig rc={reply.returncode}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.update(status="ERROR", answers=[], error=type(exc).__name__)
    return result


def collect(domain, resolver, timeout, max_hops):
    results = [query(domain, rtype, resolver, timeout) for rtype in RTYPES]
    current, chain, seen, state = domain, [], {domain}, "complete"
    first = next(r for r in results if r["rtype"] == "CNAME")
    reply = first
    for hop in range(max_hops + 1):
        if reply["status"] not in ("NOERROR", "NXDOMAIN"):
            state = "error"
            break
        if reply["status"] == "NXDOMAIN":
            state = "nxdomain"
            break
        values = [a["value"] for a in reply["answers"] if a["rtype"] == "CNAME"
                  and a["name"] == current]
        if not values:
            break
        if hop == max_hops:
            state = "max_hops"
            break
        try:
            current = dns_name(values[0])
        except ValueError:
            state = "invalid"
            break
        chain.append(current)
        if current in seen:
            state = "loop"
            break
        seen.add(current)
        reply = query(current, "CNAME", resolver, timeout)
        reply["origin"] = domain
        results.append(reply)
    results.append({"domain": domain, "resolver": resolver, "source": "dig", "kind": "cname_chain",
                    "chain": chain, "terminal": current, "status": state})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text())
    domains = [dns_name(v) for v in data["domains"]]
    for resolver in data["resolvers"]:
        parse_endpoint(resolver)
    tasks = [(domain, resolver) for domain in domains for resolver in data["resolvers"]]
    with Path(args.output).open("w", encoding="utf-8") as output, concurrent.futures.ThreadPoolExecutor(
            max_workers=data["workers"]) as executor:
        futures = [executor.submit(collect, d, r, data["timeout"], data["max_hops"]) for d, r in tasks]
        for future in concurrent.futures.as_completed(futures):
            for result in future.result():
                output.write(json.dumps(result) + "\n")
                output.flush()


if __name__ == "__main__":
    main()
