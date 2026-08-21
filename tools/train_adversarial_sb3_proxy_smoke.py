"""Run a short SB3 training check against the frozen 27D risk proxy."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import load_agent_config  # noqa: E402
from core.adversarial_gym_env import AdversarialGymEnv  # noqa: E402
from core.adversarial_proxy_executor import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    FrozenRiskProxyExecutor,
    load_proxy_executor_config,
)
from core.scenario_validator import load_json  # noqa: E402
from tools.train_adversarial_sb3_smoke import (  # noqa: E402
    ALGORITHM_NAMES,
    run_algorithm,
    run_checks,
)


DEFAULT_RECORD_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "seed_v1",
    "example_record.json",
)
DEFAULT_AGENT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_agent_proxy_training_v1.json",
)


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


def parse_args():
    parser = argparse.ArgumentParser(
        description="使用冻结 27 维风险代理验证 SB3 训练链路"
    )
    parser.add_argument("--executor-config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--agent-config", default=DEFAULT_AGENT_CONFIG_PATH)
    parser.add_argument("--record", default=DEFAULT_RECORD_PATH)
    parser.add_argument("--model-path")
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--algorithms",
        nargs="+",
        choices=ALGORITHM_NAMES,
        default=list(ALGORITHM_NAMES),
    )
    parser.add_argument("--total-timesteps", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.total_timesteps <= 0:
        raise ValueError("--total-timesteps 必须大于 0")

    import gymnasium
    import stable_baselines3
    import torch

    executor_config = load_proxy_executor_config(args.executor_config)
    agent_config = load_agent_config(args.agent_config)
    if float(agent_config["reward"]["collision_event_reward"]) != 0.0:
        raise ValueError("代理训练不能启用未建模的 collision 奖励通道")
    if float(agent_config["reward"]["event_reward"]) != 0.0:
        raise ValueError("代理训练不能启用未建模的 event 奖励通道")

    record = load_json(os.path.abspath(args.record))
    max_steps = int(agent_config["termination"]["max_steps"])

    def make_env():
        executor = FrozenRiskProxyExecutor(
            config=executor_config,
            model_path=args.model_path,
        )
        env = AdversarialGymEnv(
            record=record,
            executor=executor,
            config=agent_config,
        )
        return env, executor

    metadata_executor = FrozenRiskProxyExecutor(
        config=executor_config,
        model_path=args.model_path,
    )
    run_checks(record, max_steps, env_factory=make_env)

    output_root = os.path.abspath(args.output_root)
    os.makedirs(output_root, exist_ok=True)
    summary = {
        "format": "adversarial_sb3_proxy_smoke_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "evidence_kind": "frozen_proxy_training",
        "carla_connected": False,
        "supports_carla_policy_effect_claim": False,
        "policy_effect_scope": "proxy_environment_only",
        "git": _git_state(),
        "versions": {
            "python": sys.version.split()[0],
            "gymnasium": gymnasium.__version__,
            "stable_baselines3": stable_baselines3.__version__,
            "torch": torch.__version__,
        },
        "seed": int(args.seed),
        "record_path": os.path.abspath(args.record),
        "agent_config_path": os.path.abspath(args.agent_config),
        "executor_config_path": os.path.abspath(args.executor_config),
        "executor": metadata_executor.metadata(),
        "reward_channel_policy": {
            "available": ["risk"],
            "collision_event_reward": 0.0,
            "event_reward": 0.0,
            "reason": "冻结 V5 代理只预测连续风险分，不预测碰撞或安全事件",
        },
        "checks": {
            "model_hash": "passed",
            "feature_contract_27d": "passed",
            "gymnasium_check_env": "passed",
            "stable_baselines3_check_env": "passed",
        },
        "algorithms": [],
    }
    summary_path = os.path.join(output_root, "proxy_training_summary.json")
    _write_json(summary_path, summary)

    for index, name in enumerate(args.algorithms):
        result = run_algorithm(
            name=name,
            record=record,
            output_root=output_root,
            total_timesteps=args.total_timesteps,
            seed=args.seed + index,
            max_steps=max_steps,
            device=args.device,
            env_factory=make_env,
        )
        summary["algorithms"].append(result)
        _write_json(summary_path, summary)

    print(f"executor={executor_config['executor_id']}")
    print(f"model_sha256={metadata_executor.model_sha256}")
    print(f"checks={summary['checks']}")
    for result in summary["algorithms"]:
        last_call = result["prediction_executor_last_call"] or {}
        print(
            f"algorithm={result['algorithm']}, "
            f"timesteps={result['trained_num_timesteps']}, "
            f"prediction_valid={result['prediction']['proposal_valid']}, "
            f"proxy_score={last_call.get('score')}"
        )
    print(f"[RESULT_DIR] {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
