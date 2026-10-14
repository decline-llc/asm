"""Keep the committed tool version/integration matrix honest.

The matrix in docs/reference/tool-versions.md exists because tool versions used to
live only in Git-ignored evidence, and because per-tool reference docs drifted: they
kept saying "installed, not wired into the pipeline" long after the adapters existed.
These tests bind the matrix to the code (external_tools.SUPPORTED) and to the pinned
binary versions (tools/tool-lock.json), so drift fails here instead of misleading the
next operator.
"""
import json
from pathlib import Path

from asm import external_tools

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs/reference/tool-versions.md"
LOCK = ROOT / "tools/tool-lock.json"
STATES = {"Stage 4", "Stage 5", "Stage 6", "Stage 7/broker", "人工", "运行时依赖", "未接入"}
# Adapter names that do not share their reference document's name.
DOC_NAMES = {"dig_probe": "dig"}
# Phrases that assert a tool is NOT wired into the pipeline. Manual-file caveats
# ("人工 JSONL 不自动入库") stay allowed: those remain true.
STALE_CLAIMS = ("未接入", "无自动调度", "未自动调度", "仅安装", "当前不自动入库")


def matrix_rows():
    rows = {}
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 5 or cells[0] in {"工具", "---"} or set(cells[0]) <= {"-"}:
            continue
        rows[cells[0]] = {"version": cells[1], "state": cells[2], "location": cells[3], "evidence": cells[4]}
    return rows


def test_matrix_versions_match_the_pinned_tool_lock():
    locked = {row["name"]: row["version"] for row in json.loads(LOCK.read_text(encoding="utf-8"))["binaries"]}
    rows = matrix_rows()
    for name, version in locked.items():
        assert name in rows, f"{name} is pinned in tool-lock.json but missing from the version matrix"
        assert rows[name]["version"] == version, f"{name} version drifted from tool-lock.json"


def test_matrix_states_use_the_declared_vocabulary():
    rows = matrix_rows()
    assert rows, "tool versions matrix has no rows"
    for name, row in rows.items():
        assert row["state"] in STATES, f"{name} has an undeclared integration state: {row['state']}"
        assert row["evidence"], f"{name} has no evidence reference"


def test_every_integrated_tool_is_recorded_as_connected():
    integrated = {tool for tools in external_tools.SUPPORTED.values() for tool in tools}
    rows = matrix_rows()
    for tool in sorted(integrated):
        assert tool in rows, f"{tool} is routed by external_tools.SUPPORTED but absent from the version matrix"
        assert rows[tool]["state"] != "未接入", f"{tool} is an integrated adapter but recorded as 未接入"
        assert rows[tool]["state"] != "人工", f"{tool} has an adapter but is recorded as manual only"


def test_integrated_tool_reference_docs_no_longer_claim_they_are_unwired():
    integrated = {tool for tools in external_tools.SUPPORTED.values() for tool in tools}
    for tool in sorted(integrated):
        name = DOC_NAMES.get(tool, tool)
        document = ROOT / "docs/reference" / (name + ".md")
        assert document.is_file(), f"missing reference doc for integrated tool {tool}"
        text = document.read_text(encoding="utf-8")
        for claim in STALE_CLAIMS:
            assert claim not in text, f"{name} reference doc still claims {claim}"
        assert "已接入" in text, f"{name} reference doc does not state that the adapter is wired in"