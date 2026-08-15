"""可恢复地执行反馈候选 CARLA 外部验证清单。"""

import argparse
import json
import os
import subprocess
import sys
import time


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.collect_carla_repeatability import collect_row  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="执行反馈候选 CARLA 外部验证")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--group-index", type=int)
    parser.add_argument("--part-index", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--pause-seconds", type=float, default=10.0)
    parser.add_argument("--traffic-manager-port", type=int)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def main():
    args = parse_args()
    if args.group_index is not None and args.part_index is not None:
        raise ValueError("--group-index 与 --part-index 不能同时使用")
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit 必须大于 0")
    manifest_path = os.path.abspath(args.manifest)
    manifest = load_json(manifest_path)
    if manifest.get("format") != "feedback_candidate_validation_v1":
        raise ValueError("不支持的反馈候选验证清单格式")

    runs = sorted(manifest["runs"], key=lambda row: int(row["run_order"]))
    if args.group_index is not None:
        runs = [row for row in runs if int(row["group_index"]) == args.group_index]
    if args.part_index is not None:
        runs = [row for row in runs if int(row["part_index"]) == args.part_index]
    if not runs:
        raise ValueError("筛选后没有待运行配置")

    acceptance = manifest["acceptance_requirements"]
    scene_runner = manifest["scene_runner"]
    traffic_manager_port = (
        args.traffic_manager_port
        if args.traffic_manager_port is not None
        else int(os.environ.get("CARLA_TRAFFIC_MANAGER_PORT", "8100"))
    )
    executed = 0
    skipped = 0
    for index, run in enumerate(runs, 1):
        existing = collect_row(
            run,
            route_lock_required=True,
            acceptance_requirements=acceptance,
        )
        if existing.get("acceptance_status") == "completed" and not args.force:
            skipped += 1
            print(
                f"[SKIP {index}/{len(runs)}] {run['run_id']} 已通过严格验收",
                flush=True,
            )
            continue
        if args.limit is not None and executed >= args.limit:
            break

        command = [
            sys.executable,
            scene_runner,
            "--config",
            run["config_path"],
            "--traffic-manager-port",
            str(traffic_manager_port),
        ]
        print(f"[RUN {index}/{len(runs)}] {run['run_id']}", flush=True)
        completed = subprocess.run(command, cwd=manifest["carla_root"], check=False)
        if completed.returncode != 0:
            print(
                f"[FAILED] {run['run_id']} 退出码 {completed.returncode}",
                flush=True,
            )
            return completed.returncode or 2
        result = collect_row(
            run,
            route_lock_required=True,
            acceptance_requirements=acceptance,
        )
        if result.get("acceptance_status") != "completed":
            print(
                f"[FAILED] {run['run_id']} 严格验收失败: "
                f"{result.get('acceptance_failures')}",
                flush=True,
            )
            return 3
        executed += 1
        print(
            f"[ACCEPTED] {run['run_id']} | risk={result['risk_score']:.3f} | "
            f"level={result['observed_risk_level']} | collisions={result['collision_count']}",
            flush=True,
        )
        if args.pause_seconds > 0:
            time.sleep(args.pause_seconds)

    print(
        f"[DONE] executed={executed} | skipped={skipped} | selected_runs={len(runs)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
