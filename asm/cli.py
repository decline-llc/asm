import json
import os
import runpy
from pathlib import Path

import click
from dotenv import load_dotenv

from .conf import load_config
from .db import Database
from .pipeline import STAGES, run_pipeline
from .scope import ScopeError

os.environ.setdefault("PYTHONUTF8", "1")


@click.group()
@click.version_option(package_name="asm-workbench")
def main():
    """Windows orchestration with native WSL tools and a persisted audit trail."""
    load_dotenv(Path.cwd() / ".env", override=False)


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
    click.echo(deploy(distro or os.getenv("WSL_DISTRO", "Ubuntu-22.04"), os.getenv("WSL_USER", ""), not transfer_only))


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
    """Export trusted assets to the contractual 8-sheet workbook."""
    from .stages.s8_report import write_report
    config = load_config(profile)
    directory = config.output / "dry-run" if dry_run else config.output
    if not (directory / "asm.db").is_file():
        raise click.ClickException("No project database; run collection first")
    output = output or directory / "report.xlsx"
    with Database(directory / "asm.db") as db:
        counts = write_report(db, output)
    click.echo(str(output.resolve()))
    click.echo(json.dumps(counts, ensure_ascii=False))


@main.command()
@click.option("--profile", default="default")
def quota(profile):
    """Show quota ledger; no API call and no credentials are displayed."""
    config = load_config(profile)
    with Database(config.output / "asm.db") as db:
        click.echo(json.dumps(db.rows("SELECT * FROM sources ORDER BY day,source"), ensure_ascii=False, indent=2))
