"""收集反馈候选 CARLA 外部验证并生成重复性与外部评分报告。"""

import argparse
import csv
import json
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.analyze_carla_repeatability import write_analysis  # noqa: E402
from analysis.analyze_feedback_candidate_validation import (  # noqa: E402
    write_analysis as write_external_analysis,
)
from core.scenario_features import load_jsonl  # noqa: E402
from tools.build_risk_feedback_dataset import (  # noqa: E402
    aggregate_rows,
    write_csv as write_dataset_csv,
)
from tools.collect_carla_repeatability import collect_row, load_json  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="收集反馈候选 CARLA 外部验证")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args()


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def augment_row(row, run):
    fields = (
        "generator",
        "selection_channel",
        "selection_order",
        "predicted_risk_mean",
        "predicted_risk_std",
        "robust_predicted_risk_score",
        "bootstrap_top_k_frequency",
        "nearest_collision_distance",
        "collision_boundary_score",
        "selection_diversity_distance",
        "group_index",
        "part_index",
        "run_order",
        "block_selection_order",
        "block_traffic_manager_seed",
    )
    for field in fields:
        row[field] = run.get(field)
    return row


def write_dataset_addition(output_dir, rows, records, expected_repeats):
    accepted = [row for row in rows if row["acceptance_status"] == "completed"]
    records_by_id = {record["sample_id"]: record for record in records}
    dataset = aggregate_rows(accepted, records_by_id, expected_repeats)
    csv_path = os.path.join(output_dir, "feedback_dataset_addition.csv")
    jsonl_path = os.path.join(output_dir, "feedback_dataset_addition.jsonl")
    summary_path = os.path.join(output_dir, "feedback_dataset_addition_summary.json")
    write_dataset_csv(csv_path, dataset)
    with open(jsonl_path, "w", encoding="utf-8") as file:
        for row in dataset:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_json(
        summary_path,
        {
            "format": "risk_feedback_dataset_addition_v1",
            "strictly_accepted_run_count": len(accepted),
            "independent_scenario_count": len(dataset),
            "repeat_count_per_scenario": expected_repeats,
            "analysis_unit": "independent_scenario",
            "traffic_seed_role": "repeated_measurement",
            "collision_scenario_count": sum(
                row["collision_event_total"] > 0 for row in dataset
            ),
        },
    )
    return csv_path, summary_path


def main():
    args = parse_args()
    manifest_path = os.path.abspath(args.manifest)
    output_dir = os.path.dirname(manifest_path)
    manifest = load_json(manifest_path)
    if manifest.get("format") != "feedback_candidate_validation_v1":
        raise ValueError("不支持的反馈候选验证清单格式")

    acceptance = manifest["acceptance_requirements"]
    rows = []
    for run in manifest["runs"]:
        row = collect_row(
            run,
            route_lock_required=True,
            acceptance_requirements=acceptance,
        )
        rows.append(augment_row(row, run))
    rows.sort(key=lambda row: int(row["run_order"]))
    run_results_path = os.path.join(output_dir, "run_results.csv")
    write_csv(run_results_path, rows)
    with open(os.path.join(output_dir, "run_results.jsonl"), "w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    repeatability, repeatability_path, scenario_csv, seed_csv, repeatability_report = (
        write_analysis(
            rows,
            manifest["traffic_seeds"],
            output_dir,
            route_lock_required=True,
            report_title="反馈候选多种子受控重复性分析",
        )
    )
    external, external_path, external_scenario_csv, external_report = (
        write_external_analysis(
            rows,
            manifest["selected_scenario_count"],
            output_dir,
            top_k=9,
        )
    )

    dataset_paths = None
    if repeatability["accepted_runs"] == repeatability["expected_run_count"]:
        records = load_jsonl(manifest["selected_records"])
        dataset_paths = write_dataset_addition(
            output_dir,
            rows,
            records,
            len(manifest["traffic_seeds"]),
        )

    print(
        f"[COLLECT] completed={repeatability['completed_runs']} | "
        f"accepted={repeatability['accepted_runs']} | "
        f"missing={repeatability['missing_runs']}"
    )
    print(
        f"[COLLECT] external_scenarios="
        f"{external['accepted_scenario_count']}/{external['planned_scenario_count']}"
    )
    print(f"[COLLECT] run_results={run_results_path}")
    print(f"[COLLECT] repeatability={repeatability_path}")
    print(f"[COLLECT] scenario_repeatability={scenario_csv}")
    print(f"[COLLECT] seed_repeatability={seed_csv}")
    print(f"[COLLECT] repeatability_report={repeatability_report}")
    print(f"[COLLECT] external_validation={external_path}")
    print(f"[COLLECT] external_scenarios={external_scenario_csv}")
    print(
        f"[COLLECT] external_pairs="
        f"{os.path.join(output_dir, 'external_validation_paired.csv')}"
    )
    print(f"[COLLECT] external_report={external_report}")
    if dataset_paths:
        print(f"[COLLECT] feedback_addition={dataset_paths[0]}")
    if repeatability["missing_runs"] and not args.allow_missing:
        return 1
    return 0 if repeatability["acceptance_failed_runs"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
