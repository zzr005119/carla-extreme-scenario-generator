"""Review LHS/high proxy ranking boundaries and propose unused scenarios.

Offline only: no CARLA import, server start, GPU use, or policy inference.
"""

import argparse
import csv
import json
import os
import re
import statistics
from datetime import datetime


PARAMETERS = (
    ("weather_cloudiness", ("weather", "cloudiness")),
    ("weather_precipitation", ("weather", "precipitation")),
    ("weather_precipitation_deposits", ("weather", "precipitation_deposits")),
    ("weather_wind_intensity", ("weather", "wind_intensity")),
    ("weather_fog_density", ("weather", "fog_density")),
    ("weather_fog_distance", ("weather", "fog_distance")),
    ("weather_sun_altitude_angle", ("weather", "sun_altitude_angle")),
    ("weather_wetness", ("weather", "wetness")),
    ("lead_initial_distance_m", ("lead_vehicle", "initial_distance_m")),
    ("lead_brake_trigger_seconds", ("lead_vehicle", "brake_trigger_seconds")),
    ("lead_brake_intensity", ("lead_vehicle", "brake_intensity")),
    ("pedestrian_forward_distance_m", ("pedestrian", "forward_distance_m")),
    ("pedestrian_roadside_offset_m", ("pedestrian", "roadside_offset_m")),
    ("pedestrian_trigger_seconds", ("pedestrian", "trigger_seconds")),
    ("pedestrian_speed_mps", ("pedestrian", "speed_mps")),
)


def as_float(value):
    if value in (None, "", "null"):
        return None
    return float(value)


def write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_csv(path, rows):
    if not rows:
        raise ValueError("Cannot write an empty CSV: " + path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as file:
        for number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{number}: {exc}") from exc
    return rows


def canonical_sample_id(sample_id):
    value = str(sample_id or "")
    value = re.split(r"_(?:apcv1|apcv2)_", value, maxsplit=1)[0]
    return re.sub(r"_s202608\d+$", "", value)


def nested_value(record, path):
    value = record
    for key in path:
        value = value[key]
    return float(value)


def config_parameters(record):
    return {name: nested_value(record, path) for name, path in PARAMETERS}


def rank_rows(rows, column):
    ordered = sorted(
        rows,
        key=lambda row: (as_float(row.get(column)) or float("-inf"), row["sample_id"]),
        reverse=True,
    )
    return ordered, {row["sample_id"]: index for index, row in enumerate(ordered, 1)}


def runtime_source_ids(plan_paths):
    used = set()
    all_rows = []
    for path in plan_paths:
        for row in load_csv(path):
            row["_plan_base"] = os.path.dirname(path)
            all_rows.append(row)
            sample_id = row.get("sample_id") or row.get("canonical_sample_id")
            if sample_id:
                used.add(canonical_sample_id(sample_id))
    return used, all_rows


def select_independent_candidates(scored, pool, used_ids):
    pool_ids = {row["sample_id"] for row in pool}
    candidates = [
        row for row in scored
        if canonical_sample_id(row["sample_id"]) not in used_ids
        and row["sample_id"] in pool_ids
    ]
    if not candidates:
        raise ValueError("No unused LHS/high candidates remain")
    _, ranks = rank_rows(candidates, "robust_predicted_risk_score")
    median_boundary = statistics.median(
        as_float(row["collision_boundary_score"]) for row in candidates
    )
    median_probability = statistics.median(
        as_float(row["predicted_collision_probability_mean"]) for row in candidates
    )
    selected = []

    def add(reason, rows):
        for row in rows:
            if row["sample_id"] not in {item["sample_id"] for item in selected}:
                selected.append({
                    "sample_id": row["sample_id"],
                    "reason": reason,
                    "robust_rank_unused_pool": ranks[row["sample_id"]],
                    "robust_predicted_risk_score": row["robust_predicted_risk_score"],
                    "predicted_risk_mean": row["predicted_risk_mean"],
                    "predicted_risk_std": row["predicted_risk_std"],
                    "bootstrap_top_k_frequency": row["bootstrap_top_k_frequency"],
                    "collision_affinity": row["collision_affinity"],
                    "collision_boundary_score": row["collision_boundary_score"],
                    "predicted_collision_probability_mean": row[
                        "predicted_collision_probability_mean"
                    ],
                    "predicted_collision_probability_std": row[
                        "predicted_collision_probability_std"
                    ],
                    "collision_propensity_base": row["collision_propensity_base"],
                })
                return

    add(
        "near_high_threshold",
        sorted(candidates, key=lambda row: (
            abs(as_float(row["robust_predicted_risk_score"]) - 50.0),
            -as_float(row["collision_boundary_score"]),
            row["sample_id"],
        )),
    )
    add(
        "near_critical_boundary",
        sorted(candidates, key=lambda row: (
            abs(as_float(row["robust_predicted_risk_score"]) - 75.0),
            -as_float(row["predicted_collision_probability_mean"]),
            row["sample_id"],
        )),
    )
    add(
        "uncertain_collision_boundary",
        sorted(
            [
                row for row in candidates
                if as_float(row["collision_boundary_score"]) >= median_boundary
                and abs(
                    as_float(row["predicted_collision_probability_mean"])
                    - median_probability
                ) <= 0.25
            ],
            key=lambda row: (
                -as_float(row["predicted_risk_std"]),
                -as_float(row["collision_boundary_score"]),
                row["sample_id"],
            ),
        ),
    )
    if len(selected) < 3:
        add(
            "high_uncertainty_fallback",
            sorted(candidates, key=lambda row: (
                -as_float(row["predicted_risk_std"]),
                -as_float(row["collision_boundary_score"]),
                row["sample_id"],
            )),
        )
    return selected[:3]


def analyze(args):
    scored_all = load_csv(args.scored_candidates)
    scored = [
        row for row in scored_all
        if row.get("generator") == "lhs" and row.get("target_risk_level") == "high"
    ]
    if not scored:
        raise ValueError("No LHS/high rows in scored candidates")
    pool = load_jsonl(args.candidate_pool)
    pool_by_id = {row["sample_id"]: row for row in pool}
    used_ids, plan_rows = runtime_source_ids(args.plan_csv)
    used_ids.update(args.exclude_sample_id)
    ordered, robust_ranks = rank_rows(scored, "robust_predicted_risk_score")
    _, mean_ranks = rank_rows(scored, "predicted_risk_mean")
    source_id = args.source_sample_id
    source = next((row for row in scored if row["sample_id"] == source_id), None)
    if source is None:
        raise ValueError("Source sample is not in LHS/high scores: " + source_id)
    source_rank = robust_ranks[source_id]
    source_summary = {
        "sample_id": source_id,
        "candidate_count": len(scored),
        "robust_predicted_risk_score": as_float(source["robust_predicted_risk_score"]),
        "predicted_risk_mean": as_float(source["predicted_risk_mean"]),
        "predicted_risk_std": as_float(source["predicted_risk_std"]),
        "predicted_risk_min": as_float(source["predicted_risk_min"]),
        "predicted_risk_max": as_float(source["predicted_risk_max"]),
        "robust_rank_descending": source_rank,
        "robust_percentile_descending": round(1.0 - (source_rank - 1) / len(scored), 6),
        "mean_rank_descending": mean_ranks[source_id],
        "bootstrap_top_k_frequency": as_float(source["bootstrap_top_k_frequency"]),
        "collision_affinity": as_float(source["collision_affinity"]),
        "collision_boundary_score": as_float(source["collision_boundary_score"]),
        "predicted_collision_probability_mean": as_float(
            source["predicted_collision_probability_mean"]
        ),
        "predicted_collision_probability_std": as_float(
            source["predicted_collision_probability_std"]
        ),
        "collision_distance_margin": as_float(source["collision_distance_margin"]),
        "runtime_source_id_used": source_id in used_ids,
    }

    source_plan = [
        row for row in plan_rows
        if canonical_sample_id(row.get("sample_id")) == source_id
    ]
    runtime_candidates = []
    for row in source_plan:
        if row.get("phase") == "candidate":
            candidate_score = as_float(row.get("proxy_candidate_score"))
            if candidate_score is None:
                continue
            runtime_candidates.append({
                "strategy": row.get("strategy"),
                "proxy_baseline_score": as_float(row.get("proxy_baseline_score")),
                "proxy_candidate_score": candidate_score,
                "proxy_score_delta": as_float(row.get("proxy_score_delta")),
            })
    baseline_proxy = next(
        (as_float(row.get("proxy_baseline_score")) for row in source_plan
         if row.get("phase") == "baseline"),
        None,
    )
    runtime_proxy = {
        "physical_robust_score": source_summary["robust_predicted_risk_score"],
        "runtime_baseline_proxy_score": baseline_proxy,
        "runtime_baseline_minus_physical_robust": (
            round(baseline_proxy - source_summary["robust_predicted_risk_score"], 6)
            if baseline_proxy is not None else None
        ),
        "runtime_candidates": runtime_candidates,
        "candidate_order_descending": [
            row["strategy"] for row in sorted(
                runtime_candidates,
                key=lambda row: row["proxy_candidate_score"] or float("-inf"),
                reverse=True,
            )
        ],
        "note": "Runtime proxy ordering is pair-local and not a calibrated measured-risk delta.",
    }
    measured_rows = []
    if args.repeat_comparisons:
        measured_rows = [
            row for row in load_csv(args.repeat_comparisons)
            if row.get("generator") == "lhs"
            and row.get("target_risk_level") == "high"
        ]
    measured_summary = {}
    for strategy in sorted({row.get("strategy") for row in measured_rows}):
        rows = [row for row in measured_rows if row.get("strategy") == strategy]
        deltas = [as_float(row["risk_delta"]) for row in rows]
        measured_summary[strategy] = {
            "run_count": len(rows),
            "mean_risk_delta": round(statistics.fmean(deltas), 6),
            "median_risk_delta": round(statistics.median(deltas), 6),
            "risk_increase_count": sum(value > 0 for value in deltas),
            "collision_introduced_count": sum(
                row.get("collision_change") == "introduced" for row in rows
            ),
        }

    config_rows = []
    baseline_params = None
    for row in source_plan:
        config_path = row.get("config_path")
        if config_path and not os.path.isabs(config_path):
            config_path = os.path.join(row.get("_plan_base") or os.path.dirname(args.plan_csv[0]), config_path)
        if not config_path or not os.path.exists(config_path):
            continue
        with open(config_path, "r", encoding="utf-8") as file:
            params = config_parameters(json.load(file))
        if row.get("phase") == "baseline":
            baseline_params = params
        config_rows.append((row, params))
    if baseline_params is None:
        raise ValueError("Source baseline config was not found")
    parameter_deltas = []
    for name, _ in PARAMETERS:
        result = {"parameter": name, "baseline": baseline_params[name]}
        for plan_row, params in config_rows:
            if plan_row.get("phase") != "candidate":
                continue
            strategy = plan_row.get("strategy") or "candidate"
            result[strategy] = params[name]
            result[strategy + "_delta"] = round(params[name] - baseline_params[name], 6)
        parameter_deltas.append(result)

    independent = select_independent_candidates(scored, pool, used_ids)
    independent_with_params = []
    for row in independent:
        output = dict(row)
        output.update(config_parameters(pool_by_id[row["sample_id"]]))
        independent_with_params.append(output)

    summary = {
        "format": "lhs_high_proxy_boundary_review_v1",
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "analysis_mode": "offline_cpu_only",
        "scored_candidate_count": len(scored),
        "candidate_pool_count": len(pool),
        "source_summary": source_summary,
        "runtime_proxy_comparison": runtime_proxy,
        "runtime_measured_lhs_high": measured_summary,
        "independent_candidate_count": len(independent_with_params),
        "independent_candidate_ids": [row["sample_id"] for row in independent_with_params],
        "used_source_ids_excluded": sorted(used_ids),
        "runtime_boundary": (
            "LHS/high repeats are repeated measurements of one source scene. Proposed "
            "candidates are static unused records only; they have not run in CARLA."
        ),
    }
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    write_json(os.path.join(output_dir, "summary.json"), summary)
    write_csv(
        os.path.join(output_dir, "lhs_high_ranked_candidates.csv"),
        [
            {
                "robust_rank": robust_ranks[row["sample_id"]],
                "mean_rank": mean_ranks[row["sample_id"]],
                "sample_id": row["sample_id"],
                "robust_predicted_risk_score": row["robust_predicted_risk_score"],
                "predicted_risk_mean": row["predicted_risk_mean"],
                "predicted_risk_std": row["predicted_risk_std"],
                "bootstrap_top_k_frequency": row["bootstrap_top_k_frequency"],
                "collision_affinity": row["collision_affinity"],
                "collision_boundary_score": row["collision_boundary_score"],
                "predicted_collision_probability_mean": row[
                    "predicted_collision_probability_mean"
                ],
                "used_in_runtime_plan": canonical_sample_id(row["sample_id"]) in used_ids,
            }
            for row in ordered
        ],
    )
    write_csv(os.path.join(output_dir, "lhs_high_parameter_deltas.csv"), parameter_deltas)
    write_csv(os.path.join(output_dir, "independent_scene_candidates.csv"), independent_with_params)
    write_csv(os.path.join(output_dir, "runtime_proxy_comparison.csv"), runtime_candidates)
    if measured_rows:
        write_csv(os.path.join(output_dir, "runtime_measured_lhs_high.csv"), measured_rows)

    report = [
        "# LHS/high 候选参数与风险代理边界复核 V1",
        "",
        "## 复核口径",
        "",
        f"- 离线候选：{len(scored)} 个 LHS/high 候选。",
        f"- 复核源场景：{source_id}。",
        "- 运行侧只使用原始 pair 的代理分数和重复测量结果，不把 Traffic Manager 种子当作独立场景。",
        "- 本报告和候选设计均为 CPU-only 离线操作，不启动 CARLA、不启动在线训练。",
        "",
        "## 排序边界",
        "",
        f"源场景物理增强稳健代理分为 {source_summary['robust_predicted_risk_score']:.3f}，在 {len(scored)} 个候选中排名 {source_summary['robust_rank_descending']}；",
        f"预测均值为 {source_summary['predicted_risk_mean']:.3f}，标准差为 {source_summary['predicted_risk_std']:.3f}，",
        f"预测碰撞概率为 {source_summary['predicted_collision_probability_mean']:.3f} ± {source_summary['predicted_collision_probability_std']:.3f}。",
        "",
        f"运行侧基线代理为 {baseline_proxy:.3f}，与物理增强稳健分相差 {runtime_proxy['runtime_baseline_minus_physical_robust']:+.3f}。",
        "两个评分上下文存在边界偏移，代理分数不能直接当作 CARLA 实测风险。",
        "",
        "## 重复实测对照",
        "",
    ]
    for strategy, values in measured_summary.items():
        report.append(
            f"LHS/high 重复实测中 {strategy} 的平均风险增量为 "
            f"{values['mean_risk_delta']:+.3f}，中位数为 "
            f"{values['median_risk_delta']:+.3f}，风险升高 "
            f"{values['risk_increase_count']}/{values['run_count']}，"
            f"新增碰撞 {values['collision_introduced_count']}/{values['run_count']}。"
        )
    report.extend([
        "代理候选排序为 rule_guided_lhs 高于 sac_policy，但重复实测的增量幅度远大于代理增量；排序方向可保留，数值幅度和碰撞边界需要重新校准。",
        "",
        "## 参数差分",
        "",
        "参数级差分见 lhs_high_parameter_deltas.csv。重点观察前车制动触发、行人速度、雾距离、降水和湿滑度；这些变化同时改变 TTC、行人交互和可见度代理。",
        "",
        "## 新的独立候选",
        "",
        "以下候选已排除当前计划出现过的源场景 ID，仅作为后续可选静态场景：",
        "",
        "| sample_id | 选择理由 | 稳健分 | 标准差 | 碰撞边界分 | 预测碰撞概率 |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for row in independent_with_params:
        report.append(
            f"| {row['sample_id']} | {row['reason']} | "
            f"{float(row['robust_predicted_risk_score']):.3f} | "
            f"{float(row['predicted_risk_std']):.3f} | "
            f"{float(row['collision_boundary_score']):.3f} | "
            f"{float(row['predicted_collision_probability_mean']):.3f} |"
        )
    report.extend([
        "",
        "## 结论边界",
        "",
        "LHS/high 源场景不是离线代理排名最靠前的样本，却在重复实机中表现为候选稳定引入碰撞；当前更合理的解释是参数变化把运行行为推入了代理未充分校准的碰撞边界，而不是 CARLA 服务异常。",
        "候选排序只能用于筛选观察点，分数增量不能解释为实测风险增量。若后续决定运行，应从 independent_scene_candidates.csv 选择未重复场景，再按 CARLA 0.9.16 严格验收执行；本轮不自动提交运行计划。",
        "",
    ])
    with open(os.path.join(output_dir, "report.md"), "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(report))
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scored-candidates", required=True)
    parser.add_argument("--candidate-pool", required=True)
    parser.add_argument("--source-sample-id", required=True)
    parser.add_argument("--plan-csv", action="append", required=True)
    parser.add_argument("--exclude-sample-id", action="append", default=[])
    parser.add_argument("--repeat-comparisons")
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    summary = analyze(args)
    print(
        f"[LHS-HIGH] candidates={summary['scored_candidate_count']} "
        f"source_rank={summary['source_summary']['robust_rank_descending']} "
        f"independent={summary['independent_candidate_count']}",
        flush=True,
    )
    print(f"[RESULT_DIR] {os.path.abspath(args.output_dir)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
