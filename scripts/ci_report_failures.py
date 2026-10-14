"""把 JUnit 报告中的失败用例转成 GitHub Actions 注解，便于在检查页面直接看到失败测试名。

用法：python scripts/ci_report_failures.py [test-results.xml]

只在真实 CI 中输出 `::error::` 工作流命令（本地运行加 `[local]` 前缀，便于肉眼区分）；
无论报告是否可读都返回 0，避免诊断步骤本身改变任务结论。日志下载需要仓库权限，
注解是匿名可读的，因此这里用注解而不是把完整回溯写进日志。
"""
from __future__ import annotations

import os
import sys
from xml.etree import ElementTree

DEFAULT_PATH = "test-results.xml"
MAX_MESSAGE = 220
FAILURE_TAGS = ("failure", "error")


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _first_line(node: ElementTree.Element) -> str:
    text = (node.get("message") or node.text or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return _escape((lines or ["failed"])[0][:MAX_MESSAGE])


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
        print(f"{prefix}::error::FAILED {where} - {_first_line(problems[0])}")
    print(f"ci_report_failures: {failed} failed of {total} cases in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
