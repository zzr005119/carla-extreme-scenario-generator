"""运行场景参数级物理约束检查并输出 JSON 报告。"""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.physical_constraints import (  # noqa: E402
    build_physical_constraint_report,
    load_json_records,
)


def parse_args():
    parser = argparse.ArgumentParser(description="检查生成场景的参数级物理约束")
    parser.add_argument("path", help="单个 JSON 或 JSONL 场景记录")
    parser.add_argument("--output", help="可选 JSON 报告路径")
    parser.add_argument("--strict", action="store_true", help="存在硬约束失败时返回非零")
    return parser.parse_args()


def main():
    args = parse_args()
    source = Path(args.path).resolve()
    report = build_physical_constraint_report(load_json_records(source), source=source)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(f"[PHYSICAL] 报告: {output}")
    print(
        f"[PHYSICAL] records={report['record_count']} "
        f"valid={report['valid_count']} invalid={report['invalid_count']} "
        f"warnings={report['warning_count']}"
    )
    if args.strict and report["invalid_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
