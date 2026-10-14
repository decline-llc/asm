import json
import shutil
import threading

import httpx
import pytest

from asm.api import create_server
from asm.orchestrator import Workbench
from tests.unit.test_orchestrator import configuration, local_asset


@pytest.fixture
def api_server(tmp_path, project, monkeypatch):
    from asm.api import PROVIDERS
    for keys in PROVIDERS.values():
        for key in keys:
            monkeypatch.delenv(key, raising=False)
    (tmp_path / "profiles").mkdir()
    shutil.copy(project / "profiles/modes.yaml", tmp_path / "profiles/modes.yaml")
    wb = Workbench(tmp_path, adapters={"web_visit": local_asset})
    server = create_server(tmp_path, port=0, workbench=wb)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield server, wb, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_api_projects_real_run_files_and_event_reconnect(api_server):
    server, wb, base = api_server
    with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
        modes = client.get("/api/modes").json()
        assert set(modes["presets"]) == {"passive_discovery", "authorized_verify", "full_asm"}
        response = client.post("/api/projects", json=configuration(["http://localhost:8765"]))
        assert response.status_code == 201
        project = response.json()
        assert project["path"].endswith("local-unit.yaml")
        preview = client.get("/api/projects/unit/plan").json()
        assert preview["steps"][0]["target"] == "http://localhost:8765"
        assert preview["steps"][0]["can_execute"]
        assert not wb.store.rows("SELECT * FROM runs")
        run = wb.start(project["project_id"], background=False)
        api_run = client.get("/api/projects/unit/run").json()
        assert api_run["run_id"] == run["run_id"]
        artifacts = client.get(f"/api/runs/{run['run_id']}/artifacts").json()
        reports = [f for f in artifacts if "exports/" in f["path"] and "/tables/" not in f["path"] and f["path"].endswith((".html", ".md", ".csv"))]
        assert len(reports) == 6
        trace = client.get(f"/api/runs/{run['run_id']}/files", params={"path": "logs/tool-calls.jsonl"})
        calls = [json.loads(line) for line in trace.text.splitlines()]
        last_event = wb.store.events(run["run_id"])[-1]["id"]
        with client.stream("GET", f"/api/runs/{run['run_id']}/events", headers={"Last-Event-ID": str(calls[0]["id"] - 1)}) as stream:
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    assert event["id"] >= calls[0]["id"]
                    break
        with client.stream("GET", f"/api/runs/{run['run_id']}/events", headers={"Last-Event-ID": str(last_event)}) as stream:
            assert next(stream.iter_lines()).startswith(": keepalive")
        assert client.get(f"/api/runs/{run['run_id']}/files", params={"path": "../../.env"}).status_code == 400
        html_path = next(f["path"] for f in reports if "/professional/" in f["path"] and f["path"].endswith(".html"))
        linked = client.get(f"/api/runs/{run['run_id']}/content/{html_path}")
        assert linked.status_code == 200 and "专业调查报告" in linked.text
        assert "default-src 'none'" in linked.headers["content-security-policy"]
        assert client.get(f"/api/runs/{run['run_id']}/content/%2e%2e/%2e%2e/.env").status_code == 400
        reviewed = client.post(f"/api/runs/{run['run_id']}/review", json={"asset_id": run["assets"][0]["asset_id"], "status": "reviewed", "note": "Owned fixture evidence reviewed"})
        assert reviewed.status_code == 200 and reviewed.json()["review_status"] == "reviewed"
        package = client.post(f"/api/runs/{run['run_id']}/bundle", json={})
        assert package.status_code == 200 and package.json()["path"].endswith(".zip")


def test_api_secrets_are_masked_json_csrf_and_input_constraints(api_server):
    _server, _wb, base = api_server
    with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
        value = "FIXTURE_PRIVATE_KEY_NEVER_RETURN"
        response = client.put("/api/settings", json={"credentials": {"FOFA_EMAIL": "fixture@example.invalid", "FOFA_KEY": value}})
        assert response.status_code == 200 and value not in response.text
        status = client.get("/api/settings")
        assert value not in status.text and "fixture@example.invalid" not in status.text
        assert status.json()["providers"]["fofa"]["configured"] is True
        assert client.post("/api/projects", content="{}", headers={"Content-Type": "text/plain"}).status_code == 400
        assert client.get("/api/settings", headers={"Origin": "http://evil.invalid"}).status_code == 400
        assert client.put("/api/settings", json={"credentials": {"unknown_secret": "fixture"}}).status_code == 400
        assert client.post("/api/settings/test", json={"provider": "shodan"}).json()["status"] == "credentials_missing"


def test_api_manual_scope_is_investigation_only(api_server):
    _server, _wb, base = api_server
    with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
        client.post("/api/projects", json=configuration(["http://localhost:8765"]))
        updated = client.post("/api/projects/unit/scope", json={"value": "example.invalid"}).json()
        assert "example.invalid" in updated["config"]["scope_sets"]["investigation"]["include"]
        assert "example.invalid" not in updated["config"]["scope_sets"]["verification"]["include"]


def test_api_project_list_defaults_to_business_and_supports_test_archive(api_server):
    _server, wb, base = api_server
    wb.save_project(configuration([]))
    fixture = configuration([])
    fixture["profile"] = "ui_fixture_20261011_112731"
    wb.save_project(fixture)
    with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
        assert [item["project_id"] for item in client.get("/api/projects").json()] == ["unit"]
        assert len(client.get("/api/projects?purpose=all").json()) == 2
        assert client.get("/api/projects?purpose=validation").json()[0]["purpose"] == "validation"
        assert client.get("/api/projects?purpose=unknown").status_code == 400
