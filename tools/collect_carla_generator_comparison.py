"""收集三种场景生成器的受控 CARLA 对照结果。"""

import argparse
import csv
import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.analyze_carla_generator_comparison import (  # noqa: E402
    write_comparison,
)
from analysis.analyze_carla_repeatability import write_analysis  # noqa: E402
from core.scenario_features import load_jsonl  # noqa: E402
from tools.collect_carla_repeatability import collect_row, load_json  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="收集生成器 CARLA 对照结果")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args()


def resolve_path(base_dir, path):
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def main():
    args = parse_args()
    manifest_path = os.path.abspath(args.manifest)
    output_dir = os.path.dirname(manifest_path)
    manifest = load_json(manifest_path)
    if manifest.get("format") != "generator_carla_comparison_v1":
        raise ValueError("不支持的生成器对照清单格式")

    acceptance_requirements = manifest.get("acceptance_requirements") or {}
    rows = []
    for run in manifest["runs"]:
        row = collect_row(
            run,
            route_lock_required=True,
            acceptance_requirements=acceptance_requirements,
        )
        row["generator"] = run["generator"]
        row["group_index"] = int(run["group_index"])
        row["part_index"] = int(run["part_index"])
        row["run_order"] = int(run["run_order"])
        rows.append(row)
    rows.sort(
        key=lambda row: (
            row["generator"],
            row["sample_id"],
            row["traffic_manager_seed"],
        )
    )

    csv_path = os.path.join(output_dir, "run_results.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    jsonl_path = os.path.join(output_dir, "run_results.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    repeatability, repeatability_path, scenario_csv, seed_csv, repeatability_report = (
        write_analysis(
            rows,
            manifest["traffic_seeds"],
            output_dir,
            route_lock_required=True,
            report_title="LHS / GMM / CVAE 多种子受控重复性分析",
        )
    )
    selected_records_path = resolve_path(
        output_dir, manifest["selected_records"]
    )
    comparison, comparison_path, generator_csv, target_csv, comparison_report = (
        write_comparison(
            rows,
            load_jsonl(selected_records_path),
            manifest["traffic_seeds"],
            output_dir,
        )
    )

    print(
        f"[COLLECT] completed={repeatability['completed_runs']} | "
        f"failed={repeatability['failed_runs']} | "
        f"missing={repeatability['missing_runs']}"
    )
    print(
        f"[COLLECT] accepted={repeatability['accepted_runs']} | "
        f"acceptance_failed={repeatability['acceptance_failed_runs']} | "
        f"route_verified={repeatability['route_verified_runs']}"
    )
    print(
        f"[COLLECT] generator_comparison="
        f"{comparison['completed_runs']}/{comparison['planned_runs']}"
    )
    print(f"[COLLECT] 运行明细: {csv_path}")
    print(f"[COLLECT] 重复性汇总: {repeatability_path}")
    print(f"[COLLECT] 场景统计: {scenario_csv}")
    print(f"[COLLECT] 种子统计: {seed_csv}")
    print(f"[COLLECT] 重复性报告: {repeatability_report}")
    print(f"[COLLECT] 生成器汇总: {comparison_path}")
    print(f"[COLLECT] 生成器统计: {generator_csv}")
    print(f"[COLLECT] 目标档统计: {target_csv}")
    print(f"[COLLECT] 对照报告: {comparison_report}")
    if repeatability["missing_runs"] and not args.allow_missing:
        return 1
    return 0 if repeatability["acceptance_failed_runs"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
