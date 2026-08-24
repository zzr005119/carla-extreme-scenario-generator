"""Explicitly gated, resumable online RL training entry for CARLA."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
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
    load_record,
)


def dependency_status():
    return {
        "gymnasium": bool(importlib.util.find_spec("gymnasium")),
        "stable_baselines3": bool(importlib.util.find_spec("stable_baselines3")),
    }


def build_training_plan(
    config_path,
    record_path=None,
    output_root=None,
    *,
    algorithm="PPO",
    steps=1000,
    scenario_plan_path=None,
    checkpoint_every=1000,
    seed=None,
):
    config = load_loop_config(config_path)
    record = load_record(record_path) if record_path else None
    if algorithm.upper() not in {"PPO", "SAC"}:
        raise ValueError("算法只支持 PPO 或 SAC")
    if steps < 1:
        raise ValueError("steps 必须大于 0")
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every 必须大于 0")
    scenario_plan = load_multiscene_plan(scenario_plan_path) if scenario_plan_path else None
    if scenario_plan is None and record is None:
        raise ValueError("必须提供 --record 或 --scenario-plan")
    training_seed = int(seed) if seed is not None else int(
        record["scenario"]["traffic_manager_seed"] if record else scenario_plan["seed"]
    )
    dependency = dependency_status()
    plan = {
        "format": "carla_online_rl_training_plan_v1",
        "algorithm": algorithm.upper(),
        "requested_steps": int(steps),
        "checkpoint_every": int(checkpoint_every),
        "training_seed": training_seed,
        "carla_episode_budget": int(steps) + 1,
        "record_sample_id": record["sample_id"] if record else None,
        "output_root": str(Path(output_root).expanduser().resolve()) if output_root else None,
        "dependency_status": dependency,
        "carla_server_started_by_script": False,
        "status": "blocked_optional_dependency" if not all(dependency.values()) else "ready",
        "evidence_kind": "online_rl_preflight",
    }
    if scenario_plan is not None:
        agent_config = load_agent_config(_project_path(config["agent_config_path"]))
        max_steps = int(agent_config["termination"]["max_steps"])
        plan.update(
            {
                "scenario_plan_path": str(Path(scenario_plan_path).expanduser().resolve()),
                "scenario_plan_sha256": scenario_plan["plan_sha256"],
                "split_counts": scenario_plan["counts"],
                "carla_episode_budget": int(steps) + int(math.ceil(int(steps) / max_steps)),
                "generalization_protocol": {
                    "train_split": "used_for_updates_only",
                    "dev_split": "reserved_for_model_selection",
                    "test_split": "held_out_until_final_evaluation",
                    "canonical_id_leakage_check": "required",
                },
            }
        )
    return plan


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ppo_rollout_steps(requested_steps):
    """Choose an SB3 rollout that divides the requested budget when possible."""
    upper = min(max(int(requested_steps), 2), 16)
    for value in range(upper, 1, -1):
        if int(requested_steps) % value == 0:
            return value
    return 2


def train(
    plan,
    config_path,
    record_path=None,
    *,
    allow_online_carla=False,
    scenario_plan_path=None,
    resume=None,
    chunk_steps=None,
):
    if not allow_online_carla:
        raise RuntimeError("在线 CARLA RL 训练必须显式提供 --allow-online-carla")
    if plan["status"] != "ready":
        raise RuntimeError(f"可选依赖未齐全: {plan['dependency_status']}")
    import gymnasium  # noqa: F401
    from stable_baselines3 import PPO, SAC

    config = load_loop_config(config_path)
    scenario_plan_path = scenario_plan_path or plan.get("scenario_plan_path")
    scenario_plan = load_multiscene_plan(scenario_plan_path) if scenario_plan_path else None
    record = load_record(record_path) if record_path else None
    if scenario_plan is None and record is None:
        raise ValueError("训练必须提供单记录或多场景计划")
    output_root = Path(plan["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    training_seed = int(plan["training_seed"])
    if scenario_plan is not None:
        rows = scenario_plan["splits"]["train"]
        sampler = PlannedScenarioSampler(rows, seed=training_seed)
        initial_record = rows[0]["record"]
        scope = "multiscene"
    else:
        sampler = None
        initial_record = record
        scope = record["sample_id"]
    episode_id = _safe_name(
        f"rl_{scope}_{plan['algorithm'].lower()}_seed_{training_seed}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
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
    env = AdversarialGymEnv(
        record=initial_record if sampler is None else None,
        record_sampler=sampler,
        executor=executor,
        config=agent_config,
    )
    algorithm = plan["algorithm"]
    model_cls = PPO if algorithm == "PPO" else SAC
    model_dir = output_root / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{algorithm.lower()}_seed_{training_seed}"
    manifest_path = output_root / "checkpoint_manifest.json"
    run_manifest_path = output_root / "run_manifest.json"
    checkpoint_every = max(1, int(chunk_steps or plan.get("checkpoint_every") or 1000))
    checkpoints = []
    if resume and not manifest_path.is_file():
        raise RuntimeError("resume 需要同一输出目录下的 checkpoint_manifest.json")
    if resume and manifest_path.is_file():
        try:
            previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if previous_manifest.get("algorithm") != algorithm or int(previous_manifest.get("training_seed", -1)) != training_seed:
                raise RuntimeError("resume checkpoint manifest 与当前算法/种子不一致")
            if scenario_plan and previous_manifest.get("scenario_plan_sha256") != scenario_plan["plan_sha256"]:
                raise RuntimeError("resume checkpoint manifest 与当前多场景计划不一致")
            checkpoints = previous_manifest.get("checkpoints", [])
            resume_path = str(Path(resume).expanduser().resolve())
            if not any(item.get("path") == resume_path for item in checkpoints):
                raise RuntimeError("resume checkpoint 未登记在 checkpoint_manifest.json 中")
        except (OSError, json.JSONDecodeError):
            raise RuntimeError("无法读取 resume checkpoint manifest")
    run_manifest = {
        "format": "carla_online_rl_run_manifest_v1",
        "status": "running",
        "algorithm": algorithm,
        "training_seed": training_seed,
        "requested_steps": int(plan["requested_steps"]),
        "checkpoint_every": checkpoint_every,
        "scenario_plan_path": str(Path(scenario_plan_path).resolve()) if scenario_plan_path else None,
        "scenario_plan_sha256": scenario_plan["plan_sha256"] if scenario_plan else None,
        "split_counts": scenario_plan["counts"] if scenario_plan else None,
        "episode_id": episode_id,
        "carla_version": "0.9.16",
        "carla_server_started_by_script": False,
        "checkpoint_manifest": str(manifest_path),
        "resume_from": str(Path(resume).expanduser().resolve()) if resume else None,
    }
    _write_json(run_manifest_path, run_manifest)
    model = None
    trained_before = 0
    try:
        model_kwargs = {"verbose": 1, "device": "auto", "seed": training_seed}
        if algorithm == "PPO":
            # Keep rollout collection within the explicit CARLA step budget.
            rollout_steps = _ppo_rollout_steps(plan["requested_steps"])
            model_kwargs.update({"n_steps": rollout_steps, "batch_size": rollout_steps})
        if resume:
            resume_path = Path(resume).expanduser().resolve()
            if not resume_path.is_file():
                raise FileNotFoundError(f"找不到 resume checkpoint: {resume_path}")
            model = model_cls.load(str(resume_path), env=env, device="auto")
            trained_before = int(model.num_timesteps)
        else:
            model = model_cls("MlpPolicy", env, **model_kwargs)
        target_steps = int(plan["requested_steps"])
        chunk_index = len(checkpoints)
        while trained_before < target_steps:
            chunk = min(checkpoint_every, target_steps - trained_before)
            if algorithm == "PPO" and chunk > rollout_steps:
                chunk -= chunk % rollout_steps
                if chunk == 0:
                    chunk = rollout_steps
            model.learn(
                total_timesteps=chunk,
                reset_num_timesteps=(trained_before == 0 and chunk_index == 0),
                progress_bar=False,
            )
            trained_before = int(model.num_timesteps)
            checkpoint_path = model_dir / f"{prefix}_steps_{trained_before:06d}.zip"
            model.save(str(checkpoint_path))
            checkpoints.append(
                {
                    "chunk_index": chunk_index,
                    "chunk_steps": int(chunk),
                    "trained_num_timesteps": trained_before,
                    "path": str(checkpoint_path),
                    "exists": checkpoint_path.is_file(),
                }
            )
            _write_json(
                manifest_path,
                {
                    "format": "carla_online_rl_checkpoint_manifest_v1",
                    "algorithm": algorithm,
                    "training_seed": training_seed,
                    "requested_steps": target_steps,
                    "scenario_plan_sha256": scenario_plan["plan_sha256"] if scenario_plan else None,
                    "checkpoints": checkpoints,
                },
            )
            chunk_index += 1
        model_path = output_root / f"{prefix}_final.zip"
        model.save(str(model_path))
        summary = dict(plan)
        summary.update(
            {
                "status": "completed",
                "execution_started": True,
                "model_path": str(model_path),
                "trained_num_timesteps": trained_before,
                "checkpoint_manifest": str(manifest_path),
                "checkpoint_count": len(checkpoints),
                "sampler_snapshot": sampler.snapshot() if sampler else None,
                "evidence_kind": "carla_online_rl_runtime",
            }
        )
        run_manifest.update(summary)
        _write_json(run_manifest_path, run_manifest)
        return summary
    except Exception as exc:
        run_manifest.update(
            {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "trained_num_timesteps": trained_before,
            }
        )
        _write_json(run_manifest_path, run_manifest)
        raise
    finally:
        env.close()


def parse_args():
    parser = argparse.ArgumentParser(description="CARLA 在线 RL 训练入口（显式确认）")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "adversarial_loop_multistep_v1.json"))
    parser.add_argument("--record")
    parser.add_argument("--scenario-plan", help="prepare_carla_rl_multiscene_plan.py 生成的固定计划")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--algorithm", choices=("PPO", "SAC"), default="PPO")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--chunk-steps", type=int, default=1000)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--resume", help="从某个 .zip checkpoint 继续")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-online-carla", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if bool(args.record) == bool(args.scenario_plan):
        raise SystemExit("必须且只能提供 --record 或 --scenario-plan")
    plan = build_training_plan(
        args.config,
        args.record,
        args.output_root,
        algorithm=args.algorithm,
        steps=args.steps,
        scenario_plan_path=args.scenario_plan,
        checkpoint_every=args.chunk_steps,
        seed=args.seed,
    )
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    summary = train(
        plan,
        args.config,
        args.record,
        allow_online_carla=args.allow_online_carla,
        scenario_plan_path=args.scenario_plan,
        resume=args.resume,
        chunk_steps=args.chunk_steps,
    )
    path = Path(args.output_root).expanduser().resolve() / "rl_training_summary.json"
    _write_json(path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
