"""准备确定性 waypoint 跟踪控制器的单场景 CARLA 冒烟回归。"""

import argparse
import copy
import json
import os
import shutil


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DEFAULT_SOURCE_CONFIG = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "cvae_repeatability_v2",
    "configs",
    "cvae_medium_20260813_0103__tm_20260821.json",
)
DEFAULT_OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "route_controller_smoke_v1",
)
RUNTIME_OUTPUT_ROOT = (
    r"F:\Carla\test\output\model_generated_validation\route_controller_smoke_v1"
)
RUN_ID = "cvae_medium_20260813_0103__route_controller_smoke"


def parse_args():
    parser = argparse.ArgumentParser(description="准备路线控制器单场景冒烟回归")
    parser.add_argument("--source-config", default=DEFAULT_SOURCE_CONFIG)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def write_cmd(path, lines):
    with open(path, "w", encoding="ascii", newline="") as file:
        file.write("\r\n".join(lines))


def controller_settings():
    return {
        "target_speed_kmh": 29.0,
        "lookahead_m": 6.0,
        "steering_gain": 1.35,
        "maximum_steer": 0.8,
        "maximum_steer_delta": 0.1,
        "speed_kp": 0.45,
        "speed_ki": 0.05,
        "speed_kd": 0.02,
        "maximum_throttle": 0.75,
        "maximum_brake": 1.0,
        "ego_lead_brake_ttc_seconds": 2.0,
        "ego_lead_brake_gap_m": 5.0,
        "ego_pedestrian_brake_distance_m": 8.0,
        "ego_pedestrian_brake_lateral_m": 4.0,
    }


def main():
    args = parse_args()
    source_config_path = os.path.abspath(args.source_config)
    output_dir = os.path.abspath(args.output_dir)
    if os.path.isdir(output_dir) and os.listdir(output_dir):
        if not args.force:
            raise FileExistsError(f"输出目录非空: {output_dir}，如需覆盖请加 --force")
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    config = copy.deepcopy(load_json(source_config_path))
    config["scenario"]["name"] = RUN_ID
    config["scenario"]["traffic_manager_seed"] = 20260821
    config["traffic"].update(
        {
            "route_lock_enabled": True,
            "route_control_mode": "waypoint_follower",
            "route_length_m": 300.0,
            "route_step_m": 2.0,
            "route_deviation_tolerance_m": 3.0,
            "route_controller": controller_settings(),
        }
    )
    config["output"]["root"] = RUNTIME_OUTPUT_ROOT
    config_path = os.path.join(output_dir, "config.json")
    write_json(config_path, config)

    expected_run_root = os.path.join(RUNTIME_OUTPUT_ROOT, RUN_ID)
    manifest = {
        "format": "cvae_carla_route_repeatability_v2",
        "source_config": source_config_path,
        "route_lock_required": True,
        "traffic_seeds": [20260821],
        "sample_ids": ["cvae_medium_20260813_0103"],
        "controller_mode": "waypoint_follower",
        "acceptance_requirements": {
            "sensor_status": "completed",
            "server_status": "healthy",
            "minimum_rgb_frames": 100,
            "route_control_mode": "waypoint_follower",
            "minimum_route_both_on_rate": 1.0,
            "maximum_route_deviation_m": 3.0,
        },
        "runs": [
            {
                "run_id": RUN_ID,
                "sample_id": "cvae_medium_20260813_0103",
                "target_risk_level": "medium",
                "traffic_manager_seed": 20260821,
                "repeat_round": 1,
                "source": "route_controller_smoke_v1",
                "planned": True,
                "run_order": 1,
                "part_index": 1,
                "config_path": config_path,
                "expected_run_root": expected_run_root,
            }
        ],
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    write_json(manifest_path, manifest)

    write_cmd(
        os.path.join(output_dir, "run_smoke.cmd"),
        [
            "@echo off",
            "setlocal EnableExtensions",
            'set "PYTHONUTF8=1"',
            "chcp 65001 >nul",
            'cd /d "F:\\Carla\\test"',
            "",
            'python -u "F:\\Carla\\test\\scenes\\scene_04_parameterized.py" '
            '--config "%~dp0config.json"',
            "if errorlevel 1 goto :failed",
            "",
            'cd /d "%~dp0..\\..\\.."',
            'python tools\\collect_carla_repeatability.py '
            '--manifest "%~dp0manifest.json"',
            "if errorlevel 1 goto :failed",
            "",
            "echo [DONE] Route controller smoke regression passed.",
            "exit /b 0",
            "",
            ":failed",
            "echo [FAILED] Route controller smoke regression failed.",
            "exit /b 1",
            "",
        ],
    )

    readme_path = os.path.join(output_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as file:
        file.write(
            "# 路线控制器单场景冒烟回归\n\n"
            "该回归使用中风险 CVAE 代表样本验证主车与前车的确定性 waypoint "
            "跟踪控制。\n\n"
            "验收要求：仿真完成、RGB 写盘完成、CARLA 服务健康、路线严格验收 "
            "`1/1`；RGB 不少于 `100` 帧，双车同时在途率为 `1.0`，主车与前车"
            "最大路线偏差均不超过 `3.0 m`。\n\n"
            "启动 CARLAUE4 后运行：\n\n"
            "```cmd\n"
            f'"{os.path.join(output_dir, "run_smoke.cmd")}"\n'
            "```\n"
        )

    print(f"[PREPARE] 配置: {config_path}")
    print(f"[PREPARE] 清单: {manifest_path}")
    print(f"[PREPARE] 命令: {os.path.join(output_dir, 'run_smoke.cmd')}")


if __name__ == "__main__":
    main()
