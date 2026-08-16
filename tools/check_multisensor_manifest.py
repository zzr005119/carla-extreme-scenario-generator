"""验收主动补样清单中的多传感器写盘结果。"""

import argparse
import json
import os


def parse_args():
    parser = argparse.ArgumentParser(description="检查清单的 RGB、Depth、Semantic 帧数")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--min-completed", type=int, default=0)
    parser.add_argument("--require-all", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    with open(os.path.abspath(args.manifest), "r", encoding="utf-8") as file:
        manifest = json.load(file)
    runs = manifest.get("runs", [])
    required = manifest.get("acceptance_requirements", {})
    minimum = {
        "rgb": int(required.get("minimum_rgb_frames", 100)),
        "depth": int(required.get("minimum_depth_frames", 100)),
        "semantic": int(required.get("minimum_semantic_frames", 100)),
    }
    completed = 0
    failures = []
    for run in runs:
        matches = []
        for root, _, files in os.walk(run["expected_run_root"]):
            if "metadata.json" not in files:
                continue
            metadata_path = os.path.join(root, "metadata.json")
            try:
                with open(metadata_path, "r", encoding="utf-8") as file:
                    metadata = json.load(file)
            except (OSError, json.JSONDecodeError):
                continue
            actual_seed = (metadata.get("simulation") or {}).get(
                "traffic_manager_seed"
            )
            if actual_seed is not None and int(actual_seed) == int(
                run["traffic_manager_seed"]
            ):
                matches.append((os.path.getmtime(metadata_path), metadata_path, metadata))
        if not matches:
            failures.append((run["run_id"], "metadata_missing"))
            continue
        _, metadata_path, metadata = max(matches, key=lambda item: item[0])
        frames = metadata.get("frames", {})
        status = (metadata.get("sensor_pipeline") or {}).get("status")
        missing = [
            name for name, threshold in minimum.items() if int(frames.get(name, 0)) < threshold
        ]
        if status != "completed":
            missing.append("sensor_pipeline_status")
        if missing:
            failures.append((run["run_id"], ",".join(missing)))
            continue
        completed += 1

    print(
        f"[MULTISENSOR_CHECK] completed={completed}/{len(runs)} "
        f"required={minimum} failures={len(failures)}"
    )
    for run_id, reason in failures[:20]:
        print(f"[MULTISENSOR_CHECK] failed={run_id} reason={reason}")
    if completed < args.min_completed:
        return 2
    if args.require_all and failures:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
