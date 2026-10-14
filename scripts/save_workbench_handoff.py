"""Replace the current local handoff without modifying confirmed requirements."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    prompt = root / "docs/audits/CHATGPT_NEXT_ROUND_PROMPT.md"
    source = prompt.read_text(encoding="utf-8")
    start = source.index("### 10.3 当前接力记录")
    end = source.index("### 10.4 恢复口令", start)
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    archive = root / "data/validation/workbench-20261011/handoff-history"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / f"handoff-{stamp}.md").write_text(source[start:end], encoding="utf-8")
    record = args.record.read_text(encoding="utf-8").strip()
    assert record.startswith("### 10.3 当前接力记录")
    prompt.write_text(source[:start] + record + "\n\n" + source[end:], encoding="utf-8")
    print(f"Saved current handoff; previous record: {archive / ('handoff-' + stamp + '.md')}")


if __name__ == "__main__":
    main()
