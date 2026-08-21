"""Benchmark PPO/SAC and non-learning actions on the frozen risk proxy."""

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import (  # noqa: E402
    canonical_parameter_fingerprint,
    load_agent_config,
)
from core.adversarial_gym_env import AdversarialGymEnv  # noqa: E402
from core.adversarial_proxy_executor import (  # noqa: E402
    FrozenRiskProxyExecutor,
    load_proxy_executor_config,
)
from core.adversarial_sampling import ScenarioLibrarySampler  # noqa: E402
from core.scenario_features import normalize_vector, parameter_vector  # noqa: E402
from core.scenario_validator import load_json, validate_schema_value  # noqa: E402
from tools.evaluate_adversarial_baselines import (  # noqa: E402
    build_baseline_strategies,
    evaluate_strategy_candidate,
    load_baseline_config,
)
from tools.train_adversarial_sb3_smoke import (  # noqa: E402
    _algorithm_class,
    _model_kwargs,
)


DEFAULT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_proxy_benchmark_v1.json",
)
DEFAULT_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT,
    "schemas",
    "adversarial_proxy_benchmark_v1.schema.json",
)


def _project_path(path):
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_jsonl(path, values):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for value in values:
            file.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
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


def _default_output_dir(config):
    root = os.environ.get("PROJECT_OUTPUT_ROOT")
    if not root:
        root = r"F:\Carla\output-0.9.16" if os.name == "nt" else "/tmp"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(root, config["output_subdirectory"], timestamp)


def load_benchmark_config(
    path=DEFAULT_CONFIG_PATH,
    schema_path=DEFAULT_SCHEMA_PATH,
):
    config = load_json(os.path.abspath(path))
    schema = load_json(os.path.abspath(schema_path))
    errors = validate_schema_value(config, schema)
    if errors:
        raise ValueError("\n".join(errors))
    if int(config["evaluation"]["sample_count"]) % 12 != 0:
        raise ValueError("evaluation.sample_count 必须是完整 12 分层周期的倍数")
    return config


class ExcludingScenarioSampler:
    """Apply fixed filters while excluding frozen evaluation start records."""

    def __init__(
        self,
        entries_path,
        manifest_path,
        seed,
        filters,
        excluded_library_ids,
        max_skips,
    ):
        self.sampler = ScenarioLibrarySampler(
            entries_path=entries_path,
            manifest_path=manifest_path,
            seed=int(seed),
        )
        self.filters = dict(filters)
        self.excluded_library_ids = set(excluded_library_ids)
        self.max_skips = int(max_skips)
        self.accepted = []
        self.excluded_skip_count = 0

    def __call__(self, seed=None, options=None):
        merged = dict(self.filters)
        merged.update(dict(options or {}))
        next_seed = seed
        for _ in range(self.max_skips):
            record, info = self.sampler(next_seed, merged)
            next_seed = None
            if info["library_id"] not in self.excluded_library_ids:
                self.accepted.append(info)
                return record, info
            self.excluded_skip_count += 1
        raise RuntimeError("训练采样连续命中冻结评估场景，超过跳过上限")

    def snapshot(self):
        return {
            "accepted_count": len(self.accepted),
            "unique_library_entry_count": len(
                {item["library_id"] for item in self.accepted}
            ),
            "excluded_skip_count": self.excluded_skip_count,
            "excluded_library_entry_count": len(self.excluded_library_ids),
            "excluded_entry_seen": any(
                item["library_id"] in self.excluded_library_ids
                for item in self.accepted
            ),
            "coverage": self.sampler.coverage_snapshot(),
        }


def sample_evaluation_records(baseline_config, sample_count, sample_seed):
    sampler = ScenarioLibrarySampler(
        entries_path=_project_path(baseline_config["scenario_library_path"]),
        manifest_path=_project_path(
            baseline_config["scenario_library_manifest_path"]
        ),
        seed=int(sample_seed),
    )
    rows = []
    for index in range(int(sample_count)):
        record, sampling = sampler(
            int(sample_seed) if index == 0 else None,
            baseline_config["filters"],
        )
        rows.append({"record": record, "sampling": sampling})
    return rows


def _normalized_shift(baseline, candidate):
    baseline_values = normalize_vector(parameter_vector(baseline), clip=True)
    candidate_values = normalize_vector(parameter_vector(candidate), clip=True)
    return math.sqrt(
        float(np.mean(np.square(candidate_values - baseline_values)))
    )


def _common_result_fields(sample, replicate_seed, strategy):
    sampling = sample["sampling"]
    return {
        "strategy": strategy,
        "replicate_seed": int(replicate_seed),
        "sample_index": int(sampling["selection_index"]),
        "library_id": sampling["library_id"],
        "baseline_sample_id": sample["record"]["sample_id"],
        "generator": sampling["generator"],
        "target_risk_level": sampling["target_risk_level"],
        "weather_tags": list(sampling["weather_tags"]),
        "hazard_tags": list(sampling["hazard_tags"]),
        "traffic_manager_seed": int(sampling["traffic_manager_seed"]),
    }


def evaluate_learned_policy(
    name,
    seed,
    model_path,
    samples,
    agent_config,
    executor_config,
    model_override,
    device,
    deterministic,
):
    algorithm = _algorithm_class(name)
    model = algorithm.load(model_path, device=device)
    executor = FrozenRiskProxyExecutor(
        config=executor_config,
        model_path=model_override,
    )
    env = AdversarialGymEnv(
        record=samples[0]["record"],
        executor=executor,
        config=agent_config,
    )
    rows = []
    strategy = f"{name}_policy"
    try:
        for sample in samples:
            observation, _ = env.reset(
                seed=int(seed) + int(sample["sampling"]["selection_index"]),
                options={"record": sample["record"]},
            )
            baseline_score = float(
                env.core.baseline_result.observed_risk_score
            )
            action, _ = model.predict(
                observation,
                deterministic=bool(deterministic),
            )
            _, reward, terminated, truncated, info = env.step(action)
            transition = env.core.last_transition
            candidate = transition.get("candidate")
            candidate_score = None
            if info["proposal_valid"] and candidate is not None:
                candidate_score = float(
                    env.core.agent.last_result.observed_risk_score
                )
            row = _common_result_fields(sample, seed, strategy)
            row.update(
                {
                    "algorithm": name,
                    "action": np.asarray(action, dtype=np.float32).tolist(),
                    "mean_absolute_action": float(
                        np.mean(np.abs(np.asarray(action, dtype=np.float64)))
                    ),
                    "action_attempt_count": 1,
                    "proposal_valid": bool(info["proposal_valid"]),
                    "candidate_proxy_evaluated": candidate_score is not None,
                    "baseline_proxy_score": baseline_score,
                    "candidate_proxy_score": candidate_score,
                    "proxy_score_delta": (
                        candidate_score - baseline_score
                        if candidate_score is not None
                        else None
                    ),
                    "reward": float(reward),
                    "reward_breakdown": info["reward_breakdown"],
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "termination_reason": info["termination_reason"],
                    "candidate_fingerprint": (
                        transition["info"].get("fingerprint")
                        if transition is not None
                        else None
                    ),
                    "unchanged_from_baseline": (
                        canonical_parameter_fingerprint(candidate)
                        == canonical_parameter_fingerprint(sample["record"])
                        if candidate is not None
                        else False
                    ),
                    "normalized_parameter_shift": (
                        _normalized_shift(sample["record"], candidate)
                        if candidate is not None
                        else None
                    ),
                    "candidate": candidate,
                    "evidence_kind": "frozen_risk_proxy_inference",
                    "carla_connected": False,
                }
            )
            rows.append(row)
    finally:
        env.close()
    return rows


def evaluate_non_learning_strategies(
    seed,
    samples,
    baseline_config,
    agent_config,
    executor_config,
    model_override,
):
    strategies = build_baseline_strategies(
        baseline_config,
        lhs_batch_size=len(samples),
        seed=int(seed),
    )
    retry_strategies = build_baseline_strategies(
        baseline_config,
        lhs_batch_size=len(samples),
        seed=int(seed) + int(baseline_config["retry_seed_offset"]),
    )
    executor = FrozenRiskProxyExecutor(
        config=executor_config,
        model_path=model_override,
    )
    rows = []
    for name, strategy in strategies.items():
        for index, sample in enumerate(samples):
            proposal = evaluate_strategy_candidate(
                name=name,
                strategy=strategy,
                retry_strategy=retry_strategies[name],
                sample=sample,
                sample_index=index,
                agent_config=agent_config,
                max_attempts=int(
                    baseline_config["max_candidate_attempts"][name]
                ),
            )
            baseline_score, _ = executor.predict_score(sample["record"])
            candidate = proposal["candidate"]
            candidate_score = None
            if proposal["valid"] and candidate is not None:
                candidate_score, _ = executor.predict_score(candidate)
            delta = (
                candidate_score - baseline_score
                if candidate_score is not None
                else None
            )
            duplicate_penalty = (
                float(agent_config["reward"]["duplicate_penalty"])
                if proposal["unchanged_from_baseline"]
                else 0.0
            )
            row = _common_result_fields(sample, seed, name)
            row.update(
                {
                    "algorithm": None,
                    "action": proposal["action"],
                    "mean_absolute_action": proposal["mean_absolute_action"],
                    "action_attempt_count": proposal["attempt_count"],
                    "proposal_valid": bool(proposal["valid"]),
                    "candidate_proxy_evaluated": candidate_score is not None,
                    "baseline_proxy_score": float(baseline_score),
                    "candidate_proxy_score": candidate_score,
                    "proxy_score_delta": delta,
                    "reward": (
                        round(
                            delta
                            / 100.0
                            * float(
                                agent_config["reward"]["risk_delta_weight"]
                            )
                            + duplicate_penalty,
                            6,
                        )
                        if delta is not None
                        else float(
                            agent_config["reward"][
                                "invalid_candidate_penalty"
                            ]
                        )
                    ),
                    "reward_breakdown": {
                        "risk_delta": (
                            round(
                                delta
                                / 100.0
                                * float(
                                    agent_config["reward"][
                                        "risk_delta_weight"
                                    ]
                                ),
                                6,
                            )
                            if delta is not None
                            else 0.0
                        ),
                        "collision_event": 0.0,
                        "event": 0.0,
                        "invalid_candidate": (
                            0.0
                            if proposal["valid"]
                            else float(
                                agent_config["reward"][
                                    "invalid_candidate_penalty"
                                ]
                            )
                        ),
                        "duplicate": duplicate_penalty,
                        "run_failure": 0.0,
                    },
                    "terminated": not bool(proposal["valid"]),
                    "truncated": False,
                    "termination_reason": (
                        None if proposal["valid"] else "invalid_candidate"
                    ),
                    "candidate_fingerprint": proposal[
                        "candidate_fingerprint"
                    ],
                    "unchanged_from_baseline": proposal[
                        "unchanged_from_baseline"
                    ],
                    "normalized_parameter_shift": proposal[
                        "normalized_parameter_shift"
                    ],
                    "candidate": candidate,
                    "evidence_kind": "frozen_risk_proxy_inference",
                    "carla_connected": False,
                }
            )
            rows.append(row)
    return rows


def summarize_strategy_rows(rows):
    evaluated = [row for row in rows if row["candidate_proxy_evaluated"]]
    deltas = [float(row["proxy_score_delta"]) for row in evaluated]
    scores = [float(row["candidate_proxy_score"]) for row in evaluated]
    rewards = [float(row["reward"]) for row in rows]
    fingerprints = [
        row["candidate_fingerprint"]
        for row in evaluated
        if row["candidate_fingerprint"] is not None
    ]
    return {
        "strategy": rows[0]["strategy"] if rows else None,
        "replicate_seed": rows[0]["replicate_seed"] if rows else None,
        "planned_candidate_budget": len(rows),
        "candidate_proxy_evaluation_count": len(evaluated),
        "valid_candidate_rate": len(evaluated) / len(rows) if rows else 0.0,
        "total_action_attempt_count": sum(
            int(row["action_attempt_count"]) for row in rows
        ),
        "retried_sample_count": sum(
            int(row["action_attempt_count"]) > 1 for row in rows
        ),
        "unique_candidate_count": len(set(fingerprints)),
        "mean_candidate_proxy_score": (
            statistics.fmean(scores) if scores else None
        ),
        "mean_proxy_score_delta": (
            statistics.fmean(deltas) if deltas else None
        ),
        "median_proxy_score_delta": (
            statistics.median(deltas) if deltas else None
        ),
        "maximum_proxy_score_delta": max(deltas) if deltas else None,
        "positive_delta_count": sum(value > 0.0 for value in deltas),
        "positive_delta_rate": (
            sum(value > 0.0 for value in deltas) / len(deltas)
            if deltas
            else 0.0
        ),
        "mean_reward": statistics.fmean(rewards) if rewards else None,
        "mean_absolute_action": (
            statistics.fmean(
                float(row["mean_absolute_action"]) for row in evaluated
            )
            if evaluated
            else None
        ),
        "mean_normalized_parameter_shift": (
            statistics.fmean(
                float(row["normalized_parameter_shift"])
                for row in evaluated
                if row["normalized_parameter_shift"] is not None
            )
            if evaluated
            else None
        ),
    }


def aggregate_strategy_summaries(summaries):
    grouped = defaultdict(list)
    for summary in summaries:
        grouped[summary["strategy"]].append(summary)
    result = {}
    metrics = (
        "valid_candidate_rate",
        "mean_candidate_proxy_score",
        "mean_proxy_score_delta",
        "median_proxy_score_delta",
        "positive_delta_rate",
        "mean_reward",
        "mean_absolute_action",
        "mean_normalized_parameter_shift",
    )
    for strategy, values in sorted(grouped.items()):
        aggregate = {
            "replicate_count": len(values),
            "replicate_seeds": [item["replicate_seed"] for item in values],
            "planned_candidate_budget_total": sum(
                item["planned_candidate_budget"] for item in values
            ),
            "candidate_proxy_evaluation_count_total": sum(
                item["candidate_proxy_evaluation_count"] for item in values
            ),
        }
        for metric in metrics:
            metric_values = [
                float(item[metric])
                for item in values
                if item[metric] is not None
            ]
            aggregate[metric] = {
                "mean": statistics.fmean(metric_values)
                if metric_values
                else None,
                "sample_std": statistics.stdev(metric_values)
                if len(metric_values) > 1
                else 0.0 if metric_values else None,
                "minimum": min(metric_values) if metric_values else None,
                "maximum": max(metric_values) if metric_values else None,
            }
        result[strategy] = aggregate
    return result


def pairwise_policy_comparisons(rows):
    index = {
        (row["strategy"], row["replicate_seed"], row["library_id"]): row
        for row in rows
        if row["candidate_proxy_evaluated"]
    }
    seeds = sorted({row["replicate_seed"] for row in rows})
    comparisons = {}
    for policy in ("ppo_policy", "sac_policy"):
        for baseline in ("fixed", "random", "lhs", "rule_guided_lhs"):
            differences = []
            for seed in seeds:
                library_ids = {
                    key[2]
                    for key in index
                    if key[0] == policy and key[1] == seed
                }
                for library_id in library_ids:
                    policy_row = index.get((policy, seed, library_id))
                    baseline_row = index.get((baseline, seed, library_id))
                    if policy_row is None or baseline_row is None:
                        continue
                    differences.append(
                        float(policy_row["candidate_proxy_score"])
                        - float(baseline_row["candidate_proxy_score"])
                    )
            comparisons[f"{policy}_vs_{baseline}"] = {
                "pair_count": len(differences),
                "policy_win_count": sum(value > 0.0 for value in differences),
                "tie_count": sum(value == 0.0 for value in differences),
                "policy_loss_count": sum(value < 0.0 for value in differences),
                "mean_candidate_score_difference": (
                    statistics.fmean(differences) if differences else None
                ),
                "median_candidate_score_difference": (
                    statistics.median(differences) if differences else None
                ),
            }
    return comparisons


def train_policy(
    name,
    seed,
    total_timesteps,
    device,
    output_dir,
    baseline_config,
    agent_config,
    executor_config,
    model_override,
    excluded_library_ids,
    max_excluded_skips,
):
    sampler = ExcludingScenarioSampler(
        entries_path=_project_path(baseline_config["scenario_library_path"]),
        manifest_path=_project_path(
            baseline_config["scenario_library_manifest_path"]
        ),
        seed=int(seed),
        filters=baseline_config["filters"],
        excluded_library_ids=excluded_library_ids,
        max_skips=max_excluded_skips,
    )
    executor = FrozenRiskProxyExecutor(
        config=executor_config,
        model_path=model_override,
    )
    env = AdversarialGymEnv(
        record_sampler=sampler,
        executor=executor,
        config=agent_config,
    )
    algorithm = _algorithm_class(name)
    model = algorithm(
        **_model_kwargs(name, env, seed, total_timesteps, device)
    )
    model_path = os.path.join(
        output_dir,
        "models",
        f"{name}_seed_{int(seed)}.zip",
    )
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    try:
        model.learn(total_timesteps=int(total_timesteps), progress_bar=False)
        model.save(model_path)
        trained_num_timesteps = int(model.num_timesteps)
        executor_call_count = len(executor.calls)
        sampler_snapshot = sampler.snapshot()
    finally:
        env.close()
    if sampler_snapshot["excluded_entry_seen"]:
        raise RuntimeError("训练起始场景泄漏到冻结评估集合")
    return {
        "algorithm": name,
        "seed": int(seed),
        "requested_total_timesteps": int(total_timesteps),
        "trained_num_timesteps": trained_num_timesteps,
        "training_executor_call_count": executor_call_count,
        "model_path": os.path.abspath(model_path),
        "model_exists": os.path.isfile(model_path),
        "training_sampler": sampler_snapshot,
    }


def run_benchmark(config, output_dir, model_override=None):
    import gymnasium
    import stable_baselines3
    import torch

    baseline_config = load_baseline_config(
        _project_path(config["baseline_config_path"])
    )
    agent_config = load_agent_config(_project_path(config["agent_config_path"]))
    executor_config = load_proxy_executor_config(
        _project_path(config["executor_config_path"])
    )
    if float(agent_config["reward"]["collision_event_reward"]) != 0.0:
        raise ValueError("代理基准不能启用未建模的 collision 奖励")
    if float(agent_config["reward"]["event_reward"]) != 0.0:
        raise ValueError("代理基准不能启用未建模的 event 奖励")

    evaluation = config["evaluation"]
    samples = sample_evaluation_records(
        baseline_config,
        sample_count=evaluation["sample_count"],
        sample_seed=evaluation["sample_seed"],
    )
    excluded_library_ids = {
        sample["sampling"]["library_id"] for sample in samples
    }
    if len(excluded_library_ids) != len(samples):
        raise RuntimeError("冻结评估集合包含重复场景库条目")

    metadata_executor = FrozenRiskProxyExecutor(
        config=executor_config,
        model_path=model_override,
    )
    os.makedirs(output_dir, exist_ok=False)
    sample_path = os.path.join(output_dir, "evaluation_samples.jsonl")
    rows_path = os.path.join(output_dir, "candidate_results.jsonl")
    summary_path = os.path.join(output_dir, "benchmark_summary.json")
    _write_jsonl(sample_path, samples)

    summary = {
        "format": "adversarial_proxy_benchmark_report_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "evidence_kind": "frozen_proxy_policy_benchmark",
        "policy_effect_scope": "proxy_environment_only",
        "carla_connected": False,
        "supports_carla_policy_effect_claim": False,
        "source_git": _git_state(),
        "versions": {
            "python": sys.version.split()[0],
            "gymnasium": gymnasium.__version__,
            "stable_baselines3": stable_baselines3.__version__,
            "torch": torch.__version__,
        },
        "executor": metadata_executor.metadata(),
        "reward_channel_policy": {
            "available": ["risk"],
            "collision_event_reward": 0.0,
            "event_reward": 0.0,
        },
        "fairness_boundary": {
            "equal_scope": "evaluation_inference_candidate_budget_only",
            "planned_candidates_per_strategy_per_seed": len(samples),
            "rl_training_budget_is_additional": True,
            "baseline_retry_attempts_are_reported": True,
        },
        "split_boundary": {
            "policy_start_records_excluded_from_training": True,
            "evaluation_library_entry_count": len(excluded_library_ids),
            "proxy_model_was_trained_on_scenario_library": True,
            "external_generalization_claim_supported": False,
        },
        "evaluation": {
            "sample_count": len(samples),
            "sample_seed": int(evaluation["sample_seed"]),
            "generator_target_stratum_count": len(
                {
                    (
                        sample["sampling"]["generator"],
                        sample["sampling"]["target_risk_level"],
                    )
                    for sample in samples
                }
            ),
            "unique_library_entry_count": len(excluded_library_ids),
        },
        "training_runs": [],
        "strategy_runs": [],
        "strategy_aggregate": {},
        "pairwise_comparisons": {},
        "artifacts": {
            "evaluation_samples": os.path.basename(sample_path),
            "candidate_results": os.path.basename(rows_path),
            "models": "models/",
        },
    }
    _write_json(summary_path, summary)

    all_rows = []
    training = config["training"]
    seeds = [int(seed) for seed in training["seeds"]]
    for seed in seeds:
        baseline_rows = evaluate_non_learning_strategies(
            seed=seed,
            samples=samples,
            baseline_config=baseline_config,
            agent_config=agent_config,
            executor_config=executor_config,
            model_override=model_override,
        )
        all_rows.extend(baseline_rows)
        for strategy in ("fixed", "random", "lhs", "rule_guided_lhs"):
            selected = [
                row for row in baseline_rows if row["strategy"] == strategy
            ]
            summary["strategy_runs"].append(
                summarize_strategy_rows(selected)
            )
        _write_jsonl(rows_path, all_rows)
        _write_json(summary_path, summary)

    for name in training["algorithms"]:
        for seed in seeds:
            training_run = train_policy(
                name=name,
                seed=seed,
                total_timesteps=int(training["total_timesteps"]),
                device=training["device"],
                output_dir=output_dir,
                baseline_config=baseline_config,
                agent_config=agent_config,
                executor_config=executor_config,
                model_override=model_override,
                excluded_library_ids=excluded_library_ids,
                max_excluded_skips=int(training["max_excluded_skips"]),
            )
            summary["training_runs"].append(training_run)
            policy_rows = evaluate_learned_policy(
                name=name,
                seed=seed,
                model_path=training_run["model_path"],
                samples=samples,
                agent_config=agent_config,
                executor_config=executor_config,
                model_override=model_override,
                device=training["device"],
                deterministic=evaluation["deterministic_policy"],
            )
            all_rows.extend(policy_rows)
            summary["strategy_runs"].append(
                summarize_strategy_rows(policy_rows)
            )
            _write_jsonl(rows_path, all_rows)
            _write_json(summary_path, summary)

    summary["strategy_aggregate"] = aggregate_strategy_summaries(
        summary["strategy_runs"]
    )
    summary["pairwise_comparisons"] = pairwise_policy_comparisons(all_rows)
    _write_json(summary_path, summary)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="多随机种子比较 PPO/SAC 与四类非学习冻结代理基线"
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir")
    parser.add_argument("--model-path")
    parser.add_argument("--total-timesteps", type=int)
    parser.add_argument("--device")
    parser.add_argument("--seeds", nargs="+", type=int)
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_benchmark_config(args.config)
    if args.total_timesteps is not None:
        if args.total_timesteps < 64:
            raise ValueError("--total-timesteps 必须至少为 64")
        config["training"]["total_timesteps"] = int(args.total_timesteps)
    if args.device is not None:
        config["training"]["device"] = str(args.device)
    if args.seeds is not None:
        if len(set(args.seeds)) < 2:
            raise ValueError("--seeds 至少需要两个不同随机种子")
        config["training"]["seeds"] = list(dict.fromkeys(args.seeds))

    output_dir = os.path.abspath(args.output_dir or _default_output_dir(config))
    summary = run_benchmark(
        config=config,
        output_dir=output_dir,
        model_override=args.model_path,
    )
    print(
        f"[BENCHMARK] samples={summary['evaluation']['sample_count']} "
        f"seeds={len(config['training']['seeds'])}"
    )
    for strategy, metrics in summary["strategy_aggregate"].items():
        delta = metrics["median_proxy_score_delta"]["mean"]
        positive = metrics["positive_delta_rate"]["mean"]
        print(
            f"[BENCHMARK] {strategy}: "
            f"median_delta_mean={delta:.6f}, positive_rate_mean={positive:.6f}"
        )
    print(f"[RESULT_DIR] {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
