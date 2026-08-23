"""Select a seeded, stratified batch of unused LHS/high calibration scenes."""

import argparse
import csv
import json
import os
import random
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_validator import require_valid_scenario  # noqa: E402


STRATA = (
    {
        "stratum": "near_high_low_collision",
        "risk_min": 45.0,
        "risk_max": 50.0,
        "prob_min": 0.0,
        "prob_max": 0.33,
        "risk_target": 49.5,
        "prob_target": 0.20,
    },
    {
        "stratum": "high_threshold_uncertain_collision",
        "risk_min": 50.0,
        "risk_max": 55.0,
        "prob_min": 0.33,
        "prob_max": 0.50,
        "risk_target": 52.5,
        "prob_target": 0.42,
    },
    {
        "stratum": "mid_low_collision",
        "risk_min": 55.0,
        "risk_max": 60.0,
        "prob_min": 0.0,
        "prob_max": 0.33,
        "risk_target": 57.5,
        "prob_target": 0.25,
    },
    {
        "stratum": "mid_uncertain_collision",
        "risk_min": 55.0,
        "risk_max": 60.0,
        "prob_min": 0.33,
        "prob_max": 0.50,
        "risk_target": 57.5,
        "prob_target": 0.42,
    },
    {
        "stratum": "mid_high_collision",
        "risk_min": 55.0,
        "risk_max": 60.0,
        "prob_min": 0.50,
        "prob_max": 1.01,
        "risk_target": 59.5,
        "prob_target": 0.58,
    },
    {
        "stratum": "upper_high_collision",
        "risk_min": 60.0,
        "risk_max": 70.0,
        "prob_min": 0.50,
        "prob_max": 1.01,
        "risk_target": 64.5,
        "prob_target": 0.67,
    },
)


def _as_float(row, field):
    value = row.get(field)
    if value in (None, ""):
        raise ValueError(f"Missing {field} for {row.get('sample_id')}")
    return float(value)


def _optional_float(row, field):
    value = row.get(field)
    return None if value in (None, "") else float(value)


def _canonical_id(value):
    return str(value or "").split("_adv_", 1)[0].split("_apcv", 1)[0]


def load_scored(path):
    with open(os.path.abspath(path), "r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    rows = [
        row for row in rows
        if row.get("generator") in (None, "", "lhs")
        and row.get("target_risk_level") in (None, "", "high")
    ]
    by_id = {}
    for row in rows:
        sample_id = row.get("sample_id")
        if not sample_id:
            raise ValueError(f"Scored row missing sample_id: {path}")
        if sample_id in by_id:
            raise ValueError(f"Duplicate scored sample_id: {sample_id}")
        by_id[sample_id] = row
    return by_id


def load_pool(path):
    records = {}
    with open(os.path.abspath(path), "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            require_valid_scenario(record)
            sample_id = record["sample_id"]
            if sample_id in records:
                raise ValueError(f"Duplicate pool sample_id at line {line_number}: {sample_id}")
            records[sample_id] = record
    return records


def _in_stratum(row, spec):
    score = _as_float(row, "robust_predicted_risk_score")
    probability = _as_float(row, "predicted_collision_probability_mean")
    return (
        spec["risk_min"] <= score < spec["risk_max"]
        and spec["prob_min"] <= probability < spec["prob_max"]
    )


def select_batch(scored_by_id, pool_by_id, excluded_ids, seed=20260823):
    excluded = {_canonical_id(value) for value in excluded_ids}
    available = {
        sample_id: row for sample_id, row in scored_by_id.items()
        if _canonical_id(sample_id) not in excluded and sample_id in pool_by_id
    }
    selected = []
    for spec in STRATA:
        candidates = [row for row in available.values() if _in_stratum(row, spec)]
        if not candidates:
            raise ValueError(f"No candidate available for stratum {spec['stratum']}")
        candidates.sort(
            key=lambda row: (
                abs(_as_float(row, "robust_predicted_risk_score") - spec["risk_target"])
                + 0.5 * abs(_as_float(row, "predicted_collision_probability_mean") - spec["prob_target"]),
                -_as_float(row, "predicted_risk_std"),
                row["sample_id"],
            )
        )
        selected.append((spec, candidates[0]))
        available.pop(candidates[0]["sample_id"])

    order = list(range(len(selected)))
    random.Random(int(seed)).shuffle(order)
    outputs = []
    for selection_order, index in enumerate(order, 1):
        spec, scored = selected[index]
        sample_id = scored["sample_id"]
        outputs.append({
            "selection_order": selection_order,
            "stratum": spec["stratum"],
            "sample_id": sample_id,
            "robust_rank": int(scored["robust_rank"]),
            "robust_predicted_risk_score": _as_float(scored, "robust_predicted_risk_score"),
            "predicted_risk_mean": _as_float(scored, "predicted_risk_mean"),
            "predicted_risk_std": _as_float(scored, "predicted_risk_std"),
            "predicted_collision_probability_mean": _as_float(scored, "predicted_collision_probability_mean"),
            "predicted_collision_probability_std": _optional_float(scored, "predicted_collision_probability_std"),
            "collision_boundary_score": _as_float(scored, "collision_boundary_score"),
            "bootstrap_top_k_frequency": _as_float(scored, "bootstrap_top_k_frequency"),
            "selection_risk_target": spec["risk_target"],
            "selection_probability_target": spec["prob_target"],
        })
    return outputs


def write_batch(selection, pool_by_id, output_dir, source_pool, scored_path, excluded_ids, seed):
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=False)
    records_path = os.path.join(output_dir, "independent_candidates.jsonl")
    with open(records_path, "w", encoding="utf-8") as file:
        for row in selection:
            file.write(json.dumps(pool_by_id[row["sample_id"]], ensure_ascii=False, sort_keys=True) + "\n")
    fields = list(selection[0])
    with open(os.path.join(output_dir, "independent_candidates.csv"), "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selection)
    summary = {
        "format": "lhs_high_calibration_batch_selection_v1",
        "evidence_kind": "static_validation",
        "analysis_mode": "offline_cpu_only",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "candidate_count": len(selection),
        "selection_seed": int(seed),
        "excluded_sample_ids": sorted({_canonical_id(value) for value in excluded_ids}),
        "selected_sample_ids": [row["sample_id"] for row in selection],
        "strata": [row["stratum"] for row in selection],
        "source_pool": os.path.abspath(source_pool),
        "source_scored_candidates": os.path.abspath(scored_path),
        "runtime_executed": False,
        "runtime_boundary": "Six unused LHS/high records were selected in supported joint proxy strata; no CARLA run or online training is included.",
    }
    with open(os.path.join(output_dir, "selection_summary.json"), "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
        file.write("\n")
    report = [
        "# LHS/high 独立校准批次选择 V1",
        "",
        "本批次使用代理风险分与预测碰撞概率的联合支持域分层，选择 6 条未运行的独立场景。候选选择按分层中心距离确定，运行顺序使用固定种子随机化。",
        "",
        f"- 选择种子：`{seed}`",
        f"- 排除样本：`{len(summary['excluded_sample_ids'])}` 条",
        f"- 新增独立候选：`{len(selection)}` 条",
        "- 本阶段仅生成静态计划，不启动 CARLA、不启动在线训练。",
        "",
        "| 顺序 | 分层 | sample_id | 代理稳健分 | 预测碰撞概率 | 代理标准差 |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for row in selection:
        report.append(
            f"| {row['selection_order']} | {row['stratum']} | {row['sample_id']} | "
            f"{row['robust_predicted_risk_score']:.3f} | "
            f"{row['predicted_collision_probability_mean']:.3f} | "
            f"{row['predicted_risk_std']:.3f} |"
        )
    report.extend([
        "",
        "这 6 个分层来自当前候选池实际存在的联合支持域，不将不存在的‘高风险低碰撞概率’组合当作可估计格子。重复 Traffic Manager 种子仍不计为独立样本。",
        "",
    ])
    with open(os.path.join(output_dir, "selection_report.md"), "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(report))
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scored-candidates", required=True)
    parser.add_argument("--candidate-pool", required=True)
    parser.add_argument("--exclude-sample-id", action="append", default=[])
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    scored = load_scored(args.scored_candidates)
    pool = load_pool(args.candidate_pool)
    selection = select_batch(scored, pool, args.exclude_sample_id, args.seed)
    summary = write_batch(selection, pool, args.output_dir, args.candidate_pool, args.scored_candidates, args.exclude_sample_id, args.seed)
    print(f"[SELECT] candidates={summary['candidate_count']} seed={summary['selection_seed']}", flush=True)
    print(f"[RESULT_DIR] {os.path.abspath(args.output_dir)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
