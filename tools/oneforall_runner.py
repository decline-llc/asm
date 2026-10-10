"""Native isolated passive collector for the pinned OneForAll installation."""
import argparse
import copy
import importlib
import json
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from urllib.parse import urlsplit

from oneforall_support import PASSIVE_FLAGS, PASSIVE_MODULES, OneForAllSettings, domain_name

BODY_LIMIT = 8 * 1024 * 1024


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def configure_log(directory):
    # Upstream config.log writes beside vendor source; install an in-process log adapter first.
    from loguru import logger
    logger.remove()
    for name, number in (("INFOR", 20), ("QUITE", 25), ("ALERT", 30), ("FATAL", 50)):
        logger.level(name, no=number)
    logger.add(sys.stderr, level="INFOR")
    logger.add(directory / "oneforall.log", level="DEBUG", encoding="utf-8")
    module = types.ModuleType("config.log")
    module.logger = logger
    sys.modules["config.log"] = module


def install_http_guard(options, states, events, lock):
    import requests
    original = requests.sessions.Session.request
    module_names = {module.rsplit(".", 1)[-1]: module for module in options.modules}

    def request(session, method, url, **kwargs):
        name = module_names.get(threading.current_thread().name, "unknown")
        event = {"module": name, "url": str(url), "status": "error", "error": "", "http_status": None}
        reply = None
        try:
            parsed = urlsplit(url)
            if (name == "unknown" or method.upper() not in ("GET", "HEAD") or
                    parsed.scheme not in ("http", "https") or parsed.username or parsed.password or
                    parsed.hostname != PASSIVE_MODULES[name] or parsed.port not in (None, 80, 443)):
                raise ValueError("Request is outside the selected passive provider")
            kwargs.update(allow_redirects=False, timeout=(min(5, options.request_timeout), options.request_timeout),
                          verify=True, stream=True)
            reply = original(session, method, url, **kwargs)
            event["http_status"] = reply.status_code
            chunks, size = [], 0
            for chunk in reply.iter_content(65536):
                size += len(chunk)
                if size > BODY_LIMIT:
                    raise ValueError("Passive provider response exceeds 8 MiB")
                chunks.append(chunk)
            reply._content, reply._content_consumed = b"".join(chunks), True
            if not 200 <= reply.status_code < 300:
                raise ValueError("Passive provider returned a non-success status")
            event["status"] = "completed"
            return reply
        except Exception as exc:
            event["error"] = type(exc).__name__
            raise
        finally:
            if reply is not None:
                reply.close()
            with lock:
                events.append(event)
                if name in states and event["status"] != "completed":
                    states[name]["errors"].append(event)
    requests.sessions.Session.request = request


def collect(plan, directory, report):
    root = domain_name(plan["root"])
    options = OneForAllSettings.from_config({"oneforall": plan["settings"]})
    vendor = Path(plan["vendor"]).resolve()
    if not str(vendor).startswith("/") or str(vendor).startswith("/mnt/"):
        raise ValueError("OneForAll must reside on the native Linux filesystem")
    commit = subprocess.run(["git", "-C", str(vendor), "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True).stdout.strip()
    if commit != plan["expected_commit"]:
        raise ValueError("Installed OneForAll does not match the tool lock")
    report.update(root=root, vendor_commit=commit, settings=options.as_config())
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(vendor))
    configure_log(directory)
    from config import settings
    result_dir = directory / "vendor-results"
    result_dir.mkdir(exist_ok=True)
    settings.result_save_dir, settings.temp_save_dir = result_dir, result_dir / "temp"
    settings.enable_all_module, settings.enable_partial_module = False, list(options.modules)
    settings.module_thread_timeout = options.module_timeout
    settings.request_timeout_second = (min(5, options.request_timeout), options.request_timeout)
    settings.enable_check_version = settings.enable_request_proxy = False
    settings.enable_brute_module = settings.enable_dns_resolve = settings.enable_http_request = False
    settings.enable_finder_module = settings.enable_altdns_module = settings.enable_enrich_module = False
    settings.enable_takeover_check, settings.save_module_result = False, True
    settings.request_allow_redirect, settings.request_ssl_verify = False, True
    states = {name: {"status": "pending", "errors": [], "exception": ""} for name in options.modules}
    events, lock = [], threading.Lock()
    install_http_guard(options, states, events, lock)
    from modules.collect import Collect
    from common import utils
    from oneforall import OneForAll
    if "modules.intelligence.alienvault" in options.modules:
        from modules.intelligence.alienvault import AlienVault
        original_collect = AlienVault.collect_subdomains

        def merge_endpoints(self, *args, **kwargs):
            return self.subdomains | original_collect(self, *args, **kwargs)
        # The pinned module assigns each endpoint response over its previous result.
        AlienVault.collect_subdomains = merge_endpoints
    utils.init_table(root)
    collector = Collect(root)

    def wrapped(name, function):
        def run(domain):
            with lock:
                states[name]["status"] = "running"
            try:
                function(domain)
            except (Exception, SystemExit) as exc:
                with lock:
                    states[name]["exception"] = type(exc).__name__
            finally:
                with lock:
                    state = states[name]
                    state["status"] = "partial" if state["errors"] or state["exception"] else "completed"
        return run

    def import_functions():
        collector.collect_funcs = [[wrapped(name, importlib.import_module(name).run), name.rsplit(".", 1)[-1]]
                                   for name in collector.modules]
    collector.import_func = import_functions
    collector.run()
    with lock:
        for state in states.values():
            if state["status"] == "running":
                state["status"] = "timed_out"
        report.update(modules=copy.deepcopy(states), requests=copy.deepcopy(events))
    observations = utils.get_data(root)
    write_json(directory / "oneforall-observations.json", observations)
    utils.deal_data(root)
    # Avoid upstream run/main's unconditional wildcard/SRV queries and registrable-domain widening.
    engine = OneForAll(target=root, brute=False, dns=False, req=False, alive=False, fmt="json",
                       path=str(directory / "oneforall.json"), takeover=False)
    engine.domain = root
    engine.config_param()
    engine.check_param()
    engine.export_data()
    report["count"] = len(json.loads((directory / "oneforall.json").read_text(encoding="utf-8")))
    report["status"] = "completed" if all(state["status"] == "completed" for state in report["modules"].values()) else "partial"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    directory = Path.cwd().resolve()
    input_path = Path(args.input).resolve()
    if not input_path.is_relative_to(directory):
        raise ValueError("Job input must be inside the native job directory")
    plan = json.loads(input_path.read_text(encoding="utf-8"))
    report = {"mode": "passive", "entrypoint": "Collect + OneForAll.export_data", "root": plan.get("root"),
              "status": "running", "modules": {}, "requests": [], "flags": dict.fromkeys(PASSIVE_FLAGS, False)}
    write_json(directory / "oneforall-run.json", report)
    start = time.monotonic()
    try:
        collect(plan, directory, report)
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        print(report["error"], file=sys.stderr)
    finally:
        report["elapsed"] = round(time.monotonic() - start, 3)
        write_json(directory / "oneforall-run.json", report)
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
