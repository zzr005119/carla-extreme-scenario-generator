"""准备单通道独有与双通道独有候选的配对 CARLA 验证计划。"""

import argparse
import copy
import csv
import hashlib
import json
import os
import random
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
TRAFFIC_SEEDS = (20260821, 20260822, 20260823)
ARMS = ("single_only", "dual_only")
DEFAULT_BASE_CONFIG = PROJECT_ROOT / "configs" / "multi_hazard_rainy_night.json"
DEFAULT_CONTROL_PROFILE = (
    PROJECT_ROOT / "configs" / "route_control_profiles" / "waypoint_follower_v1.json"
)

from core.scenario_validator import compile_carla_config, load_json, require_valid_scenario
from core.scenario_features import load_jsonl
from tools.prepare_carla_route_regression import apply_regression_profile, load_control_profile


def parse_args():
    parser = argparse.ArgumentParser(description="准备双通道配对验证计划")
    parser.add_argument("--single-records", required=True)
    parser.add_argument("--single-selection", required=True)
    parser.add_argument("--dual-records", required=True)
    parser.add_argument("--dual-selection", required=True)
    parser.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG))
    parser.add_argument("--control-profile", default=str(DEFAULT_CONTROL_PROFILE))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--runtime-output-root", required=True)
    parser.add_argument("--carla-root", default=str(PROJECT_ROOT))
    parser.add_argument("--run-seed", type=int, default=20260816)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--validate-runner", action="store_true")
    parser.add_argument("--validation-python", default=sys.executable)
    return parser.parse_args()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_executable(path, lines):
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines) + "\n")
    os.chmod(
        path,
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH,
    )


def current_git_commit():
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def load_selection(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"选择清单为空: {path}")
    required = {
        "sample_id",
        "generator",
        "target_risk_level",
        "selection_channel",
        "selection_order",
    }
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"选择清单缺少字段: {missing}")
    return rows


def load_arm(records_path, selection_path, arm):
    records = load_jsonl(os.path.abspath(records_path))
    rows = load_selection(os.path.abspath(selection_path))
    clean_records = []
    for record in records:
        scenario_record = copy.deepcopy(record)
        scenario_record.pop("candidate_scoring_v2", None)
        clean_records.append(scenario_record)
    record_by_id = {record["sample_id"]: record for record in clean_records}
    row_by_id = {row["sample_id"]: row for row in rows}
    if len(record_by_id) != len(records) or len(row_by_id) != len(rows):
        raise ValueError(f"{arm} 存在重复 sample_id")
    if set(record_by_id) != set(row_by_id):
        raise ValueError(f"{arm} 的 JSONL 与选择清单 sample_id 不一致")
    for record in clean_records:
        require_valid_scenario(record)
        row = row_by_id[record["sample_id"]]
        if record["provenance"]["generator"].split("_")[0] not in {
            "balanced",
            "conditional",
        }:
            raise ValueError(f"无法识别生成器来源: {record['sample_id']}")
        if record["conditions"]["target_risk_level"] != row["target_risk_level"]:
            raise ValueError(f"目标档不一致: {record['sample_id']}")
    return record_by_id, row_by_id


def validate_comparison(single_records, single_rows, dual_records, dual_rows):
    single_ids = set(single_records)
    dual_ids = set(dual_records)
    common_ids = single_ids & dual_ids
    single_only = single_ids - dual_ids
    dual_only = dual_ids - single_ids
    if len(single_records) != 27 or len(dual_records) != 27:
        raise ValueError("单通道和双通道短名单都必须为 27 个场景")
    if len(common_ids) != 18 or len(single_only) != 9 or len(dual_only) != 9:
        raise ValueError(
            f"配对设计要求交集18、两侧独有各9，实际为 "
            f"交集{len(common_ids)}、单侧{len(single_only)}、双侧{len(dual_only)}"
        )

    def cell_counts(rows, ids):
        counts = {}
        for row in rows:
            if row["sample_id"] not in ids:
                continue
            key = (row["generator"], row["target_risk_level"])
            counts[key] = counts.get(key, 0) + 1
        return counts

    single_counts = cell_counts(single_rows.values(), single_only)
    dual_counts = cell_counts(dual_rows.values(), dual_only)
    if single_counts != dual_counts:
        raise ValueError(
            f"两侧独有样本的生成器×目标档分布不一致: {single_counts} != {dual_counts}"
        )
    expected_counts = {
        (generator, "high"): 1
        for generator in ("lhs", "gmm", "cvae")
    }
    expected_counts.update(
        {(generator, "critical"): 2 for generator in ("lhs", "gmm", "cvae")}
    )
    if single_counts != expected_counts:
        raise ValueError(f"独有样本分层不符合配对设计: {single_counts}")
    return common_ids, single_only, dual_only


def build_records(single_records, dual_records, single_rows, dual_rows, single_only, dual_only):
    rows_by_arm = {
        "single_only": (single_records, single_rows, single_only),
        "dual_only": (dual_records, dual_rows, dual_only),
    }
    combined_records = {}
    combined_rows = []
    for arm, (records, rows, selected_ids) in rows_by_arm.items():
        for sample_id in sorted(selected_ids):
            record = copy.deepcopy(records[sample_id])
            row = dict(rows[sample_id])
            row["comparison_arm"] = arm
            row["original_selection_channel"] = row["selection_channel"]
            row["selection_channel"] = arm
            row["selection_order"] = str(
                len(
                    [
                        item
                        for item in combined_rows
                        if item["comparison_arm"] == arm
                        and item["generator"] == row["generator"]
                        and item["target_risk_level"] == row["target_risk_level"]
                    ]
                )
                + 1
            )
            combined_records[sample_id] = record
            combined_rows.append(row)
    return combined_records, combined_rows


def build_runs(records, rows_by_id, base_config, control_profile, config_dir, runtime_root):
    runs = {}
    for sample_id in sorted(records):
        record = records[sample_id]
        metadata = dict(rows_by_id[sample_id])
        for repeat_round, traffic_seed in enumerate(TRAFFIC_SEEDS, 1):
            run_id = (
                f"{sample_id}__{metadata['comparison_arm']}__tm_{traffic_seed}"
                "__dual_channel_validation_v1"
            )
            config = compile_carla_config(copy.deepcopy(record), copy.deepcopy(base_config))
            config["scenario"]["name"] = run_id
            config["scenario"]["traffic_manager_seed"] = traffic_seed
            apply_regression_profile(config, control_profile)
            config["output"]["root"] = runtime_root
            config_path = os.path.join(config_dir, f"{run_id}.json")
            write_json(config_path, config)
            runs[(sample_id, traffic_seed)] = {
                **metadata,
                "sample_id": sample_id,
                "run_id": run_id,
                "repeat_round": repeat_round,
                "traffic_manager_seed": traffic_seed,
                "source": "dual_channel_validation_v1",
                "config_path": config_path,
                "expected_run_root": os.path.join(runtime_root, run_id),
                "group_index": None,
                "part_index": None,
                "run_order": None,
                "block_traffic_manager_seed": None,
            }
    return runs


def build_schedule(runs, run_seed):
    generator = random.Random(run_seed)
    groups = []
    schedule = []
    part_index = 0
    for group_index, traffic_seed in enumerate(TRAFFIC_SEEDS, 1):
        current = [runs[(sample_id, traffic_seed)] for sample_id, _ in runs if _ == traffic_seed]
        generator.shuffle(current)
        group_parts = []
        for offset in range(0, len(current), 3):
            part_index += 1
            part_rows = current[offset : offset + 3]
            for row in part_rows:
                row["group_index"] = group_index
                row["part_index"] = part_index
                row["run_order"] = len(schedule) + 1
                row["block_traffic_manager_seed"] = traffic_seed
                schedule.append(row)
            group_parts.append(part_rows)
        groups.append(group_parts)
    return groups, schedule


def validate_configs(config_paths, scene_runner, python_path):
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    results = []
    for config_path in config_paths:
        completed = subprocess.run(
            [os.path.abspath(python_path), scene_runner, "--config", config_path, "--validate-only"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
        result = {
            "config_path": config_path,
            "valid": completed.returncode == 0,
            "return_code": completed.returncode,
            "message": (completed.stdout or completed.stderr).strip(),
        }
        results.append(result)
        if not result["valid"]:
            raise RuntimeError(f"配置校验失败: {config_path}\n{result['message']}")
    return results


def write_scripts(output_dir, groups, project_root):
    runner = os.path.join(project_root, "tools", "run_feedback_candidate_validation.py")
    collector = os.path.join(project_root, "tools", "collect_feedback_candidate_validation.py")
    manifest = os.path.join(output_dir, "manifest.json")
    group_paths = []
    for group_index, group_parts in enumerate(groups, 1):
        part_paths = []
        for part_rows in group_parts:
            part_index = int(part_rows[0]["part_index"])
            part_path = os.path.join(output_dir, f"run_part_{part_index:02d}.sh")
            write_executable(
                part_path,
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    f'python -u "{runner}" --manifest "{manifest}" --part-index {part_index}',
                ],
            )
            part_paths.append(part_path)
        group_path = os.path.join(output_dir, f"run_group_{group_index:02d}.sh")
        lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
        for part_path in part_paths:
            lines.extend([f'bash "{part_path}"', "sleep 20"])
        write_executable(group_path, lines)
        group_paths.append(group_path)
    run_all = ["#!/usr/bin/env bash", "set -euo pipefail"]
    for group_path in group_paths:
        run_all.extend([f'bash "{group_path}"', "sleep 30"])
    write_executable(os.path.join(output_dir, "run_all.sh"), run_all)
    write_executable(
        os.path.join(output_dir, "run_smoke.sh"),
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f'python -u "{runner}" --manifest "{manifest}" --limit 1',
        ],
    )
    write_executable(
        os.path.join(output_dir, "collect_results.sh"),
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f'python -u "{collector}" --manifest "{manifest}"',
        ],
    )


def main():
    args = parse_args()
    output_dir = Path(os.path.abspath(args.output_dir))
    if output_dir.exists() and any(output_dir.iterdir()) and not args.force:
        raise FileExistsError(f"输出目录非空，如需覆盖请使用 --force: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    config_dir = output_dir / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    runtime_root = os.path.abspath(args.runtime_output_root)

    single_records, single_rows = load_arm(args.single_records, args.single_selection, "single_channel")
    dual_records, dual_rows = load_arm(args.dual_records, args.dual_selection, "dual_channel")
    common_ids, single_only, dual_only = validate_comparison(
        single_records, single_rows, dual_records, dual_rows
    )
    records, combined_rows = build_records(
        single_records, dual_records, single_rows, dual_rows, single_only, dual_only
    )
    rows_by_id = {row["sample_id"]: row for row in combined_rows}
    selected_records_path = output_dir / "selected_records.jsonl"
    selection_csv_path = output_dir / "selection_metadata.csv"
    write_jsonl(selected_records_path, [records[sample_id] for sample_id in sorted(records)])
    write_csv(selection_csv_path, combined_rows)

    base_config = load_json(os.path.abspath(args.base_config))
    _, control_profile = load_control_profile(args.control_profile)
    carla_root = os.path.abspath(args.carla_root)
    scene_runner = os.path.join(carla_root, "scenes", "scene_04_parameterized.py")
    runs = build_runs(
        records,
        rows_by_id,
        base_config,
        control_profile,
        str(config_dir),
        runtime_root,
    )
    groups, schedule = build_schedule(runs, args.run_seed)
    validation_results = []
    if args.validate_runner:
        validation_results = validate_configs(
            [row["config_path"] for row in schedule], scene_runner, args.validation_python
        )
    write_csv(output_dir / "run_schedule.csv", schedule)
    write_scripts(str(output_dir), groups, carla_root)

    acceptance = copy.deepcopy(control_profile["acceptance_requirements"])
    acceptance["carla_version"] = "0.9.16"
    acceptance["route_verification_scope"] = "pre_collision_for_collision_runs"
    manifest = {
        "format": "feedback_candidate_validation_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": current_git_commit(),
        "analysis_unit": "paired_unique_candidate",
        "traffic_seed_role": "repeated_measurement",
        "supports_significance_testing": False,
        "generators": ["lhs", "gmm", "cvae"],
        "selection_channels": list(ARMS),
        "traffic_seeds": list(TRAFFIC_SEEDS),
        "selected_scenario_count": len(records),
        "planned_run_count": len(schedule),
        "selected_records": str(selected_records_path),
        "selected_records_sha256": file_sha256(selected_records_path),
        "selection_metadata": str(selection_csv_path),
        "selection_metadata_sha256": file_sha256(selection_csv_path),
        "scene_runner": scene_runner,
        "carla_root": carla_root,
        "runtime_output_root": runtime_root,
        "route_lock_required": True,
        "controller_mode": control_profile["route"]["route_control_mode"],
        "control_profile_id": control_profile["profile_id"],
        "acceptance_requirements": acceptance,
        "runs": schedule,
        "comparison_design": {
            "common_scenario_count": len(common_ids),
            "single_only_count": len(single_only),
            "dual_only_count": len(dual_only),
            "arms": list(ARMS),
            "pairing_factors": ["generator", "target_risk_level", "traffic_manager_seed"],
            "independent_unit": "scenario",
        },
        "validation_results": validation_results,
        "design": {
            "type": "paired_randomized_block_repeated_measurement",
            "run_seed": args.run_seed,
            "block_count": len(groups),
            "part_count": len([part for group in groups for part in group]),
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    (output_dir / "README.md").write_text(
        "\n".join(
            [
                "# 双通道候选配对验证 V1",
                "",
                f"- 单通道独有：`{len(single_only)}` 个；双通道独有：`{len(dual_only)}` 个；共同候选：`{len(common_ids)}` 个。",
                f"- 本次验证：`{len(records)}` 个独立场景 × 3 个交通种子 = `{len(schedule)}` 次运行。",
                "- 两侧独有样本按生成器和目标档严格配对：每个生成器各 1 个 high、2 个 critical。",
                "- 该实验只比较选择通道，不比较生成器优劣；三个 Traffic Manager 种子是重复测量。",
                "",
                "## 执行",
                "",
                "```bash",
                "bash run_smoke.sh",
                "bash run_all.sh",
                "bash collect_results.sh",
                "```",
                "",
                "配置已先通过 `--validate-only` 静态校验；正式运行仍需CARLA服务健康和严格验收。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"[DUAL_PLAN] common={len(common_ids)} | single_only={len(single_only)} | "
        f"dual_only={len(dual_only)} | runs={len(schedule)}"
    )
    print(f"[DUAL_PLAN] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
