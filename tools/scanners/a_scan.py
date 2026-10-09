#!/usr/bin/env python3
"""WSL stdlib TCP fallback: scope-approved IPs only, no login or exploitation."""
import argparse
import concurrent.futures
import json
import socket


def scan(host, port, timeout):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"host": host, "port": port, "proto": "tcp", "service": "unknown"}
    except OSError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--ports", default="80,443,3000,8000,8080,8443,9090,9200")
    parser.add_argument("--timeout", type=float, default=1)
    parser.add_argument("--threads", type=int, default=64)
    args = parser.parse_args()
    ports = set()
    for token in args.ports.split(","):
        if "-" in token:
            low, high = map(int, token.split("-"))
            ports.update(range(low, high + 1))
        else:
            ports.add(int(token))
    if not ports or min(ports) < 1 or max(ports) > 65535:
        parser.error("Invalid ports")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        for item in executor.map(lambda p: scan(args.host, p, args.timeout), sorted(ports)):
            if item:
                print(json.dumps(item), flush=True)


if __name__ == "__main__":
    main()
