"""Select one CARLA RL checkpoint using comparable dev-only evaluations."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


SELECTION_FORMAT = "carla_online_rl_checkpoint_selection_v1"
EVALUATION_FORMAT = "carla_online_rl_evaluation_v2"


def _load_json(path):
    path = Path(path).expanduser().resolve()
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取评估摘要: {path}") from exc


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate(summary_path):
    path, summary = _load_json(summary_path)
    if summary.get("format") != EVALUATION_FORMAT:
        raise ValueError(f"评估摘要不是 V2 格式: {path}")
    if summary.get("split") != "dev":
        raise ValueError(f"checkpoint 选择只允许 dev 结果，收到 {summary.get('split')}: {path}")
    acceptance = summary.get("acceptance") or {}
    required_gates = {
        "baseline_strict_acceptance",
        "candidate_condition_validity",
        "candidate_runtime_strict_acceptance",
        "candidate_evidence_completeness",
    }
    checks = acceptance.get("checks") or {}
    if (
        acceptance.get("status") != "passed"
        or set(checks) != required_gates
        or not all((checks.get(name) or {}).get("passed") is True for name in required_gates)
    ):
        raise ValueError(f"dev 四项验收未通过: {path}")
    policy = summary.get("evaluation_policy") or {}
    if policy.get("selection_mode") != "best_so_far":
        raise ValueError(f"dev 评估未使用 best_so_far: {path}")
    effect = summary.get("effect_summary") or {}
    dev_count = int(summary.get("test_count", -1))
    if (
        effect.get("status") != "descriptive_only"
        or int(effect.get("row_count", 0)) < 1
        or int(effect.get("row_count", 0)) != dev_count
    ):
        raise ValueError(f"dev 效果统计不完整: {path}")
    for field in ("algorithm", "scenario_plan_sha256", "config_sha256"):
        if not summary.get(field):
            raise ValueError(f"dev 摘要缺少 {field}: {path}")
    if int(summary.get("seed", -1)) < 0 or dev_count < 1:
        raise ValueError(f"dev 摘要的 seed/count 无效: {path}")
    model_path = Path(str(summary.get("model_path") or "")).expanduser().resolve()
    if not model_path.is_file():
        raise ValueError(f"dev 对应 checkpoint 不存在: {model_path}")
    model_sha256 = _sha256_file(model_path)
    if summary.get("model_sha256") != model_sha256:
        raise ValueError(f"checkpoint 哈希与 dev 摘要不一致: {model_path}")
    row_count = int(effect["row_count"])
    risk_increase_count = int(effect.get("risk_increase_count", 0))
    return {
        "evaluation_summary_path": str(path),
        "evaluation_summary_sha256": _sha256_file(path),
        "model_path": str(model_path),
        "model_sha256": model_sha256,
        "trained_num_timesteps": int(summary.get("model_trained_num_timesteps", -1)),
        "algorithm": summary.get("algorithm"),
        "scenario_plan_sha256": summary.get("scenario_plan_sha256"),
        "config_sha256": summary.get("config_sha256"),
        "evaluation_seed": int(summary.get("seed", -1)),
        "dev_count": dev_count,
        "delta_mean": float(effect["delta_mean"]),
        "delta_median": float(effect["delta_median"]),
        "risk_increase_count": risk_increase_count,
        "risk_increase_rate": risk_increase_count / row_count,
        "selected_candidate_mean": float(effect["selected_candidate_mean"]),
        "acceptance_status": "passed",
    }


def _rank_key(candidate):
    return (
        candidate["delta_mean"],
        candidate["risk_increase_rate"],
        candidate["selected_candidate_mean"],
        -candidate["trained_num_timesteps"],
    )


def select_checkpoint(summary_paths, output_path):
    if not summary_paths:
        raise ValueError("至少需要一个 dev 评估摘要")
    candidates = [_candidate(path) for path in summary_paths]
    comparison_fields = (
        "algorithm",
        "scenario_plan_sha256",
        "config_sha256",
        "evaluation_seed",
        "dev_count",
    )
    for field in comparison_fields:
        values = {candidate[field] for candidate in candidates}
        if len(values) != 1:
            raise ValueError(f"dev 评估口径不一致: {field}={sorted(values, key=str)}")
    steps = [candidate["trained_num_timesteps"] for candidate in candidates]
    if any(step < 0 for step in steps) or len(steps) != len(set(steps)):
        raise ValueError("dev 评估的 checkpoint 步数缺失或重复")
    ranked = sorted(candidates, key=_rank_key, reverse=True)
    for rank, candidate in enumerate(ranked, start=1):
        candidate["rank"] = rank
    selected = ranked[0]
    promotion_checks = {
        "positive_mean_risk_delta": {
            "passed": selected["delta_mean"] > 0.0,
            "actual": selected["delta_mean"],
            "expected": "> 0.0",
        },
        "majority_risk_increase": {
            "passed": selected["risk_increase_rate"] > 0.5,
            "actual": selected["risk_increase_rate"],
            "expected": "> 0.5",
        },
    }
    manifest = {
        "format": SELECTION_FORMAT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_split": "dev",
        "selection_policy": [
            "delta_mean_desc",
            "risk_increase_rate_desc",
            "selected_candidate_mean_desc",
            "trained_num_timesteps_asc",
        ],
        "candidate_count": len(ranked),
        "comparison_contract": {
            field: selected[field] for field in comparison_fields
        },
        "selected_model_path": selected["model_path"],
        "selected_model_sha256": selected["model_sha256"],
        "selected_trained_num_timesteps": selected["trained_num_timesteps"],
        "selected_evaluation_summary_path": selected["evaluation_summary_path"],
        "candidates": ranked,
        "promotion_gate": {
            "status": (
                "passed"
                if all(check["passed"] for check in promotion_checks.values())
                else "failed"
            ),
            "scope": "dev_experiment_decision_only",
            "checks": promotion_checks,
        },
        "test_split_used_for_selection": False,
    }
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args():
    parser = argparse.ArgumentParser(description="使用同口径 dev 评估选择 RL checkpoint")
    parser.add_argument("--evaluation-summary", action="append", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    result = select_checkpoint(args.evaluation_summary, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
