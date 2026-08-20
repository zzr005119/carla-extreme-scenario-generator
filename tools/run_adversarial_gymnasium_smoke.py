"""Run one real CARLA episode through the optional Gymnasium environment."""

import argparse
import json
import os
import sys
from datetime import datetime

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import load_agent_config  # noqa: E402
from core.adversarial_gym_env import AdversarialGymEnv  # noqa: E402
from core.scenario_validator import load_json  # noqa: E402
from tools.run_adversarial_episode import (  # noqa: E402
    CarlaSceneExecutor,
    _project_path,
    _safe_name,
    load_loop_config,
    load_record,
)


DEFAULT_LOOP_CONFIG = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_loop_multistep_v1.json",
)


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="通过 Gymnasium 环境执行 CARLA 基线和连续候选冒烟"
    )
    parser.add_argument("--config", default=DEFAULT_LOOP_CONFIG)
    parser.add_argument("--record", required=True)
    parser.add_argument("--sample-id")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--runtime-output-root")
    parser.add_argument("--traffic-manager-port", type=int)
    parser.add_argument("--steps", type=int, default=2)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.steps <= 0:
        raise ValueError("--steps 必须大于 0")

    loop_config = load_loop_config(args.config)
    record = load_record(args.record, args.sample_id)
    output_root = os.path.abspath(args.output_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    episode_id = _safe_name(f"{record['sample_id']}_gym_{timestamp}")
    episode_dir = os.path.join(output_root, "episodes", episode_id)
    os.makedirs(episode_dir, exist_ok=False)
    runtime_output_root = os.path.abspath(
        args.runtime_output_root
        or os.path.join(output_root, "runtime", episode_id)
    )
    traffic_manager_port = (
        args.traffic_manager_port
        or int(os.environ.get("CARLA_TRAFFIC_MANAGER_PORT", 0))
        or int(loop_config["runtime"]["traffic_manager_port"])
    )

    base_config = load_json(_project_path(loop_config["base_carla_config_path"]))
    route_profile = load_json(_project_path(loop_config["route_profile_path"]))
    executor = CarlaSceneExecutor(
        episode_dir,
        runtime_output_root,
        base_config,
        route_profile,
        loop_config["acceptance_requirements"],
        traffic_manager_port,
        loop_config["runtime"]["scene_timeout_seconds"],
        episode_id,
    )
    env = AdversarialGymEnv(
        record=record,
        executor=executor,
        config=load_agent_config(_project_path(loop_config["agent_config_path"])),
    )
    summary_path = os.path.join(episode_dir, "gymnasium_episode_summary.json")
    summary = {
        "format": "adversarial_gymnasium_smoke_v1",
        "evidence_kind": "carla_runtime",
        "episode_id": episode_id,
        "gymnasium_version": __import__("gymnasium").__version__,
        "initial_record": record,
        "fixed_action": loop_config["fixed_action"],
        "requested_steps": args.steps,
        "runtime_output_root": runtime_output_root,
        "status": "running",
        "reset": None,
        "transitions": [],
    }
    _write_json(summary_path, summary)

    try:
        observation, reset_info = env.reset(seed=record["scenario"]["traffic_manager_seed"])
        summary["reset"] = {
            "observation": observation.tolist(),
            "info": reset_info,
        }
        _write_json(summary_path, summary)

        action = np.asarray(loop_config["fixed_action"], dtype=np.float32)
        for _ in range(args.steps):
            next_observation, reward, terminated, truncated, info = env.step(action)
            summary["transitions"].append(
                {
                    "observation": next_observation.tolist(),
                    "reward": reward,
                    "terminated": terminated,
                    "truncated": truncated,
                    "info": info,
                    "agent_transition": env.core.last_transition,
                }
            )
            _write_json(summary_path, summary)
            if terminated or truncated:
                break
        summary["status"] = (
            "failed"
            if summary["transitions"]
            and summary["transitions"][-1]["terminated"]
            else "completed"
        )
        summary["termination_reason"] = (
            summary["transitions"][-1]["info"]["termination_reason"]
            if summary["transitions"]
            else None
        )
    except Exception as exc:
        summary["status"] = "failed"
        summary["termination_reason"] = str(exc)
        _write_json(summary_path, summary)
        raise
    finally:
        env.close()

    _write_json(summary_path, summary)
    print(f"[GYM] episode_status={summary['status']}")
    print(f"[GYM] transitions={len(summary['transitions'])}")
    print(f"[GYM] summary={summary_path}")
    print(f"[RESULT_DIR] {episode_dir}")
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

