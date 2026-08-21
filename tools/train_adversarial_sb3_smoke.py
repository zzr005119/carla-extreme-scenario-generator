"""Validate the Stable-Baselines3 training pipeline without CARLA.

This entry point intentionally uses a deterministic mock risk function. It
proves environment compatibility, short training, model persistence, loading,
and prediction only; it does not provide policy-effect evidence.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import load_agent_config  # noqa: E402
from core.adversarial_gym_env import AdversarialGymEnv  # noqa: E402
from core.scenario_features import normalize_vector, parameter_vector  # noqa: E402
from core.scenario_validator import load_json  # noqa: E402


DEFAULT_RECORD_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "seed_v1",
    "example_record.json",
)
ALGORITHM_NAMES = ("ppo", "sac")


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _git_state():
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()
    return {"commit": commit, "worktree_dirty": bool(status)}


def _risk_level(score):
    if score >= 75.0:
        return "critical"
    if score >= 50.0:
        return "high"
    if score >= 25.0:
        return "medium"
    return "low"


class DeterministicMockRiskExecutor:
    """Cheap deterministic executor used only for training-pipeline checks."""

    def __init__(self):
        self.calls = []

    @staticmethod
    def score(record):
        values = normalize_vector(parameter_vector(record), clip=True)
        adverse = np.asarray(
            [
                values[0],
                values[1],
                values[2],
                values[3],
                values[4],
                1.0 - values[5],
                1.0 - values[6],
                values[7],
                1.0 - values[8],
                1.0 - values[9],
                values[10],
                1.0 - values[11],
                1.0 - values[12],
                1.0 - values[13],
                values[14],
            ],
            dtype=np.float64,
        )
        weights = np.asarray(
            [0.04, 0.08, 0.05, 0.03, 0.08, 0.08, 0.05, 0.06,
             0.10, 0.07, 0.10, 0.07, 0.04, 0.06, 0.09],
            dtype=np.float64,
        )
        score = float(np.dot(adverse, weights) / weights.sum() * 100.0)
        return round(min(100.0, max(0.0, score)), 6)

    def __call__(self, record, phase, step_index):
        score = self.score(record)
        collision_count = int(score >= 78.0)
        event_count = int(score >= 55.0)
        self.calls.append(
            {
                "sample_id": record["sample_id"],
                "phase": phase,
                "step_index": int(step_index),
                "score": score,
            }
        )
        return {
            "status": "completed",
            "observed_risk_score": score,
            "observed_risk_level": _risk_level(score),
            "risk_method": "deterministic_mock_v1",
            "collision_count": collision_count,
            "event_count": event_count,
            "run_valid": True,
            "strict_acceptance_passed": True,
            "carla_service_healthy": True,
            "run_dir": f"mock://deterministic-risk/{phase}/{step_index}",
        }


def _make_env(record, max_steps):
    config = load_agent_config()
    config["termination"]["max_steps"] = int(max_steps)
    executor = DeterministicMockRiskExecutor()
    env = AdversarialGymEnv(record=record, executor=executor, config=config)
    return env, executor


def _algorithm_class(name):
    try:
        from stable_baselines3 import PPO, SAC
    except ImportError as exc:
        raise RuntimeError(
            "缺少 Stable-Baselines3；请在 Carla666-0916 环境安装 "
            "requirements-rl-training.txt"
        ) from exc
    return {"ppo": PPO, "sac": SAC}[name]


def _model_kwargs(name, env, seed, total_timesteps, device):
    common = {
        "policy": "MlpPolicy",
        "env": env,
        "seed": int(seed),
        "device": device,
        "verbose": 0,
        "policy_kwargs": {"net_arch": [32, 32]},
    }
    if name == "ppo":
        rollout_steps = max(16, min(32, int(total_timesteps)))
        common.update(
            {
                "n_steps": rollout_steps,
                "batch_size": 16,
                "n_epochs": 2,
            }
        )
    else:
        common.update(
            {
                "learning_starts": max(1, min(8, int(total_timesteps) // 4)),
                "buffer_size": max(128, int(total_timesteps) * 2),
                "batch_size": 16,
                "train_freq": 1,
                "gradient_steps": 1,
            }
        )
    return common


def run_algorithm(
    name,
    record,
    output_root,
    total_timesteps,
    seed,
    max_steps,
    device,
    env_factory=None,
):
    algorithm = _algorithm_class(name)
    make_env = env_factory or (lambda: _make_env(record, max_steps))
    env, training_executor = make_env()
    model = algorithm(
        **_model_kwargs(name, env, seed, total_timesteps, device)
    )
    try:
        model.learn(total_timesteps=int(total_timesteps), progress_bar=False)
        model_path = os.path.join(output_root, "models", f"{name}_smoke_model.zip")
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        model.save(model_path)
    finally:
        env.close()

    prediction_env, prediction_executor = make_env()
    loaded = algorithm.load(model_path, env=prediction_env, device=device)
    try:
        observation, reset_info = prediction_env.reset(seed=int(seed) + 1000)
        action, _ = loaded.predict(observation, deterministic=True)
        next_observation, reward, terminated, truncated, info = prediction_env.step(
            action
        )
    finally:
        prediction_env.close()

    return {
        "algorithm": name,
        "requested_total_timesteps": int(total_timesteps),
        "trained_num_timesteps": int(model.num_timesteps),
        "model_path": os.path.abspath(model_path),
        "model_exists": os.path.isfile(model_path),
        "training_executor_call_count": len(training_executor.calls),
        "prediction_executor_call_count": len(prediction_executor.calls),
        "prediction_executor_last_call": (
            prediction_executor.calls[-1]
            if prediction_executor.calls
            else None
        ),
        "prediction": {
            "reset_sample_id": reset_info["sample_id"],
            "action": np.asarray(action, dtype=np.float32).tolist(),
            "observation_shape": list(np.asarray(next_observation).shape),
            "reward": float(reward),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "proposal_valid": bool(info["proposal_valid"]),
        },
    }


def run_checks(record, max_steps, env_factory=None):
    from gymnasium.utils.env_checker import check_env as gymnasium_check_env
    from stable_baselines3.common.env_checker import check_env as sb3_check_env

    make_env = env_factory or (lambda: _make_env(record, max_steps))
    gym_env, _ = make_env()
    try:
        gymnasium_check_env(gym_env, skip_render_check=True)
    finally:
        gym_env.close()
    sb3_env, _ = make_env()
    try:
        sb3_check_env(sb3_env, warn=True)
    finally:
        sb3_env.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description="不连接 CARLA，验证 SB3 check_env、短训练和模型持久化"
    )
    parser.add_argument("--record", default=DEFAULT_RECORD_PATH)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--algorithms",
        nargs="+",
        choices=ALGORITHM_NAMES,
        default=list(ALGORITHM_NAMES),
    )
    parser.add_argument("--total-timesteps", type=int, default=64)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.total_timesteps <= 0:
        raise ValueError("--total-timesteps 必须大于 0")
    if args.max_steps <= 0:
        raise ValueError("--max-steps 必须大于 0")

    import gymnasium
    import stable_baselines3
    import torch

    output_root = os.path.abspath(args.output_root)
    os.makedirs(output_root, exist_ok=True)
    record = load_json(os.path.abspath(args.record))
    run_checks(record, args.max_steps)

    summary = {
        "format": "adversarial_sb3_smoke_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "evidence_kind": "training_plumbing_only",
        "executor_kind": "deterministic_mock_v1",
        "carla_connected": False,
        "supports_policy_effect_claim": False,
        "git": _git_state(),
        "versions": {
            "python": sys.version.split()[0],
            "gymnasium": gymnasium.__version__,
            "stable_baselines3": stable_baselines3.__version__,
            "torch": torch.__version__,
        },
        "seed": int(args.seed),
        "record_path": os.path.abspath(args.record),
        "max_steps": int(args.max_steps),
        "checks": {
            "gymnasium_check_env": "passed",
            "stable_baselines3_check_env": "passed",
        },
        "algorithms": [],
    }
    summary_path = os.path.join(output_root, "training_summary.json")
    _write_json(summary_path, summary)

    for index, name in enumerate(args.algorithms):
        result = run_algorithm(
            name=name,
            record=record,
            output_root=output_root,
            total_timesteps=args.total_timesteps,
            seed=args.seed + index,
            max_steps=args.max_steps,
            device=args.device,
        )
        summary["algorithms"].append(result)
        _write_json(summary_path, summary)

    print(f"stable_baselines3={stable_baselines3.__version__}")
    print(f"checks={summary['checks']}")
    for result in summary["algorithms"]:
        print(
            f"algorithm={result['algorithm']}, "
            f"timesteps={result['trained_num_timesteps']}, "
            f"model_exists={result['model_exists']}, "
            f"prediction_valid={result['prediction']['proposal_valid']}"
        )
    print(f"[RESULT_DIR] {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
