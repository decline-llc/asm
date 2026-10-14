"""把 JUnit 报告中的失败用例转成 GitHub Actions 注解，便于在检查页面直接看到失败测试与出错位置。

用法：python scripts/ci_report_failures.py [test-results.xml]

日志下载需要仓库写权限，而检查注解匿名可读，因此这里输出 `::error file=...,line=...::`
工作流命令并定位到最深层栈帧；本地运行时加 `[local]` 前缀以便肉眼区分，且始终返回 0，
避免诊断步骤本身改变任务结论。
"""
from __future__ import annotations

import os
import re
import sys
from xml.etree import ElementTree

DEFAULT_PATH = "test-results.xml"
MAX_MESSAGE = 200
FAILURE_TAGS = ("failure", "error")
# pytest ends the failure text with the deepest frame, e.g. "asm\utils\dns.py:99: ValueError".
TRAILING_FRAME = re.compile(r"^(.+\.py):(\d+):")


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _summary(node: ElementTree.Element) -> str:
    text = (node.get("message") or node.text or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return _escape((lines or ["failed"])[0][:MAX_MESSAGE])


def _location(node: ElementTree.Element) -> tuple[str, str] | None:
    """Deepest frame pytest printed, as (repo-relative path, line)."""
    lines = [line.strip() for line in (node.text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        match = TRAILING_FRAME.match(line)
        if match:
            return match.group(1).replace("\\", "/"), match.group(2)
    return None


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else DEFAULT_PATH
    if not os.path.exists(path):
        print(f"ci_report_failures: {path} not found; nothing to report")
        return 0
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as exc:
        print(f"ci_report_failures: cannot parse {path}: {exc}")
        return 0
    prefix = "" if os.environ.get("GITHUB_ACTIONS") else "[local] "
    total = failed = 0
    for case in root.iter("testcase"):
        total += 1
        problems = [child for child in case if child.tag in FAILURE_TAGS]
        if not problems:
            continue
        failed += 1
        where = f"{case.get('classname')}::{case.get('name')}"
        location = _location(problems[0])
        if location:
            # The location also stays readable inside the message: GitHub may drop the
            # file/line properties of a workflow command.
            where = f"{where} at {location[0]}:{location[1]}"
        target = f" file={location[0]},line={location[1]}" if location else ""
        print(f"{prefix}::error{target}::FAILED {where} - {_summary(problems[0])}")
    print(f"ci_report_failures: {failed} failed of {total} cases in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
