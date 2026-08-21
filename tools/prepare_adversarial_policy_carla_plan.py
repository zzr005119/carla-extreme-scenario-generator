"""Prepare an independent CARLA plan for frozen SAC and rule-guided LHS."""

import argparse
import copy
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import (  # noqa: E402
    AdversarialTestAgentV1,
    EpisodeResult,
    canonical_parameter_fingerprint,
    load_agent_config,
)
from core.adversarial_loop import RuleGuidedLhsActionStrategy  # noqa: E402
from core.adversarial_proxy_executor import (  # noqa: E402
    FrozenRiskProxyExecutor,
    file_sha256,
    load_proxy_executor_config,
)
from core.adversarial_sampling import ScenarioLibrarySampler  # noqa: E402
from core.scenario_validator import (  # noqa: E402
    load_json,
    require_valid_scenario,
    validate_schema_value,
)
from tools.evaluate_adversarial_baselines import (  # noqa: E402
    evaluate_strategy_candidate,
    git_state,
    load_baseline_config,
)
from tools.prepare_adversarial_baseline_carla_plan import (  # noqa: E402
    _portable,
    _write_run_artifacts,
)
from tools.run_adversarial_episode import load_loop_config  # noqa: E402


DEFAULT_CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_policy_carla_plan_v1.json",
)
DEFAULT_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT,
    "schemas",
    "adversarial_policy_carla_plan_v1.schema.json",
)
STRATEGY_SUFFIXES = {
    "sac_policy": "sac",
    "rule_guided_lhs": "rulelhs",
}


def _project_path(path):
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def _rooted_path(spec):
    root = os.environ.get(spec["root_env"])
    if not root:
        raise ValueError(f"缺少路径根目录环境变量: {spec['root_env']}")
    return os.path.abspath(os.path.join(root, spec["relative_path"]))


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


def _write_csv(path, rows):
    fields = (
        "run_order",
        "pair_id",
        "phase",
        "strategy",
        "run_id",
        "sample_id",
        "library_id",
        "generator",
        "target_risk_level",
        "traffic_manager_seed",
        "proxy_baseline_score",
        "proxy_candidate_score",
        "proxy_score_delta",
        "attempt_count",
        "record_path",
        "config_path",
        "expected_run_root",
        "validation_status",
    )
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fields} for row in rows)


def load_policy_plan_config(
    path=DEFAULT_CONFIG_PATH,
    schema_path=DEFAULT_SCHEMA_PATH,
):
    config = load_json(os.path.abspath(path))
    schema = load_json(os.path.abspath(schema_path))
    errors = validate_schema_value(config, schema)
    if errors:
        raise ValueError("\n".join(errors))
    if tuple(config["strategy_order"]) != tuple(STRATEGY_SUFFIXES):
        raise ValueError("strategy_order 必须为 sac_policy、rule_guided_lhs")
    return config


def load_excluded_library_ids(path, expected_count):
    ids = []
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            library_id = (row.get("sampling") or {}).get("library_id")
            if not library_id:
                raise ValueError(f"{path}:{line_number}: 缺少 sampling.library_id")
            ids.append(str(library_id))
    unique_ids = set(ids)
    if len(ids) != int(expected_count) or len(unique_ids) != int(expected_count):
        raise ValueError(
            "被排除的代理评估集合数量不符或包含重复条目: "
            f"rows={len(ids)}, unique={len(unique_ids)}"
        )
    return unique_ids


def select_independent_samples(
    baseline_config,
    sample_count,
    sample_seed,
    excluded_library_ids,
    max_attempts,
):
    sampler = ScenarioLibrarySampler(
        entries_path=_project_path(baseline_config["scenario_library_path"]),
        manifest_path=_project_path(
            baseline_config["scenario_library_manifest_path"]
        ),
        seed=int(sample_seed),
    )
    selected = {}
    selected_ids = set()
    skipped_excluded = 0
    skipped_filled_stratum = 0
    attempts = 0
    for index in range(int(max_attempts)):
        record, sampling = sampler(
            int(sample_seed) if index == 0 else None,
            baseline_config["filters"],
        )
        attempts += 1
        library_id = sampling["library_id"]
        stratum = (
            sampling["generator"],
            sampling["target_risk_level"],
        )
        if library_id in excluded_library_ids:
            skipped_excluded += 1
            continue
        if stratum in selected or library_id in selected_ids:
            skipped_filled_stratum += 1
            continue
        selected[stratum] = {"record": record, "sampling": sampling}
        selected_ids.add(library_id)
        if len(selected) == int(sample_count):
            break
    if len(selected) != int(sample_count):
        raise RuntimeError(
            "无法构造完整独立分层集合: "
            f"selected={len(selected)}, attempts={attempts}"
        )
    rows = list(selected.values())
    overlap = selected_ids.intersection(excluded_library_ids)
    if overlap:
        raise RuntimeError(f"独立集合与代理评估集合重叠: {sorted(overlap)}")
    return rows, {
        "attempt_count": attempts,
        "skipped_excluded_count": skipped_excluded,
        "skipped_filled_stratum_count": skipped_filled_stratum,
        "selected_library_entry_count": len(selected_ids),
        "selected_stratum_count": len(selected),
        "excluded_overlap_count": 0,
    }


def _default_plan_root(config):
    root = os.environ.get("PROJECT_OUTPUT_ROOT")
    if not root:
        root = r"F:\Carla\output-0.9.16" if os.name == "nt" else "/tmp"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(root, config["output_subdirectory"], timestamp)


def _default_runtime_root(config, plan_root):
    root = os.environ.get("PROJECT_OUTPUT_ROOT")
    if not root:
        root = r"F:\Carla\output-0.9.16" if os.name == "nt" else plan_root
    return os.path.join(
        root,
        config["runtime_output_subdirectory"],
        os.path.basename(plan_root),
    )


def _candidate_sample_id(record, pair_index, strategy):
    suffix = f"_apcv1_{pair_index:02d}_{STRATEGY_SUFFIXES[strategy]}"
    base = str(record["sample_id"]).split("_adv_", 1)[0]
    return f"{base[:64 - len(suffix)]}{suffix}"


def _load_sac_policy(config):
    model_spec = config["policy_model"]
    model_path = _rooted_path(model_spec)
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"冻结 SAC 模型不存在: {model_path}")
    actual_hash = file_sha256(model_path)
    if actual_hash != model_spec["sha256"]:
        raise ValueError(
            "冻结 SAC 模型 SHA-256 不一致: "
            f"expected={model_spec['sha256']}, actual={actual_hash}"
        )
    from stable_baselines3 import SAC

    model = SAC.load(model_path, device=model_spec["device"])
    return model, model_path, actual_hash


def prepare_plan(
    plan_config,
    plan_root,
    runtime_output_root,
    traffic_manager_port=None,
    validate_runner=None,
):
    baseline_config = load_baseline_config(
        _project_path(plan_config["baseline_config_path"])
    )
    loop_config = load_loop_config(_project_path(plan_config["loop_config_path"]))
    proxy_config = load_proxy_executor_config(
        _project_path(plan_config["proxy_executor_config_path"])
    )
    proxy_agent_config = load_agent_config(
        _project_path(plan_config["proxy_agent_config_path"])
    )
    runtime_agent_config = load_agent_config(
        _project_path(loop_config["agent_config_path"])
    )
    excluded_path = _rooted_path(plan_config["excluded_proxy_evaluation"])
    excluded_ids = load_excluded_library_ids(
        excluded_path,
        plan_config["excluded_proxy_evaluation"][
            "expected_library_entry_count"
        ],
    )
    sample_rows, selection_audit = select_independent_samples(
        baseline_config=baseline_config,
        sample_count=plan_config["sample_count"],
        sample_seed=plan_config["sample_seed"],
        excluded_library_ids=excluded_ids,
        max_attempts=plan_config["max_selection_attempts"],
    )
    model, model_path, model_hash = _load_sac_policy(plan_config)
    proxy_executor = FrozenRiskProxyExecutor(config=proxy_config)
    rule_strategy = RuleGuidedLhsActionStrategy(
        seed=int(plan_config["rule_guided_lhs_seed"]),
        batch_size=len(sample_rows),
        minimum_magnitude=float(
            baseline_config["rule_lhs_minimum_magnitude"]
        ),
    )
    rule_retry_strategy = RuleGuidedLhsActionStrategy(
        seed=(
            int(plan_config["rule_guided_lhs_seed"])
            + int(baseline_config["retry_seed_offset"])
        ),
        batch_size=len(sample_rows),
        minimum_magnitude=float(
            baseline_config["rule_lhs_minimum_magnitude"]
        ),
    )
    base_config = load_json(_project_path(loop_config["base_carla_config_path"]))
    route_profile = load_json(_project_path(loop_config["route_profile_path"]))
    traffic_manager_port = int(
        traffic_manager_port or loop_config["runtime"]["traffic_manager_port"]
    )
    if validate_runner is None:
        validate_runner = bool(plan_config["validate_scene_configs"])
    os.makedirs(plan_root, exist_ok=False)

    runs = []
    candidate_fingerprints = set()
    for pair_index, sample in enumerate(sample_rows, 1):
        record = copy.deepcopy(sample["record"])
        sampling = sample["sampling"]
        pair_id = f"apcv1_pair_{pair_index:02d}"
        baseline_run_id = f"{pair_id}_baseline"
        baseline_artifacts = _write_run_artifacts(
            plan_root,
            runtime_output_root,
            record,
            baseline_run_id,
            base_config,
            route_profile,
            traffic_manager_port,
            validate_runner,
        )
        baseline_payload = proxy_executor(record, "baseline", -1)
        baseline_result = EpisodeResult.from_mapping(baseline_payload)
        baseline_score = float(baseline_result.observed_risk_score)
        runs.append(
            {
                "run_order": len(runs) + 1,
                "pair_id": pair_id,
                "phase": "baseline",
                "strategy": None,
                "run_id": baseline_run_id,
                "sample_id": record["sample_id"],
                "library_id": sampling["library_id"],
                "generator": sampling["generator"],
                "target_risk_level": sampling["target_risk_level"],
                "traffic_manager_seed": sampling["traffic_manager_seed"],
                "proxy_baseline_score": baseline_score,
                "proxy_candidate_score": None,
                "proxy_score_delta": None,
                "attempt_count": 0,
                **baseline_artifacts,
            }
        )

        policy_agent = AdversarialTestAgentV1(proxy_agent_config)
        observation = policy_agent.reset(record, baseline_result)
        action, _ = model.predict(
            np.asarray(observation["vector"], dtype=np.float32),
            deterministic=bool(plan_config["policy_model"]["deterministic"]),
        )
        policy_proposal = policy_agent.propose(
            np.asarray(action, dtype=np.float32).tolist()
        )
        if not policy_proposal["valid"]:
            raise ValueError(
                f"{pair_id}/sac_policy: {policy_proposal['error']}"
            )
        policy_candidate = copy.deepcopy(policy_proposal["candidate"])
        policy_score, _ = proxy_executor.predict_score(policy_candidate)
        policy_row = {
            "action": policy_proposal["action"],
            "attempts": [
                {
                    "attempt_index": 0,
                    "action": policy_proposal["action"],
                    "valid": True,
                    "clipped": policy_proposal.get("clipped", False),
                    "fingerprint": policy_proposal["fingerprint"],
                    "error": None,
                }
            ],
            "attempt_count": 1,
            "invalid_attempt_count": 0,
            "first_attempt_valid": True,
            "candidate_fingerprint": policy_proposal["fingerprint"],
            "candidate": policy_candidate,
            "proxy_candidate_score": float(policy_score),
        }

        rule_row = evaluate_strategy_candidate(
            "rule_guided_lhs",
            rule_strategy,
            rule_retry_strategy,
            sample,
            pair_index - 1,
            runtime_agent_config,
            int(
                baseline_config["max_candidate_attempts"]["rule_guided_lhs"]
            ),
        )
        if not rule_row["valid"]:
            raise ValueError(
                f"{pair_id}/rule_guided_lhs: retry budget exhausted"
            )
        rule_row["proxy_candidate_score"], _ = proxy_executor.predict_score(
            rule_row["candidate"]
        )

        pair_fingerprints = set()
        for strategy, row in (
            ("sac_policy", policy_row),
            ("rule_guided_lhs", rule_row),
        ):
            candidate = copy.deepcopy(row["candidate"])
            fingerprint = row["candidate_fingerprint"]
            if fingerprint == canonical_parameter_fingerprint(record):
                raise ValueError(f"{pair_id}/{strategy}: 候选与基线重复")
            if fingerprint in pair_fingerprints:
                raise ValueError(f"{pair_id}: 两个策略生成了重复候选")
            if fingerprint in candidate_fingerprints:
                raise ValueError(f"{pair_id}/{strategy}: 跨 pair 候选重复")
            pair_fingerprints.add(fingerprint)
            candidate_fingerprints.add(fingerprint)
            candidate["sample_id"] = _candidate_sample_id(
                record,
                pair_index,
                strategy,
            )
            require_valid_scenario(candidate)
            run_id = f"{pair_id}_{STRATEGY_SUFFIXES[strategy]}"
            artifacts = _write_run_artifacts(
                plan_root,
                runtime_output_root,
                candidate,
                run_id,
                base_config,
                route_profile,
                traffic_manager_port,
                validate_runner,
            )
            candidate_score = float(row["proxy_candidate_score"])
            runs.append(
                {
                    "run_order": len(runs) + 1,
                    "pair_id": pair_id,
                    "phase": "candidate",
                    "strategy": strategy,
                    "run_id": run_id,
                    "sample_id": candidate["sample_id"],
                    "library_id": sampling["library_id"],
                    "generator": sampling["generator"],
                    "target_risk_level": sampling["target_risk_level"],
                    "traffic_manager_seed": sampling["traffic_manager_seed"],
                    "proxy_baseline_score": baseline_score,
                    "proxy_candidate_score": candidate_score,
                    "proxy_score_delta": round(
                        candidate_score - baseline_score,
                        6,
                    ),
                    "first_attempt_valid": row["first_attempt_valid"],
                    "attempt_count": row["attempt_count"],
                    "invalid_attempt_count": row["invalid_attempt_count"],
                    "selected_action": row["action"],
                    "attempts": row["attempts"],
                    "candidate_fingerprint": fingerprint,
                    "policy_model_sha256": (
                        model_hash if strategy == "sac_policy" else None
                    ),
                    "policy_seed": (
                        int(plan_config["policy_model"]["seed"])
                        if strategy == "sac_policy"
                        else None
                    ),
                    **artifacts,
                }
            )

    strata = {
        (row["sampling"]["generator"], row["sampling"]["target_risk_level"])
        for row in sample_rows
    }
    strategy_counts = Counter(
        run["strategy"] for run in runs if run["phase"] == "candidate"
    )
    summary = {
        "format": "adversarial_policy_carla_plan_summary_v1",
        "evidence_kind": "static_validation",
        "prepared_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_git": git_state(),
        "sample_count": len(sample_rows),
        "generator_target_stratum_count": len(strata),
        "baseline_run_count": sum(run["phase"] == "baseline" for run in runs),
        "candidate_run_count": sum(run["phase"] == "candidate" for run in runs),
        "total_run_count": len(runs),
        "strategy_order": list(plan_config["strategy_order"]),
        "strategy_candidate_counts": dict(sorted(strategy_counts.items())),
        "unique_candidate_fingerprint_count": len(candidate_fingerprints),
        "scene_config_validation_count": sum(
            run["validation_status"] == "completed" for run in runs
        ),
        "policy_model": {
            **plan_config["policy_model"],
            "resolved_path": model_path,
            "verified_sha256": model_hash,
        },
        "proxy_executor": proxy_executor.metadata(),
        "excluded_proxy_evaluation": {
            "resolved_path": excluded_path,
            "sha256": file_sha256(excluded_path),
            "library_entry_count": len(excluded_ids),
        },
        "selection_audit": selection_audit,
        "carla_runtime_executed": False,
        "runtime_boundary": (
            "The independent records, frozen-policy candidates, rule-guided "
            "candidates, and CARLA configs passed static validation. No CARLA "
            "scene was executed by this planning command."
        ),
        "runtime_output_root": os.path.abspath(runtime_output_root),
        "traffic_manager_port": traffic_manager_port,
        "artifacts": {
            "run_plan_json": "run_plan.json",
            "run_plan_csv": "run_plan.csv",
            "sample_manifest": "sample_manifest.jsonl",
            "selection_audit": "selection_audit.json",
        },
    }
    _write_jsonl(os.path.join(plan_root, "sample_manifest.jsonl"), sample_rows)
    _write_json(
        os.path.join(plan_root, "run_plan.json"),
        {
            "format": "adversarial_policy_carla_run_plan_v1",
            "summary": summary,
            "acceptance_requirements": loop_config["acceptance_requirements"],
            "runs": runs,
        },
    )
    _write_csv(os.path.join(plan_root, "run_plan.csv"), runs)
    _write_json(os.path.join(plan_root, "selection_audit.json"), selection_audit)
    _write_json(os.path.join(plan_root, "summary.json"), summary)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="准备冻结 SAC 与 rule-guided LHS 的 CARLA 独立评估计划"
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir")
    parser.add_argument("--runtime-output-root")
    parser.add_argument("--traffic-manager-port", type=int)
    parser.add_argument("--skip-runner-validation", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_policy_plan_config(args.config)
    plan_root = os.path.abspath(args.output_dir or _default_plan_root(config))
    runtime_output_root = os.path.abspath(
        args.runtime_output_root or _default_runtime_root(config, plan_root)
    )
    summary = prepare_plan(
        plan_config=config,
        plan_root=plan_root,
        runtime_output_root=runtime_output_root,
        traffic_manager_port=args.traffic_manager_port,
        validate_runner=False if args.skip_runner_validation else None,
    )
    print(
        f"[PLAN] baseline={summary['baseline_run_count']} "
        f"candidates={summary['candidate_run_count']} "
        f"total={summary['total_run_count']}"
    )
    print(
        f"[PLAN] strata={summary['generator_target_stratum_count']} "
        f"overlap={summary['selection_audit']['excluded_overlap_count']} "
        f"static_validated={summary['scene_config_validation_count']}"
    )
    print(f"[RESULT_DIR] {plan_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
