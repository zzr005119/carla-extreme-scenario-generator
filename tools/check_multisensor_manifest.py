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
        metadata_path = os.path.join(run["expected_run_root"], "metadata.json")
        if not os.path.isfile(metadata_path):
            failures.append((run["run_id"], "metadata_missing"))
            continue
        with open(metadata_path, "r", encoding="utf-8") as file:
            metadata = json.load(file)
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
