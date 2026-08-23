"""Explicitly gated online RL training entry for the CARLA Gymnasium adapter."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.adversarial_gym_env import AdversarialGymEnv  # noqa: E402
from core.adversarial_agent import load_agent_config  # noqa: E402
from core.scenario_validator import load_json  # noqa: E402
from tools.run_adversarial_episode import (  # noqa: E402
    CarlaSceneExecutor,
    _project_path,
    _safe_name,
    load_loop_config,
    load_record,
)


def dependency_status():
    return {
        "gymnasium": bool(importlib.util.find_spec("gymnasium")),
        "stable_baselines3": bool(importlib.util.find_spec("stable_baselines3")),
    }


def build_training_plan(config_path, record_path, output_root, *, algorithm="PPO", steps=1000):
    config = load_loop_config(config_path)
    record = load_record(record_path)
    if algorithm.upper() not in {"PPO", "SAC"}:
        raise ValueError("algorithm 只支持 PPO 或 SAC")
    if steps < 1:
        raise ValueError("steps 必须大于 0")
    return {
        "format": "carla_online_rl_training_plan_v1",
        "algorithm": algorithm.upper(),
        "requested_steps": int(steps),
        "carla_episode_budget": int(steps) + 1,
        "record_sample_id": record["sample_id"],
        "output_root": str(Path(output_root).expanduser().resolve()),
        "dependency_status": dependency_status(),
        "carla_server_started_by_script": False,
        "status": "blocked_optional_dependency" if not all(dependency_status().values()) else "ready",
        "evidence_kind": "online_rl_preflight",
    }


def train(plan, config_path, record_path, *, allow_online_carla=False):
    if not allow_online_carla:
        raise RuntimeError("在线 CARLA RL 训练必须显式提供 --allow-online-carla")
    if plan["status"] != "ready":
        raise RuntimeError(f"可选依赖未齐全: {plan['dependency_status']}")
    import gymnasium  # noqa: F401
    from stable_baselines3 import PPO, SAC

    config = load_loop_config(config_path)
    record = load_record(record_path)
    output_root = Path(plan["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    episode_id = _safe_name(f"rl_{record['sample_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    episode_dir = output_root / "episodes" / episode_id
    episode_dir.mkdir(parents=True, exist_ok=False)
    runtime_root = output_root / "runtime" / episode_id
    base_config = load_json(_project_path(config["base_carla_config_path"]))
    route_profile = load_json(_project_path(config["route_profile_path"]))
    agent_config = load_agent_config(_project_path(config["agent_config_path"]))
    executor = CarlaSceneExecutor(
        str(episode_dir), str(runtime_root), base_config, route_profile,
        config["acceptance_requirements"], int(config["runtime"]["traffic_manager_port"]),
        int(config["runtime"]["scene_timeout_seconds"]), episode_id, agent_config,
    )
    env = AdversarialGymEnv(record=record, executor=executor, config=agent_config)
    algorithm = plan["algorithm"]
    model_cls = PPO if algorithm == "PPO" else SAC
    try:
        model_kwargs = {
            "verbose": 1,
            "device": "auto",
            "seed": record["scenario"]["traffic_manager_seed"],
        }
        if algorithm == "PPO":
            # PPO collects a rollout before learning; keep that rollout within
            # the explicit CARLA budget instead of silently using 2048 steps.
            rollout_steps = max(2, min(int(plan["requested_steps"]), 16))
            model_kwargs.update({"n_steps": rollout_steps, "batch_size": rollout_steps})
        model = model_cls("MlpPolicy", env, **model_kwargs)
        model.learn(total_timesteps=plan["requested_steps"])
        model_path = output_root / f"{episode_id}_{algorithm.lower()}"
        model.save(str(model_path))
        summary = dict(plan)
        summary.update({
            "status": "completed",
            "execution_started": True,
            "model_path": str(model_path),
            "evidence_kind": "carla_online_rl_runtime",
        })
        return summary
    finally:
        env.close()


def parse_args():
    parser = argparse.ArgumentParser(description="CARLA 在线 RL 训练入口（显式确认）")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "adversarial_loop_multistep_v1.json"))
    parser.add_argument("--record", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--algorithm", choices=("PPO", "SAC"), default="PPO")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-online-carla", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    plan = build_training_plan(args.config, args.record, args.output_root, algorithm=args.algorithm, steps=args.steps)
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    summary = train(plan, args.config, args.record, allow_online_carla=args.allow_online_carla)
    path = Path(args.output_root).expanduser().resolve() / "rl_training_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
