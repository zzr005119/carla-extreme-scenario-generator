"""按风险、生成器、证据和质量字段查询极端场景库。"""

import argparse
import csv
import json
import os
import sys

# Allow the CLI to import the shared core package when launched as a script.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_query import (
    matches as controlled_matches,
    sort_entries as controlled_sort_entries,
    spec_from_mapping,
)

DEFAULT_LIBRARY = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "scenario_library_v1",
    "entries.jsonl",
)


OUTPUT_FIELDS = (
    "library_id",
    "sample_id",
    "generators",
    "target_risk_levels",
    "observed_risk_level",
    "risk_score_mean",
    "collision_observed",
    "verification_basis",
    "evidence_granularity",
    "carla_versions",
    "quality_tier",
    "operational_quality",
    "diversity_score",
)


def parse_args():
    parser = argparse.ArgumentParser(description="查询极端场景库 V1")
    parser.add_argument("--library", default=DEFAULT_LIBRARY)
    parser.add_argument("--generator")
    parser.add_argument(
        "--target-risk",
        choices=("low", "medium", "high", "critical"),
    )
    parser.add_argument(
        "--observed-risk",
        choices=("low", "medium", "high", "critical"),
    )
    parser.add_argument("--collision", choices=("yes", "no"))
    parser.add_argument(
        "--evidence-granularity",
        choices=("run_level", "aggregate"),
    )
    parser.add_argument(
        "--verification-basis",
        choices=("direct_run_evidence", "inherited_batch_acceptance"),
    )
    parser.add_argument("--carla-version", help="使用 unknown 查询未记录版本的条目")
    parser.add_argument("--quality-tier", choices=("bronze", "silver", "gold"))
    parser.add_argument("--weather-tag", action="append", default=[])
    parser.add_argument("--hazard-tag", action="append", default=[])
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="在样本标识、生成器、风险/天气/危险标签和证据字段中做受控关键词匹配",
    )
    parser.add_argument("--min-score", type=float)
    parser.add_argument("--max-score", type=float)
    parser.add_argument("--min-diversity", type=float)
    parser.add_argument(
        "--sort",
        choices=(
            "risk_desc",
            "risk_asc",
            "diversity_desc",
            "quality_desc",
            "sample_id",
        ),
        default="risk_desc",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=("table", "csv", "jsonl"), default="table")
    parser.add_argument("--output")
    return parser.parse_args()


def load_entries(path):
    entries = []
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: JSON 解析失败") from exc
    return entries


def matches(entry, args):
    return controlled_matches(entry, spec_from_mapping(vars(args)))


def sort_entries(entries, mode):
    return controlled_sort_entries(entries, mode)


def flatten_entry(entry):
    labels = entry["labels"]
    evidence = entry["execution_evidence"]
    risk = entry["observed_risk"]
    quality = entry["quality"]
    return {
        "library_id": entry["library_id"],
        "sample_id": entry["canonical_sample_id"],
        "generators": ";".join(labels["generators"]),
        "target_risk_levels": ";".join(labels["target_risk_levels"]),
        "observed_risk_level": labels["observed_risk_level"],
        "risk_score_mean": round(risk["score_mean"], 3),
        "collision_observed": risk["collision_observed"],
        "verification_basis": evidence["verification_basis"],
        "evidence_granularity": evidence["evidence_granularity"],
        "carla_versions": ";".join(evidence["carla_versions"]) or "unknown",
        "quality_tier": quality["tier"],
        "operational_quality": round(quality["operational_score"], 3),
        "diversity_score": round(quality["diversity"]["score"] or 0.0, 3),
    }


def render_table(rows):
    headers = (
        "sample_id",
        "generators",
        "target_risk_levels",
        "observed_risk_level",
        "risk_score_mean",
        "collision_observed",
        "evidence_granularity",
        "quality_tier",
    )
    widths = {
        header: max(len(header), *(len(str(row[header])) for row in rows))
        for header in headers
    }
    return "\n".join(
        [
            " | ".join(header.ljust(widths[header]) for header in headers),
            "-+-".join("-" * widths[header] for header in headers),
            *(
                " | ".join(str(row[header]).ljust(widths[header]) for header in headers)
                for row in rows
            ),
        ]
    )


def emit(rows, output_format, output_path):
    if output_path:
        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
    if output_format == "jsonl":
        content = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        )
    elif output_format == "csv":
        if output_path:
            with open(output_path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=OUTPUT_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            return
        writer = csv.DictWriter(sys.stdout, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        return
    else:
        content = render_table(rows) + "\n" if rows else "未找到匹配场景。\n"
    if output_path:
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(content)
    else:
        sys.stdout.write(content)


def main():
    args = parse_args()
    if args.limit < 0:
        raise ValueError("--limit 不能小于 0")
    entries = load_entries(os.path.abspath(args.library))
    matched = [entry for entry in entries if matches(entry, args)]
    matched = sort_entries(matched, args.sort)
    if args.limit:
        matched = matched[: args.limit]
    rows = [flatten_entry(entry) for entry in matched]
    emit(rows, args.format, args.output)
    print(f"[QUERY] matched={len(rows)} / library={len(entries)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
