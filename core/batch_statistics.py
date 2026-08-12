"""批量重复实验的描述性统计。"""

import json
import statistics


METRIC_FIELDS = [
    "collision_count",
    "minimum_ttc_seconds",
    "minimum_lead_gap_m",
    "minimum_pedestrian_distance_m",
    "risk_score",
    "rgb_frames",
    "depth_frames",
    "semantic_frames",
    "total_frames",
]

AGGREGATE_FIELDS = [
    "variant",
    "planned_runs",
    "attempted_runs",
    "completed_runs",
    "failed_runs",
    "unattempted_runs",
    "success_rate_pct",
    "sensor_success_rate_pct",
    "server_health_success_rate_pct",
    "traffic_manager_seeds",
    "dominant_risk_level",
    "risk_level_counts",
]
for metric_name in METRIC_FIELDS:
    AGGREGATE_FIELDS.extend(
        [
            f"{metric_name}_mean",
            f"{metric_name}_std",
        ]
    )


def _numeric_values(rows, field_name):
    values = []
    for row in rows:
        value = row.get(field_name)
        if value in (None, ""):
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def _mean_and_std(values):
    if not values:
        return "", ""
    mean_value = round(statistics.fmean(values), 3)
    std_value = round(statistics.stdev(values), 3) if len(values) > 1 else 0.0
    return mean_value, std_value


def _percentage(numerator, denominator):
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 3)


def aggregate_variant_rows(variant_names, rows, repeat_count):
    aggregates = []
    risk_order = {
        "unknown": -1,
        "low": 0,
        "medium": 1,
        "high": 2,
        "critical": 3,
    }
    for variant_name in variant_names:
        variant_rows = [row for row in rows if row["variant"] == variant_name]
        completed_rows = [
            row for row in variant_rows if row["status"] == "completed"
        ]
        attempted_runs = len(variant_rows)
        completed_runs = len(completed_rows)
        failed_runs = attempted_runs - completed_runs
        unattempted_runs = max(0, repeat_count - attempted_runs)

        risk_counts = {}
        for row in completed_rows:
            level = row.get("risk_level") or "unknown"
            risk_counts[level] = risk_counts.get(level, 0) + 1
        dominant_risk_level = ""
        if risk_counts:
            dominant_risk_level = max(
                risk_counts,
                key=lambda level: (
                    risk_counts[level],
                    risk_order.get(level, -1),
                ),
            )

        seeds = []
        for row in variant_rows:
            seed = row.get("traffic_manager_seed")
            if seed not in (None, "") and seed not in seeds:
                seeds.append(seed)

        aggregate = {
            "variant": variant_name,
            "planned_runs": repeat_count,
            "attempted_runs": attempted_runs,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
            "unattempted_runs": unattempted_runs,
            "success_rate_pct": _percentage(completed_runs, repeat_count),
            "sensor_success_rate_pct": _percentage(
                sum(
                    row.get("sensor_pipeline_status") == "completed"
                    for row in variant_rows
                ),
                repeat_count,
            ),
            "server_health_success_rate_pct": _percentage(
                sum(
                    row.get("server_health_status") == "healthy"
                    for row in variant_rows
                ),
                repeat_count,
            ),
            "traffic_manager_seeds": ",".join(str(seed) for seed in seeds),
            "dominant_risk_level": dominant_risk_level,
            "risk_level_counts": json.dumps(
                risk_counts,
                ensure_ascii=False,
                sort_keys=True,
            ),
        }
        for metric_name in METRIC_FIELDS:
            mean_value, std_value = _mean_and_std(
                _numeric_values(completed_rows, metric_name)
            )
            aggregate[f"{metric_name}_mean"] = mean_value
            aggregate[f"{metric_name}_std"] = std_value
        aggregates.append(aggregate)
    return aggregates
