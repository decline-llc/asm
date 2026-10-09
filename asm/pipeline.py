import importlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .bridge import Bridge, JobManager
from .conf import load_config
from .db import Database
from .models import utcnow
from .scope import Scope, ScopeError

STAGES = {
    "1": "stages.s1_seed", "2a": "stages.s2a_equity", "2b": "stages.s2b_icp",
    "3": "stages.s3_scope", "4": "stages.s4_subdomain", "5": "stages.s5_dns_cdn",
    "6": "stages.s6_port", "7": "stages.s7_web", "8": "stages.s8_report",
    "p1": "parallel.p1_osint", "p2": "parallel.p2_supply",
}


@dataclass
class StageResult:
    status: str = "completed"
    count: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class StageContext:
    profile: object
    db: Database
    bridge: Bridge
    jobs: JobManager
    scope: Scope
    stage_dir: Path
    passive_only: bool = False
    target_local: bool = False
    dry_run: bool = False

    @property
    def config(self):
        return self.profile.data

    def note(self, kind, target, evidence, severity="info"):
        self.db.finding({"kind": kind, "url": target, "evidence": evidence,
                         "severity": severity, "status": "review"})

    def write(self, name, value):
        path = self.stage_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run_pipeline(profile="default", stages=None, *, root=None, passive_only=False,
                 target_local=False, dry_run=False, resume=False, on_result=None):
    config = load_config(profile, root)
    scope = Scope(config.data, passive_only=passive_only, target_local=target_local)
    explicit = stages is not None
    stages = list(stages or STAGES)
    if any(stage not in STAGES for stage in stages):
        raise ValueError("Unknown stage; use 1,2a,2b,3,4,5,6,7,8,p1,p2")
    if passive_only or not scope.authorized:
        if explicit and any(s in {"6", "7"} for s in stages) and not dry_run:
            raise ScopeError("Stages 6/7 need authorization=true and active mode")
        stages = [s for s in stages if s not in {"6", "7"}]
    output = config.output / "dry-run" if dry_run else config.output
    output.mkdir(parents=True, exist_ok=True)
    fingerprint = config.fingerprint(passive_only, target_local) + (":dry-run" if dry_run else "")
    result = {}
    with Database(output / "asm.db") as db:
        bridge = Bridge()
        jobs = JobManager(bridge, db, output)
        if resume and db.rows("SELECT 1 FROM jobs WHERE status='running'"):
            jobs.recover()
            jobs.wait_all(max_seconds=1)
        for stage in stages:
            if resume and db.completed(fingerprint, stage):
                stage_result = StageResult("skipped", notes=["Previously completed for this exact configuration"])
            else:
                db.state(fingerprint, stage, "running")
                ctx = StageContext(config, db, bridge, jobs, scope, output / "stages" / stage,
                                   passive_only, target_local, dry_run)
                ctx.stage_dir.mkdir(parents=True, exist_ok=True)
                try:
                    stage_result = importlib.import_module("asm." + STAGES[stage]).run(ctx)
                except ScopeError:
                    db.state(fingerprint, stage, "failed")
                    raise
                except Exception as exc:
                    stage_result = StageResult("failed", notes=[f"{type(exc).__name__}: {exc}"])
                    ctx.note("stage_error", stage, stage_result.notes[0])
                db.state(fingerprint, stage, stage_result.status)
            result[stage] = asdict(stage_result)
            if on_result:
                on_result(stage, stage_result)
            log = output / "logs" / "pipeline.jsonl"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"ts": utcnow(), "stage": stage, **asdict(stage_result)},
                                        ensure_ascii=False) + "\n")
        # Long tools remain recoverable if interrupted. Final drain precedes exit.
        if jobs.handles:
            jobs.wait_all()
        db.fact("last_run", {"profile": fingerprint, "dry_run": dry_run, "stages": result})
    return result
