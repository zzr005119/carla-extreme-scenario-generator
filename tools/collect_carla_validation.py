"""读取 CARLA metadata.json 并回填生成场景的 observed_risk。"""

import argparse
import csv
import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_features import RISK_LEVELS, load_jsonl  # noqa: E402
from core.scenario_validator import require_valid_scenario  # noqa: E402
from analysis.analyze_carla_validation import write_analysis  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description="汇总生成场景的 CARLA 运行结果并回填 observed_risk"
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def resolve_manifest_path(manifest_dir, path):
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(manifest_dir, path))


def newest_metadata(run_root):
    if not os.path.isdir(run_root):
        return None
    candidates = []
    for root, _, files in os.walk(run_root):
        if "metadata.json" in files:
            path = os.path.join(root, "metadata.json")
            candidates.append((os.path.getmtime(path), path))
    if not candidates:
        return None
    return max(candidates)[1]


def collect_result(record, manifest_row):
    metadata_path = newest_metadata(manifest_row["expected_run_root"])
    if metadata_path is None:
        return record, {
            "run_order": manifest_row.get("run_order"),
            "block_index": manifest_row.get("block_index"),
            "traffic_manager_seed": manifest_row.get("traffic_manager_seed"),
            "sample_id": record["sample_id"],
            "target_risk_level": record["conditions"]["target_risk_level"],
            "status": "missing",
            "observed_risk_level": None,
            "risk_score": None,
            "target_match": None,
            "risk_method": None,
            "collision_count": None,
            "minimum_ttc_seconds": None,
            "minimum_lead_gap_m": None,
            "minimum_pedestrian_distance_m": None,
            "sensor_status": None,
            "server_status": None,
            "run_dir": None,
            "metadata_path": None,
        }

    metadata = load_json(metadata_path)
    result = metadata.get("result") or {}
    risk = result.get("risk_evaluation") or {}
    run_dir = os.path.dirname(metadata_path)
    completed = (
        result.get("status") == "completed"
        and risk.get("method") is not None
        and risk.get("score") is not None
        and risk.get("level") in RISK_LEVELS
    )
    if completed:
        record["observed_risk"] = {
            "status": "completed",
            "method": risk["method"],
            "score": float(risk["score"]),
            "level": risk["level"],
            "run_dir": run_dir,
        }
        status = "completed"
    else:
        record["observed_risk"] = {
            "status": "failed",
            "method": None,
            "score": None,
            "level": None,
            "run_dir": run_dir,
        }
        status = "failed"
    require_valid_scenario(record)
    target_level = record["conditions"]["target_risk_level"]
    observed_level = record["observed_risk"]["level"]
    return record, {
        "run_order": manifest_row.get("run_order"),
        "block_index": manifest_row.get("block_index"),
        "traffic_manager_seed": manifest_row.get("traffic_manager_seed"),
        "sample_id": record["sample_id"],
        "target_risk_level": target_level,
        "status": status,
        "observed_risk_level": observed_level,
        "risk_score": record["observed_risk"]["score"],
        "target_match": observed_level == target_level if completed else None,
        "risk_method": record["observed_risk"]["method"],
        "collision_count": result.get("collision_count"),
        "minimum_ttc_seconds": result.get("minimum_ttc_seconds"),
        "minimum_lead_gap_m": result.get("minimum_lead_gap_m"),
        "minimum_pedestrian_distance_m": result.get(
            "minimum_pedestrian_distance_m"
        ),
        "sensor_status": (metadata.get("sensor_pipeline") or {}).get("status"),
        "server_status": (metadata.get("server_health") or {}).get("status"),
        "run_dir": run_dir,
        "metadata_path": metadata_path,
    }


def main():
    args = parse_args()
    manifest_path = os.path.abspath(args.manifest)
    manifest_dir = os.path.dirname(manifest_path)
    manifest = load_json(manifest_path)
    if manifest.get("format") != "cvae_carla_validation_v1":
        raise ValueError("不支持的验证清单格式")

    records_path = resolve_manifest_path(
        manifest_dir,
        manifest["selected_records"],
    )
    records = load_jsonl(records_path)
    records_by_id = {record["sample_id"]: record for record in records}
    if len(records_by_id) != len(records):
        raise ValueError("selected_records 中存在重复 sample_id")

    updated_records = []
    rows = []
    for manifest_row in manifest["records"]:
        sample_id = manifest_row["sample_id"]
        if sample_id not in records_by_id:
            raise KeyError(f"清单样本不在 selected_records 中: {sample_id}")
        record, row = collect_result(records_by_id[sample_id], manifest_row)
        updated_records.append(record)
        rows.append(row)

    observed_path = os.path.join(manifest_dir, "observed_records.jsonl")
    write_jsonl(observed_path, updated_records)
    csv_path = os.path.join(manifest_dir, "result_summary.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    completed_rows = [row for row in rows if row["status"] == "completed"]
    summary = {
        "manifest": manifest_path,
        "total": len(rows),
        "completed": len(completed_rows),
        "failed": sum(row["status"] == "failed" for row in rows),
        "missing": sum(row["status"] == "missing" for row in rows),
        "target_level_matches": sum(
            row["target_match"] is True for row in completed_rows
        ),
        "target_level_match_rate": (
            sum(row["target_match"] is True for row in completed_rows)
            / len(completed_rows)
            if completed_rows
            else None
        ),
        "observed_records": observed_path,
        "result_csv": csv_path,
    }
    summary_path = os.path.join(manifest_dir, "result_summary.json")
    write_json(summary_path, summary)
    analysis, analysis_json, analysis_markdown = write_analysis(
        csv_path,
        manifest_dir,
    )
    summary["analysis_json"] = analysis_json
    summary["analysis_markdown"] = analysis_markdown
    summary["mean_scores_strictly_increasing"] = analysis[
        "mean_scores_strictly_increasing"
    ]
    write_json(summary_path, summary)
    print(
        "[COLLECT] "
        f"completed={summary['completed']} | failed={summary['failed']} | "
        f"missing={summary['missing']}"
    )
    print(f"[COLLECT] 记录: {observed_path}")
    print(f"[COLLECT] 汇总: {summary_path}")
    print(f"[COLLECT] 分析: {analysis_markdown}")
    if summary["missing"] and not args.allow_missing:
        return 1
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
