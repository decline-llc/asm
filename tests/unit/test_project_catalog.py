import hashlib
import shutil
from pathlib import Path

import pytest

from asm.conf import load_config
from asm.orchestrator import Workbench
from asm.run_store import digest, encode
from scripts.organize_projects import organize
from tests.unit.test_orchestrator import configuration, local_asset


@pytest.fixture
def workbench_root(tmp_path, project):
    (tmp_path / "profiles").mkdir()
    shutil.copy(project / "profiles/modes.yaml", tmp_path / "profiles/modes.yaml")
    return tmp_path


def test_business_replay_and_local_projects_are_not_test_records(workbench_root):
    wb = Workbench(workbench_root, recover=False)
    business = configuration([])
    business.update(profile="customer_review", name="企业互联网暴露面调查")
    business["execution"]["source"] = "replay"
    wb.save_project(business)
    validation = configuration([])
    validation.update(profile="ui_fixture_20261011_112731")
    wb.save_project(validation)
    assert [p["project_id"] for p in wb.projects("investigation")] == ["customer_review"]
    assert [p["project_id"] for p in wb.projects("validation")] == [validation["profile"]]
    assert load_config("local-customer_review", workbench_root).name == "customer_review"
    with pytest.raises(ValueError):
        wb.save_project({**business, "project_purpose": "unknown"})


def test_validation_workspace_does_not_pollute_business_catalog(workbench_root):
    business = Workbench(workbench_root, recover=False)
    testing = Workbench(workbench_root, recover=False, validation=True)
    item = testing.save_project(configuration([]))
    assert item["purpose"] == "validation"
    assert Path(item["path"]).parent.name == "validation"
    assert not business.projects()
    assert len(testing.projects()) == 1


def test_profile_organization_keeps_configuration_and_historical_evidence(workbench_root):
    wb = Workbench(workbench_root, adapters={"web_visit": local_asset}, recover=False)
    config = configuration(["http://localhost:8765"])
    config["profile"] = "lab_native_20261011_055655"
    item = wb.save_project(config)
    # Simulate the legacy layout, including the database reference.
    source = workbench_root / "profiles" / Path(item["path"]).name
    Path(item["path"]).replace(source)
    with wb.store.connection() as conn:
        conn.execute("UPDATE projects SET path=? WHERE id=?", (str(source), item["project_id"]))
    run = wb.start(item["project_id"], background=False)
    before = digest(wb.run(run["run_id"]))
    original_config = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path(run["directory"]).rglob("*") if p.is_file()}
    plan = organize(workbench_root)
    assert not plan["applied"] and source.exists()
    migrated = organize(workbench_root, apply=True)
    updated = wb.project(item["project_id"])
    assert migrated["moved"] == 1 and migrated["history_state_unchanged"]
    assert Path(updated["path"]).parent.name == "validation" and not source.exists()
    assert hashlib.sha256(Path(updated["path"]).read_bytes()).hexdigest() == original_config
    assert digest(wb.run(run["run_id"])) == before
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == checksum for p, checksum in evidence.items())
    assert organize(workbench_root, apply=True)["moved"] == 0


def test_legacy_invalid_config_remains_visible_only_in_its_category(workbench_root):
    wb = Workbench(workbench_root, recover=False)
    with wb.store.connection() as conn:
        conn.execute("INSERT INTO projects VALUES(?,?,?,?,?)",
                     ("ui_fixture_20261011_112731", str(workbench_root / "missing.yaml"), 1, encode({}), "2026-10-11"))
    assert not wb.projects("investigation")
    assert wb.projects("validation")[0]["status"] == "invalid_config"
