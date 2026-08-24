"""Evaluate one frozen CARLA RL checkpoint on the held-out test split."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.adversarial_agent import load_agent_config  # noqa: E402
from core.adversarial_gym_env import AdversarialGymEnv  # noqa: E402
from core.carla_rl_plan import PlannedScenarioSampler, load_multiscene_plan  # noqa: E402
from core.scenario_validator import load_json  # noqa: E402
from tools.run_adversarial_episode import (  # noqa: E402
    CarlaSceneExecutor,
    _project_path,
    _safe_name,
    load_loop_config,
)


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def evaluate(plan_path, config_path, model_path, output_root, algorithm, *, split="test", seed=None, max_scenarios=0):
    import gymnasium  # noqa: F401
    from stable_baselines3 import PPO, SAC

    plan = load_multiscene_plan(plan_path)
    config = load_loop_config(config_path)
    if split not in ("dev", "test"):
        raise ValueError("独立评估 split 只能为 dev 或 test")
    rows = plan["splits"][split]
    if max_scenarios:
        rows = rows[: int(max_scenarios)]
    if not rows:
        raise ValueError("test split 为空")
    eval_seed = int(seed if seed is not None else plan["seed"] + 100000)
    sampler = PlannedScenarioSampler(rows, seed=eval_seed)
    output_root = Path(output_root).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    episode_id = _safe_name(f"rl_test_{algorithm.lower()}_{eval_seed}_{timestamp}")
    episode_dir = output_root / "episodes" / episode_id
    runtime_root = output_root / "runtime" / episode_id
    base_config = load_json(_project_path(config["base_carla_config_path"]))
    route_profile = load_json(_project_path(config["route_profile_path"]))
    agent_config = load_agent_config(_project_path(config["agent_config_path"]))
    executor = CarlaSceneExecutor(
        str(episode_dir), str(runtime_root), base_config, route_profile,
        config["acceptance_requirements"], int(config["runtime"]["traffic_manager_port"]),
        int(config["runtime"]["scene_timeout_seconds"]), episode_id, agent_config,
    )
    env = AdversarialGymEnv(
        record_sampler=sampler,
        executor=executor,
        config=agent_config,
    )
    model_cls = PPO if algorithm.upper() == "PPO" else SAC
    model = model_cls.load(str(Path(model_path).expanduser().resolve()), env=env, device="auto")
    max_steps = int(agent_config["termination"]["max_steps"])
    rows_out = []
    try:
        for index in range(len(rows)):
            observation, reset_info = env.reset(seed=eval_seed if index == 0 else None)
            transitions = []
            for _ in range(max_steps):
                action, _ = model.predict(observation, deterministic=True)
                observation, reward, terminated, truncated, info = env.step(action)
                transitions.append(
                    {
                        "reward": float(reward),
                        "terminated": bool(terminated),
                        "truncated": bool(truncated),
                        "failure_reason": info.get("failure_reason"),
                    }
                )
                if terminated or truncated:
                    break
            final_transition = env.core.last_transition or {}
            candidate = final_transition.get("candidate") or {}
            candidate_risk = candidate.get("observed_risk") or {}
            baseline = reset_info.get("baseline_result") or {}
            rows_out.append(
                {
                    "index": index,
                    "sample_id": reset_info.get("sample_id"),
                    "canonical_sample_id": (reset_info.get("sampling") or {}).get("canonical_sample_id"),
                    "generator": (reset_info.get("sampling") or {}).get("generator"),
                    "target_risk_level": (reset_info.get("sampling") or {}).get("target_risk_level"),
                    "baseline": {
                        "score": baseline.get("observed_risk_score"),
                        "level": baseline.get("observed_risk_level"),
                        "run_dir": baseline.get("run_dir"),
                        "strict_acceptance_passed": baseline.get("strict_acceptance_passed"),
                    },
                    "final_candidate": {
                        "score": candidate_risk.get("score"),
                        "level": candidate_risk.get("level"),
                        "run_dir": candidate_risk.get("run_dir"),
                    },
                    "transition_count": len(transitions),
                    "transitions": transitions,
                    "termination_reason": (final_transition.get("reason")),
                }
            )
    finally:
        env.close()
    summary = {
        "format": "carla_online_rl_test_evaluation_v1",
        "algorithm": algorithm.upper(),
        "model_path": str(Path(model_path).expanduser().resolve()),
        "scenario_plan_path": str(Path(plan_path).expanduser().resolve()),
        "scenario_plan_sha256": plan["plan_sha256"],
        "split": split,
        "test_count": len(rows_out),
        "seed": eval_seed,
        "rows": rows_out,
        "evidence_kind": "carla_online_rl_independent_test_runtime",
    }
    _write_json(output_root / "test_evaluation_summary.json", summary)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="在冻结 test split 上评估 CARLA RL checkpoint")
    parser.add_argument("--scenario-plan", required=True)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "adversarial_loop_multistep_v1.json"))
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--algorithm", choices=("PPO", "SAC"), required=True)
    parser.add_argument("--split", choices=("dev", "test"), default="test")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--max-scenarios", type=int, default=0)
    parser.add_argument("--allow-online-carla", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.allow_online_carla:
        raise SystemExit("test 评估必须显式提供 --allow-online-carla")
    summary = evaluate(
        args.scenario_plan,
        args.config,
        args.model,
        args.output_root,
        args.algorithm,
        split=args.split,
        seed=args.seed,
        max_scenarios=args.max_scenarios,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
