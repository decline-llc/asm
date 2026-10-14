import json
import os
import runpy
import sys
import sqlite3
from pathlib import Path

import click

from .conf import load_config
from .db import Database
from .pipeline import STAGES, run_pipeline
from .scope import ScopeError

os.environ.setdefault("PYTHONUTF8", "1")


@click.group()
@click.version_option(package_name="asm-workbench")
def main():
    """Windows orchestration with native WSL tools and a persisted audit trail."""
    # PYTHONUTF8 set after interpreter startup does not change existing streams.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


@main.command()
@click.option("--json-output", is_flag=True)
def doctor(json_output):
    """Run the 18 deployment checks without printing credentials."""
    from .doctor import doctor as inspect
    checks = inspect()
    if json_output:
        click.echo(json.dumps(checks, ensure_ascii=False, indent=2))
    else:
        for check in checks:
            click.echo(f"[{check['id']:02}] {'PASS' if check['ok'] else 'FAIL'} {check['name']}: {check['detail']}")
            if not check["ok"]:
                click.echo("  Repair: " + check["repair"])
        click.echo(f"{sum(c['ok'] for c in checks)}/18 passed")
    if not all(c["ok"] for c in checks):
        raise click.exceptions.Exit(1)


@main.command("init-wsl")
@click.option("--distro", default=None)
@click.option("--transfer-only", is_flag=True)
def init_wsl(distro, transfer_only):
    """Install pinned external tools in WSL's native filesystem."""
    path = Path(__file__).resolve().parents[1] / "scripts/deploy-wsl.py"
    deploy = runpy.run_path(str(path))["deploy"]
    click.echo(deploy(distro or os.getenv("WSL_DISTRO", "Ubuntu"), os.getenv("WSL_USER", ""), not transfer_only))


def run_options(func):
    for option in reversed([
        click.option("--profile", default="default", show_default=True),
        click.option("--stages", default=None, help="Comma-separated: " + ",".join(STAGES)),
        click.option("--passive-only", is_flag=True), click.option("--target-local", is_flag=True),
        click.option("--dry-run", is_flag=True, help="Fixture replay in a separate dry-run database"),
        click.option("--resume", is_flag=True),
    ]):
        func = option(func)
    return func


@main.command()
@run_options
def run(profile, stages, passive_only, target_local, dry_run, resume):
    """Run selected stages; failed/partial stages remain resumable."""
    try:
        config = load_config(profile, load_secrets=False)
        if config.data.get("schema_version") == 2:
            from .orchestrator import Workbench
            wb = Workbench(config.root)
            project = wb.import_project(profile)
            if resume:
                previous = wb.store.rows("SELECT id FROM runs WHERE project=? ORDER BY started DESC,rowid DESC LIMIT 1", (project["project_id"],))
                if not previous:
                    raise ValueError("No existing run to resume")
                current = wb.resume(previous[0]["id"], background=False)
            else:
                stage_caps = {"1": [], "3": [], "8": [], "2a": ["company_lookup"], "2b": ["company_lookup"],
                    "4": ["passive_subdomains", "dns_enum"], "5": ["dns_recursive", "takeover_probe"],
                    "6": ["tcp_scan", "udp_scan", "service_probe", "deep_service_probe"],
                    "7": ["web_visit", "tls_inspect", "screenshot", "web_crawl", "js_analysis", "web_path_enum", "exposure_check", "vulnerability_check", "auth_audit"],
                    "p1": ["osint"], "p2": ["passive_supply_chain"]}
                selected = None
                if stages:
                    if any(s not in stage_caps for s in stages.split(",")):
                        raise ValueError("Unknown stage")
                    selected = [c for s in stages.split(",") for c in stage_caps[s]]
                current = wb.start(project["project_id"], source="replay" if dry_run else None,
                    background=False, selected_capabilities=selected, passive_only=passive_only, target_local=target_local)
            click.echo(json.dumps(current, ensure_ascii=False, indent=2))
            if current["status"] != "completed":
                raise click.exceptions.Exit(1)
            return
        results = run_pipeline(profile, stages.split(",") if stages else None, passive_only=passive_only,
            target_local=target_local, dry_run=dry_run, resume=resume,
            on_result=lambda s, r: click.echo(f"{s}: {r.status}, count={r.count} " + "; ".join(r.notes)))
    except (ValueError, ScopeError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    if any(r["status"] in {"failed", "partial"} for r in results.values()):
        raise click.exceptions.Exit(1)


@main.command()
@click.argument("stage_name", type=click.Choice(list(STAGES)))
@click.option("--profile", default="default")
@click.option("--passive-only", is_flag=True)
@click.option("--target-local", is_flag=True)
@click.option("--dry-run", is_flag=True)
def stage(stage_name, profile, passive_only, target_local, dry_run):
    """Run one stage."""
    try:
        result = run_pipeline(profile, [stage_name], passive_only=passive_only, target_local=target_local, dry_run=dry_run)
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        if result[stage_name]["status"] != "completed":
            raise click.exceptions.Exit(1)
    except (ValueError, ScopeError) as exc:
        raise click.ClickException(str(exc)) from exc


@main.command()
@click.option("--profile", default="default")
@click.option("--output", type=click.Path(path_type=Path))
@click.option("--dry-run", is_flag=True)
def report(profile, output, dry_run):
    """Export the same eight tables to XLSX, CSV and standalone HTML."""
    from .stages.s8_report import report_paths, write_report
    config = load_config(profile, load_secrets=False)
    directory = config.output / "dry-run" if dry_run else config.output
    if not (directory / "asm.db").is_file():
        raise click.ClickException("No project database; run collection first")
    output = output or directory / "report.xlsx"
    try:
        paths = report_paths(output)
        with Database(directory / "asm.db") as db:
            counts = write_report(db, output)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    for kind, path in paths.items():
        click.echo(f"{kind}: {path.resolve()}")
    click.echo(json.dumps(counts, ensure_ascii=False))


@main.command()
@click.option("--profile", default="default")
@click.option("--db", "db_path", type=click.Path(path_type=Path), help="Read an existing ledger without creating files")
def quota(profile, db_path):
    """Show quota ledger; no API call and no credentials are displayed."""
    try:
        config = load_config(profile, load_secrets=False)
        path = (db_path or config.output / "asm.db").resolve()
        if not path.is_file():
            # Check the nearest existing directory rather than mkdir on a read-only command.
            parent = path.parent
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            next(parent.iterdir(), None)
            result = {"status": "no_ledger", "used": 0, "rows": [], "path": str(path)}
        else:
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY day,source")]
            result = {"status": "known", "rows": rows, "path": str(path)}
    except (OSError, sqlite3.Error, ValueError) as exc:
        result = {"status": "unknown", "used": None, "reason": type(exc).__name__}
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@main.command("serve")
@click.option("--port", default=6400, type=click.IntRange(1024, 65535))
def serve(port):
    """Start the persistent local workbench API and serve the built frontend."""
    from .api import serve as serve_api
    serve_api(Path.cwd(), port=port)


@main.command("workbench-run")
@click.option("--profile", required=True)
@click.option("--source", type=click.Choice(["live", "replay"]))
@click.option("--resume", "run_id", default=None, help="Resume the original run ID")
def workbench_run(profile, source, run_id):
    """Execute a configuration-driven run with persistent events and dual reports."""
    from .orchestrator import Workbench
    workbench = Workbench(Path.cwd())
    project = workbench.import_project(profile)
    run = workbench.resume(run_id, background=False) if run_id else workbench.start(project["project_id"], source=source, background=False)
    click.echo(json.dumps(run, ensure_ascii=False, indent=2))
    if run["status"] != "completed":
        raise click.exceptions.Exit(1)
