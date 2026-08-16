"""准备一次低频 RGB、Depth、Semantic 和 Collision 传感器冒烟。"""

import argparse
import copy
import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = (
    PROJECT_ROOT / "data" / "scenarios" / "route_controller_smoke_v1" / "config.json"
)


def parse_args():
    parser = argparse.ArgumentParser(description="准备多传感器单样本冒烟")
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--runtime-output-root", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    source_path = Path(os.path.abspath(args.source_config))
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    with source_path.open("r", encoding="utf-8") as file:
        config = copy.deepcopy(json.load(file))

    config["scenario"]["name"] = "cvae_medium_20260813_0103__multisensor_smoke"
    config["scenario"]["traffic_manager_port"] = 8100
    config["sensors"]["camera"].update(
        {
            "width": 640,
            "height": 360,
            "sensor_tick": 0.2,
            "writer_workers": 1,
            "writer_queue_size": 8,
        }
    )
    for sensor_name in ("rgb", "depth", "semantic", "collision"):
        config["sensors"][sensor_name]["enabled"] = True
    config["output"]["root"] = os.path.abspath(args.runtime_output_root)

    config_path = output_dir / "config.json"
    with config_path.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)

    print(f"[MULTISENSOR_PREPARE] config={config_path}")
    print(
        "[MULTISENSOR_PREPARE] sensors=rgb,depth,semantic,collision | "
        "resolution=640x360 | tick=0.2s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
