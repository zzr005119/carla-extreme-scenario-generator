"""准备 LHS、GMM 与 CVAE 的同口径受控 CARLA 对照实验。"""

import argparse
import copy
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_features import RISK_LEVELS, load_jsonl  # noqa: E402
from core.scenario_validator import (  # noqa: E402
    compile_carla_config,
    load_json,
    require_valid_scenario,
)
from tools.prepare_carla_route_regression import (  # noqa: E402
    apply_regression_profile,
    file_sha256,
    load_control_profile,
    write_lines,
)
from tools.prepare_carla_validation import select_records  # noqa: E402


GENERATORS = ("lhs", "gmm", "cvae")
GENERATOR_IDS = {
    "lhs": "balanced_latin_hypercube_v1",
    "gmm": "conditional_diagonal_gmm_v1",
    "cvae": "conditional_tabular_cvae_v1",
}
TRAFFIC_SEEDS = (20260821, 20260822, 20260823)
DEFAULT_INPUT_ROOT = os.path.join(PROJECT_ROOT, "artifacts", "final_evaluation")
DEFAULT_OUTPUT_DIR = os.path.join(
    PROJECT_ROOT, "data", "scenarios", "generator_comparison_v1"
)
DEFAULT_BASE_CONFIG = os.path.join(
    PROJECT_ROOT, "configs", "multi_hazard_rainy_night.json"
)
DEFAULT_CONTROL_PROFILE = os.path.join(
    PROJECT_ROOT,
    "configs",
    "route_control_profiles",
    "waypoint_follower_v1.json",
)
DEFAULT_CARLA_ROOT = r"F:\Carla\test"


def parse_args():
    parser = argparse.ArgumentParser(description="准备三生成器 CARLA 对照实验")
    parser.add_argument("--input-root", default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--control-profile", default=DEFAULT_CONTROL_PROFILE)
    parser.add_argument("--carla-root", default=DEFAULT_CARLA_ROOT)
    parser.add_argument("--per-level", type=int, default=3)
    parser.add_argument(
        "--selection", choices=("spread", "centroid"), default="spread"
    )
    parser.add_argument("--run-seed", type=int, default=20260814)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--validate-runner", action="store_true")
    parser.add_argument("--validation-python", default=sys.executable)
    return parser.parse_args()


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_path(input_root, generator, level):
    return os.path.join(input_root, f"{generator}_{level}.jsonl")


def load_grouped_sources(input_root):
    grouped = {generator: {} for generator in GENERATORS}
    source_files = []
    seen_ids = set()
    for generator in GENERATORS:
        for level in RISK_LEVELS:
            path = os.path.abspath(source_path(input_root, generator, level))
            if not os.path.isfile(path):
                raise FileNotFoundError(f"缺少生成结果: {path}")
            records = load_jsonl(path)
            for record in records:
                require_valid_scenario(record)
                sample_id = record["sample_id"]
                if sample_id in seen_ids:
                    raise ValueError(f"样本编号重复: {sample_id}")
                seen_ids.add(sample_id)
                if record["conditions"]["target_risk_level"] != level:
                    raise ValueError(f"风险档不一致: {sample_id}")
                actual_generator = record["provenance"]["generator"]
                if actual_generator != GENERATOR_IDS[generator]:
                    raise ValueError(f"生成器标识不一致: {sample_id}")
            grouped[generator][level] = records
            source_files.append(
                {
                    "generator": generator,
                    "target_risk_level": level,
                    "path": path,
                    "sha256": sha256(path),
                    "record_count": len(records),
                }
            )
    return grouped, source_files


def select_scenarios(grouped, per_level, method):
    selected = []
    selected_by_cell = {generator: {} for generator in GENERATORS}
    selection_rows = []
    for generator in GENERATORS:
        for level in RISK_LEVELS:
            records = select_records(grouped[generator][level], per_level, method)
            selected_by_cell[generator][level] = []
            for selection_index, source_record in enumerate(records, 1):
                record = copy.deepcopy(source_record)
                selected.append(record)
                selected_by_cell[generator][level].append(record)
                selection_rows.append(
                    {
                        "generator": generator,
                        "target_risk_level": level,
                        "selection_index": selection_index,
                        "sample_id": record["sample_id"],
                        "source_generator_id": record["provenance"]["generator"],
                    }
                )
    return selected, selected_by_cell, selection_rows


def make_runs(
    selected_by_cell,
    base_config,
    control_profile,
    config_dir,
    runtime_output_root,
):
    runs = {}
    for generator in GENERATORS:
        for level in RISK_LEVELS:
            for selection_index, record in enumerate(
                selected_by_cell[generator][level], 1
            ):
                for repeat_round, traffic_seed in enumerate(TRAFFIC_SEEDS, 1):
                    sample_id = record["sample_id"]
                    run_id = (
                        f"{sample_id}__tm_{traffic_seed}__generator_compare_v1"
                    )
                    config = compile_carla_config(
                        copy.deepcopy(record), copy.deepcopy(base_config)
                    )
                    config["scenario"]["name"] = run_id
                    config["scenario"]["traffic_manager_seed"] = traffic_seed
                    apply_regression_profile(config, control_profile)
                    config["output"]["root"] = runtime_output_root
                    config_path = os.path.join(config_dir, f"{run_id}.json")
                    write_json(config_path, config)
                    runs[(generator, level, selection_index, traffic_seed)] = {
                        "run_id": run_id,
                        "sample_id": sample_id,
                        "generator": generator,
                        "target_risk_level": level,
                        "selection_index": selection_index,
                        "repeat_round": repeat_round,
                        "traffic_manager_seed": traffic_seed,
                        "source": "controlled_generator_comparison_v1",
                        "planned": True,
                        "group_index": None,
                        "part_index": None,
                        "run_order": None,
                        "config_path": config_path,
                        "expected_run_root": os.path.join(
                            runtime_output_root, run_id
                        ),
                    }
    return runs


def build_schedule(runs, run_seed):
    generator = np.random.default_rng(run_seed)
    templates = [
        (sample_offset, seed_offset)
        for sample_offset in range(3)
        for seed_offset in range(3)
    ]
    generator.shuffle(templates)
    groups = []
    planned_rows = []
    part_index = 0
    for group_index, (sample_offset, seed_offset) in enumerate(templates, 1):
        group_parts = []
        generator_rotation = int(generator.integers(0, len(GENERATORS)))
        for subpart_index in range(3):
            part_index += 1
            rows = []
            for level_index, level in enumerate(RISK_LEVELS):
                generator_index = (
                    subpart_index + level_index + generator_rotation
                ) % len(GENERATORS)
                model_name = GENERATORS[generator_index]
                selection_index = (
                    sample_offset + generator_index + level_index
                ) % 3 + 1
                traffic_seed = TRAFFIC_SEEDS[
                    (seed_offset + generator_index + level_index) % 3
                ]
                rows.append(
                    runs[
                        (
                            model_name,
                            level,
                            selection_index,
                            traffic_seed,
                        )
                    ]
                )
            generator.shuffle(rows)
            for row in rows:
                row["group_index"] = group_index
                row["part_index"] = part_index
                row["run_order"] = len(planned_rows) + 1
                planned_rows.append(row)
            group_parts.append(rows)
        groups.append(group_parts)
    return groups, planned_rows


def write_part_script(path, carla_root, scene_runner, rows):
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        'set "PYTHONUTF8=1"',
        "chcp 65001 >nul",
        f'cd /d "{carla_root}"',
        "",
    ]
    for index, row in enumerate(rows, 1):
        config_name = os.path.basename(row["config_path"])
        lines.extend(
            [
                f"echo [RUN {index}/{len(rows)}] {row['run_id']}",
                f'python -u "{scene_runner}" --config "%~dp0configs\\{config_name}"',
                "if errorlevel 1 goto :failed",
                "timeout /t 10 /nobreak >nul",
                "",
            ]
        )
    lines.extend(
        [
            "echo [DONE] Generator comparison part completed.",
            "exit /b 0",
            "",
            ":failed",
            "echo [FAILED] Stop after CARLA or Python error.",
            "exit /b 1",
            "",
        ]
    )
    write_lines(path, lines)


def write_call_script(path, children, done_message, wait_seconds):
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        'set "PYTHONUTF8=1"',
        "chcp 65001 >nul",
        "",
    ]
    for child in children:
        lines.extend(
            [
                f'call "%~dp0{os.path.basename(child)}"',
                "if errorlevel 1 exit /b 1",
                f"timeout /t {wait_seconds} /nobreak >nul",
                "",
            ]
        )
    lines.extend([f"echo [DONE] {done_message}", "exit /b 0", ""])
    write_lines(path, lines)


def write_collect_script(path):
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        'set "PYTHONUTF8=1"',
        "chcp 65001 >nul",
        'cd /d "%~dp0..\\..\\.."',
        "",
        "python -u tools\\collect_carla_generator_comparison.py "
        '--manifest "%~dp0manifest.json"',
        "if errorlevel 1 goto :failed",
        "",
        "echo [DONE] Generator comparison acceptance passed.",
        "exit /b 0",
        "",
        ":failed",
        "echo [FAILED] Generator comparison acceptance failed.",
        "exit /b 1",
        "",
    ]
    write_lines(path, lines)


def write_validate_script(path, scene_runner):
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        'set "PYTHONUTF8=1"',
        "chcp 65001 >nul",
        "",
        'for %%F in ("%~dp0configs\\*.json") do (',
        f'  python -u "{scene_runner}" --config "%%~fF" --validate-only',
        "  if errorlevel 1 exit /b 1",
        ")",
        "echo [DONE] All generated configs passed validate-only.",
        "exit /b 0",
        "",
    ]
    write_lines(path, lines)


def validate_configs(config_paths, scene_runner, python_path):
    results = []
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    for index, config_path in enumerate(config_paths, 1):
        completed = subprocess.run(
            [
                os.path.abspath(python_path),
                os.path.abspath(scene_runner),
                "--config",
                os.path.abspath(config_path),
                "--validate-only",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
        results.append(
            {
                "config": os.path.abspath(config_path),
                "valid": completed.returncode == 0,
                "return_code": completed.returncode,
                "message": (completed.stdout or completed.stderr).strip(),
            }
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"配置校验失败 {index}/{len(config_paths)}: "
                f"{config_path}\n{completed.stdout}\n{completed.stderr}"
            )
    return results


def write_readme(path, manifest, group_paths, part_paths):
    output_dir = os.path.dirname(path)
    lines = [
        "# LHS / GMM / CVAE CARLA 同口径对照 V1",
        "",
        "该实验在冻结的 `waypoint_follower_v1` 下比较三种参数级场景生成器。",
        "",
        "## 实验设计",
        "",
        "- 生成器：LHS、条件 GMM、条件表格 CVAE。",
        "- 每个生成器在低、中、高、临界四档各选择 3 个场景，共 36 个独立场景样本。",
        "- 每个场景使用三个 Traffic Manager 种子重复运行，共 108 次。",
        "- 独立实验单位是场景样本；交通种子属于重复测量，不能当作额外独立样本。",
        "- 采用相同的 `spread` 抽样、基础配置、控制器、传感器和严格验收口径。",
        "- 9 个平衡组各包含三种生成器 × 四个风险档，拆为 27 个四场景小批次；组内随机化用于削弱运行顺序和设备状态干扰。",
        "- 本轮是工程描述性对照，不支持统计显著性声明。",
        "",
        "## 执行",
        "",
        "启动 CARLAUE4 后，优先逐个运行下列 9 个组脚本：",
        "",
    ]
    lines.extend(f"- `{os.path.basename(path)}`" for path in group_paths)
    lines.extend(
        [
            "",
            "每个组脚本包含 3 个四场景小批次；若设备不稳定，可直接运行对应的 `run_part_*.cmd`。",
            f"一次运行全部 108 次可使用 `{os.path.join(output_dir, 'run_all.cmd')}`，RTX 4060 设备不推荐连续执行。",
            "",
            "全部完成后运行：",
            "",
            "```cmd",
            f'"{os.path.join(output_dir, "collect_results.cmd")}"',
            "```",
            "",
            "重新检查 108 份配置可运行：",
            "",
            "```cmd",
            f'"{os.path.join(output_dir, "validate_all.cmd")}"',
            "```",
            "",
            "汇总时同时输出跨种子重复性和三生成器对照报告；始终分开报告 `target_risk_level` 与 CARLA 实测 `observed_risk`。",
            "",
            f"共生成 `{len(part_paths)}` 个小批次脚本。",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


def main():
    args = parse_args()
    if args.per_level != 3:
        raise ValueError("当前平衡调度固定要求 --per-level=3")

    output_dir = os.path.abspath(args.output_dir)
    if os.path.isdir(output_dir) and os.listdir(output_dir):
        if not args.force:
            raise FileExistsError(f"输出目录非空: {output_dir}，如需覆盖请加 --force")
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    config_dir = os.path.join(output_dir, "configs")
    os.makedirs(config_dir, exist_ok=True)

    grouped, source_files = load_grouped_sources(os.path.abspath(args.input_root))
    selected, selected_by_cell, selection_rows = select_scenarios(
        grouped, args.per_level, args.selection
    )
    selected_records_path = os.path.join(output_dir, "selected_records.jsonl")
    write_jsonl(selected_records_path, selected)

    base_config_path = os.path.abspath(args.base_config)
    base_config = load_json(base_config_path)
    control_profile_path, control_profile = load_control_profile(
        args.control_profile
    )
    carla_root = os.path.abspath(args.carla_root)
    scene_runner = os.path.join(
        carla_root, "scenes", "scene_04_parameterized.py"
    )
    runtime_output_root = os.path.join(
        carla_root, "output", "generator_comparison_v1"
    )
    runs = make_runs(
        selected_by_cell,
        base_config,
        control_profile,
        config_dir,
        runtime_output_root,
    )
    groups, planned_rows = build_schedule(runs, args.run_seed)

    part_paths = []
    group_paths = []
    for group_index, group_parts in enumerate(groups, 1):
        current_part_paths = []
        for rows in group_parts:
            part_path = os.path.join(
                output_dir, f"run_part_{rows[0]['part_index']:02d}.cmd"
            )
            write_part_script(part_path, carla_root, scene_runner, rows)
            part_paths.append(part_path)
            current_part_paths.append(part_path)
        group_path = os.path.join(output_dir, f"run_group_{group_index:02d}.cmd")
        write_call_script(
            group_path,
            current_part_paths,
            f"Generator comparison group {group_index:02d} completed.",
            20,
        )
        group_paths.append(group_path)
    run_all_path = os.path.join(output_dir, "run_all.cmd")
    write_call_script(
        run_all_path,
        group_paths,
        "All generator comparison groups completed.",
        30,
    )
    write_collect_script(os.path.join(output_dir, "collect_results.cmd"))
    write_validate_script(os.path.join(output_dir, "validate_all.cmd"), scene_runner)

    validation_results = []
    if args.validate_runner:
        validation_results = validate_configs(
            [row["config_path"] for row in planned_rows],
            scene_runner,
            args.validation_python,
        )

    selection_csv = os.path.join(output_dir, "selection_summary.csv")
    with open(selection_csv, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=tuple(selection_rows[0]))
        writer.writeheader()
        writer.writerows(selection_rows)
    schedule_csv = os.path.join(output_dir, "run_schedule.csv")
    schedule_fields = (
        "run_order",
        "group_index",
        "part_index",
        "run_id",
        "sample_id",
        "generator",
        "target_risk_level",
        "selection_index",
        "repeat_round",
        "traffic_manager_seed",
        "source",
        "config_path",
        "expected_run_root",
    )
    with open(schedule_csv, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=schedule_fields)
        writer.writeheader()
        writer.writerows(
            {field: row.get(field) for field in schedule_fields}
            for row in planned_rows
        )

    route = control_profile["route"]
    manifest = {
        "format": "generator_carla_comparison_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generators": list(GENERATORS),
        "target_levels": list(RISK_LEVELS),
        "traffic_seeds": list(TRAFFIC_SEEDS),
        "analysis_unit": "selected_scenario",
        "traffic_seed_role": "repeated_measure",
        "supports_significance_testing": False,
        "selection": {
            "method": args.selection,
            "per_generator_level": args.per_level,
            "description": (
                "每个生成器和目标档分别沿第一主变化方向选择 "
                "0.1/0.5/0.9 分位附近样本"
            ),
        },
        "source_files": source_files,
        "selected_records": os.path.relpath(
            selected_records_path, output_dir
        ).replace("\\", "/"),
        "selected_records_sha256": file_sha256(selected_records_path),
        "base_config": base_config_path,
        "base_config_sha256": file_sha256(base_config_path),
        "control_profile_id": control_profile["profile_id"],
        "control_profile_path": control_profile_path,
        "control_profile_sha256": file_sha256(control_profile_path),
        "scene_runner": scene_runner,
        "carla_root": carla_root,
        "runtime_output_root": runtime_output_root,
        "route_lock_required": True,
        "controller_mode": route["route_control_mode"],
        "acceptance_requirements": copy.deepcopy(
            control_profile["acceptance_requirements"]
        ),
        "route_control": {
            **copy.deepcopy(route),
            "route_controller": copy.deepcopy(control_profile["controller"]),
        },
        "design": {
            "type": "blocked_generator_risk_repeated_measure",
            "run_seed": args.run_seed,
            "group_count": len(group_paths),
            "parts_per_group": 3,
            "runs_per_part": 4,
            "description": (
                "9 个平衡组覆盖三生成器乘四风险档，每组拆为 3 个四场景小批次；"
                "交通种子作为重复测量并在组内轮换"
            ),
        },
        "scenario_count": len(selected),
        "scenario_count_by_generator": {
            generator: sum(
                record["provenance"]["generator"] == GENERATOR_IDS[generator]
                for record in selected
            )
            for generator in GENERATORS
        },
        "planned_run_count": len(planned_rows),
        "static_validation": {
            "requested": bool(args.validate_runner),
            "python": os.path.abspath(args.validation_python),
            "validated_count": len(validation_results),
            "passed_count": sum(row["valid"] for row in validation_results),
        },
        "runs": sorted(planned_rows, key=lambda row: row["run_order"]),
    }
    write_json(os.path.join(output_dir, "manifest.json"), manifest)
    if validation_results:
        validation_csv = os.path.join(output_dir, "static_validation.csv")
        with open(validation_csv, "w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=("config", "valid", "return_code", "message"),
            )
            writer.writeheader()
            writer.writerows(validation_results)
    write_readme(
        os.path.join(output_dir, "README.md"),
        manifest,
        group_paths,
        part_paths,
    )

    print(f"[PREPARE] 独立场景: {len(selected)}")
    print(f"[PREPARE] 计划运行: {len(planned_rows)}")
    print(f"[PREPARE] 平衡组: {len(group_paths)}")
    print(f"[PREPARE] 小批次: {len(part_paths)}")
    if args.validate_runner:
        print(
            f"[PREPARE] validate-only: "
            f"{sum(row['valid'] for row in validation_results)}/"
            f"{len(validation_results)}"
        )
    print(f"[PREPARE] 目录: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
