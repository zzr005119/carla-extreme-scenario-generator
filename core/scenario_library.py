"""极端场景库条目构建、哈希去重和质量评估。"""

import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath

from core.scenario_features import FEATURE_SPECS, HAZARD_TAGS
from core.scenario_validator import (
    derive_weather_tags,
    require_valid_scenario,
    validate_schema_value,
)


RISK_LEVELS = ("low", "medium", "high", "critical")
EVIDENCE_FIELDS = (
    ("status", "completed"),
    ("acceptance_status", "completed"),
    ("runtime_verified", True),
    ("sensor_status", "completed"),
    ("server_status", "healthy"),
    ("route_verified", True),
    ("metadata_path", "present"),
    ("carla_client_version", "present"),
    ("carla_server_version", "present"),
)


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_jsonl(path):
    records = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            stripped = line.strip()
            if stripped:
                records.append((line_number, json.loads(stripped)))
    return records


def load_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def value_sha256(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_bool(value):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def optional_float(value):
    if value is None or str(value).strip() == "":
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def optional_int(value):
    number = optional_float(value)
    return None if number is None else int(number)


def resolve_project_path(project_root, raw_path):
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(project_root) / path
    return path.resolve()


def resolve_candidate_path(project_root, candidates):
    for raw_path in candidates:
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(project_root) / path
        if path.is_file():
            return path.resolve()
    raise FileNotFoundError(f"候选路径均不可用: {candidates}")


def require_file_hash(path, expected_sha256):
    actual_sha256 = file_sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"文件哈希不匹配: {path} | expected={expected_sha256} | actual={actual_sha256}"
        )
    return actual_sha256


def resolve_manifest_file(project_root, source_dir, raw_path):
    path = Path(raw_path)
    if path.is_file():
        return path.resolve()
    if not path.is_absolute():
        candidate = (Path(project_root) / path).resolve()
        if candidate.is_file():
            return candidate
    filename = PureWindowsPath(str(raw_path)).name
    for candidate in (
        Path(source_dir) / "configs" / filename,
        Path(source_dir) / filename,
    ):
        if candidate.is_file():
            return candidate.resolve()
    return None


def portable_path(project_root, path):
    path = Path(path).resolve()
    try:
        return path.relative_to(Path(project_root).resolve()).as_posix()
    except ValueError:
        return str(path)


def scenario_identity_payload(record):
    return {
        "family": record["family"],
        "duration_seconds": record["scenario"]["duration_seconds"],
        "weather": record["weather"],
        "lead_vehicle": record["lead_vehicle"],
        "pedestrian": record["pedestrian"],
    }


def normalized_parameter_vector(record):
    values = []
    for dotted_name, lower, upper in FEATURE_SPECS:
        value = record
        for part in dotted_name.split("."):
            value = value[part]
        normalized = (float(value) - lower) / (upper - lower)
        values.append(min(1.0, max(0.0, normalized)))
    return values


def normalized_distance(left, right):
    squared = sum((a - b) ** 2 for a, b in zip(left, right))
    return math.sqrt(squared / len(left))


def _evidence_component_matches(row, field, expected):
    value = row.get(field)
    if expected is True:
        return parse_bool(value) is True
    if expected == "present":
        return value is not None and str(value).strip() != ""
    return str(value).strip().lower() == expected


def evidence_completeness_score(rows):
    if not rows:
        return 0.0
    matched = sum(
        _evidence_component_matches(row, field, expected)
        for row in rows
        for field, expected in EVIDENCE_FIELDS
    )
    return matched / (len(rows) * len(EVIDENCE_FIELDS))


def aggregate_evidence_completeness_score():
    return 6.0 / 9.0


def _minimum(rows, field):
    values = [optional_float(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _modal_risk_level(rows):
    counts = Counter(
        row.get("observed_risk_level")
        for row in rows
        if row.get("observed_risk_level") in RISK_LEVELS
    )
    if not counts:
        raise ValueError("缺少合法的实测风险等级")
    return max(RISK_LEVELS, key=lambda level: (counts[level], RISK_LEVELS.index(level)))


def _quality_tier(executability, evidence, repeatability):
    if executability == 1.0 and evidence >= 0.95 and repeatability >= 0.9:
        return "gold"
    if executability >= 0.9 and evidence >= 0.75 and repeatability >= 0.75:
        return "silver"
    return "bronze"


def _source_generator(planned_runs, record):
    generators = {
        str(run.get("generator")).strip()
        for run in planned_runs
        if str(run.get("generator") or "").strip()
    }
    if generators:
        return sorted(generators)[0]
    return record["sample_id"].split("_", 1)[0]


def _strictly_accepted(planned_runs, result_rows):
    if not planned_runs or len(planned_runs) != len(result_rows):
        return False
    expected_ids = {run["run_id"] for run in planned_runs}
    actual_ids = {row["run_id"] for row in result_rows}
    return expected_ids == actual_ids and all(
        row.get("status") == "completed"
        and row.get("acceptance_status") == "completed"
        for row in result_rows
    )


def _source_ref(
    project_root,
    source,
    manifest,
    record,
    line_number,
    selected_path,
    manifest_path,
    run_results_path,
    generator,
):
    return {
        "source_id": source["source_id"],
        "experiment_format": str(manifest.get("format") or "unknown"),
        "generator": generator,
        "generator_implementation": record["provenance"]["generator"],
        "generator_seed": int(record["provenance"]["generator_seed"]),
        "source_record_path": f"{portable_path(project_root, selected_path)}#L{line_number}",
        "source_record_sha256": value_sha256(record),
        "selected_records_path": portable_path(project_root, selected_path),
        "selected_records_sha256": file_sha256(selected_path),
        "manifest_path": portable_path(project_root, manifest_path),
        "manifest_sha256": file_sha256(manifest_path),
        "run_results_path": portable_path(project_root, run_results_path),
        "run_results_sha256": file_sha256(run_results_path),
    }


def _aggregate_source_ref(
    project_root,
    source,
    record,
    row,
    dataset_path,
    dataset_sha256,
    merge_summary_path,
    merge_summary_sha256,
):
    generator = row["generator"]
    return {
        "source_id": source["source_id"],
        "experiment_format": "risk_feedback_dataset_merge_v2",
        "generator": generator,
        "generator_implementation": f"{generator}_risk_feedback_v5_aggregate",
        "generator_seed": None,
        "source_record_path": (
            f"{portable_path(project_root, dataset_path)}#sample_id={row['sample_id']}"
        ),
        "source_record_sha256": value_sha256(row),
        "selected_records_path": portable_path(project_root, dataset_path),
        "selected_records_sha256": dataset_sha256,
        "manifest_path": portable_path(project_root, merge_summary_path),
        "manifest_sha256": merge_summary_sha256,
        "run_results_path": portable_path(project_root, dataset_path),
        "run_results_sha256": dataset_sha256,
    }


def _config_ref(project_root, source_dir, planned_run):
    config_path = resolve_manifest_file(
        project_root,
        source_dir,
        planned_run.get("config_path") or "",
    )
    if config_path is None:
        raw_path = str(planned_run.get("config_path") or "missing")
        return {
            "run_id": planned_run["run_id"],
            "path": raw_path,
            "sha256": None,
        }
    return {
        "run_id": planned_run["run_id"],
        "path": portable_path(project_root, config_path),
        "sha256": file_sha256(config_path),
    }


def _new_accumulator(record):
    return {
        "record": record,
        "aliases": set(),
        "target_risk_levels": set(),
        "weather_tags": set(),
        "hazard_tags": set(),
        "generators": set(),
        "source_refs": [],
        "expected_runs": {},
        "result_rows": {},
        "aggregate_rows": {},
        "config_refs": {},
        "aggregate_refs": {},
        "aggregate_sensor_statuses": set(),
        "aggregate_server_statuses": set(),
        "risk_methods": set(),
    }


def _aggregate_record(row, source, build_date):
    weather = {
        "cloudiness": float(row["parameter_weather_cloudiness"]),
        "precipitation": float(row["parameter_weather_precipitation"]),
        "precipitation_deposits": float(
            row["parameter_weather_precipitation_deposits"]
        ),
        "wind_intensity": float(row["parameter_weather_wind_intensity"]),
        "fog_density": float(row["parameter_weather_fog_density"]),
        "fog_distance": float(row["parameter_weather_fog_distance"]),
        "sun_altitude_angle": float(row["parameter_weather_sun_altitude_angle"]),
        "wetness": float(row["parameter_weather_wetness"]),
    }
    traffic_seeds = [
        int(value.strip())
        for value in row["traffic_manager_seeds"].split(",")
        if value.strip()
    ]
    record = {
        "schema_version": "1.0",
        "sample_id": row["sample_id"],
        "family": "multi_hazard_parameter_v1",
        "conditions": {
            "target_risk_level": row["target_risk_level"],
            "weather_tags": derive_weather_tags(weather),
            "hazard_tags": list(HAZARD_TAGS),
            "condition_text_zh": "风险反馈 V5 聚合场景",
        },
        "scenario": {
            "duration_seconds": float(source["duration_seconds"]),
            "traffic_manager_seed": traffic_seeds[0],
        },
        "weather": weather,
        "lead_vehicle": {
            "initial_distance_m": float(
                row["parameter_lead_vehicle_initial_distance_m"]
            ),
            "brake_trigger_seconds": float(
                row["parameter_lead_vehicle_brake_trigger_seconds"]
            ),
            "brake_intensity": float(
                row["parameter_lead_vehicle_brake_intensity"]
            ),
        },
        "pedestrian": {
            "forward_distance_m": float(
                row["parameter_pedestrian_forward_distance_m"]
            ),
            "roadside_offset_m": float(
                row["parameter_pedestrian_roadside_offset_m"]
            ),
            "spawn_z_offset_m": float(source["pedestrian_spawn_z_offset_m"]),
            "trigger_seconds": float(row["parameter_pedestrian_trigger_seconds"]),
            "speed_mps": float(row["parameter_pedestrian_speed_mps"]),
        },
        "observed_risk": {
            "status": "not_simulated",
            "method": None,
            "score": None,
            "level": None,
            "run_dir": None,
        },
        "provenance": {
            "source_kind": "real_carla_run",
            "generator": "risk_feedback_v5_aggregate",
            "generator_seed": 0,
            "split": "inference",
            "created_at": build_date,
        },
    }
    require_valid_scenario(record)
    return record


def _register_common(accumulator, record, generator, risk_method):
    accumulator["aliases"].add(record["sample_id"])
    accumulator["target_risk_levels"].add(
        record["conditions"]["target_risk_level"]
    )
    accumulator["weather_tags"].update(record["conditions"]["weather_tags"])
    accumulator["hazard_tags"].update(record["conditions"]["hazard_tags"])
    accumulator["generators"].add(generator)
    accumulator["risk_methods"].add(risk_method)


def _register_file_ref(accumulator, role, project_root, path, sha256=None):
    sha256 = sha256 or file_sha256(path)
    portable = portable_path(project_root, path)
    accumulator["aggregate_refs"][(role, portable, sha256)] = {
        "role": role,
        "path": portable,
        "sha256": sha256,
    }


def _collect_run_bundle_source(source, source_config, project_root, accumulators, stats):
    selected_path = resolve_project_path(project_root, source["selected_records"])
    manifest_path = resolve_project_path(project_root, source["manifest"])
    run_results_path = resolve_project_path(project_root, source["run_results"])
    source_dir = manifest_path.parent
    manifest = load_json(manifest_path)
    selected_records = load_jsonl(selected_path)
    result_rows = load_csv(run_results_path)
    rows_by_sample = defaultdict(list)
    for row in result_rows:
        rows_by_sample[row["sample_id"]].append(row)
    planned_by_sample = defaultdict(list)
    for run in manifest.get("runs") or []:
        planned_by_sample[run["sample_id"]].append(run)

    for line_number, record in selected_records:
        stats["input_record_count"] += 1
        require_valid_scenario(record)
        sample_id = record["sample_id"]
        planned_runs = planned_by_sample.get(sample_id, [])
        actual_rows = rows_by_sample.get(sample_id, [])
        strict = _strictly_accepted(planned_runs, actual_rows)
        if source.get("strict_only", False) and not strict:
            stats["excluded_record_count"] += 1
            continue
        scenario_hash = value_sha256(scenario_identity_payload(record))
        if scenario_hash in accumulators:
            stats["duplicate_record_count"] += 1
        accumulator = accumulators.setdefault(scenario_hash, _new_accumulator(record))
        generator = _source_generator(planned_runs, record)
        _register_common(accumulator, record, generator, source["risk_method"])
        accumulator["source_refs"].append(
            _source_ref(
                project_root,
                source,
                manifest,
                record,
                line_number,
                selected_path,
                manifest_path,
                run_results_path,
                generator,
            )
        )
        _register_file_ref(accumulator, "selected_records", project_root, selected_path)
        _register_file_ref(accumulator, "experiment_manifest", project_root, manifest_path)
        _register_file_ref(accumulator, "run_results", project_root, run_results_path)
        for run in planned_runs:
            accumulator["expected_runs"][run["run_id"]] = run
            accumulator["config_refs"][run["run_id"]] = _config_ref(
                project_root,
                source_dir,
                run,
            )
        for row in actual_rows:
            accumulator["result_rows"][row["run_id"]] = row


def _collect_aggregate_source(source, source_config, project_root, accumulators, stats):
    dataset_path = resolve_candidate_path(project_root, source["dataset_candidates"])
    merge_summary_path = resolve_candidate_path(
        project_root,
        source["merge_summary_candidates"],
    )
    dataset_sha256 = require_file_hash(
        dataset_path,
        source["expected_dataset_sha256"],
    )
    merge_summary_sha256 = require_file_hash(
        merge_summary_path,
        source["expected_merge_summary_sha256"],
    )
    merge_summary = load_json(merge_summary_path)
    rows = load_csv(dataset_path)
    expected_count = int(merge_summary["merged_dataset"]["independent_scenario_count"])
    if len(rows) != expected_count:
        raise ValueError(
            f"{source['source_id']}: 聚合数据数量不一致 {len(rows)} != {expected_count}"
        )
    if not source.get("strict_acceptance_inherited", False):
        raise ValueError(f"{source['source_id']}: 未声明严格验收继承关系")

    for row in rows:
        stats["input_record_count"] += 1
        record = _aggregate_record(row, source, source_config["build_date"])
        scenario_hash = value_sha256(scenario_identity_payload(record))
        if scenario_hash in accumulators:
            stats["duplicate_record_count"] += 1
        accumulator = accumulators.setdefault(scenario_hash, _new_accumulator(record))
        _register_common(
            accumulator,
            record,
            row["generator"],
            source["risk_method"],
        )
        accumulator["source_refs"].append(
            _aggregate_source_ref(
                project_root,
                source,
                record,
                row,
                dataset_path,
                dataset_sha256,
                merge_summary_path,
                merge_summary_sha256,
            )
        )
        accumulator["aggregate_rows"][row["sample_id"]] = row
        accumulator["aggregate_sensor_statuses"].add(source["sensor_status"])
        accumulator["aggregate_server_statuses"].add(source["server_status"])
        _register_file_ref(
            accumulator,
            "aggregate_dataset",
            project_root,
            dataset_path,
            dataset_sha256,
        )
        _register_file_ref(
            accumulator,
            "merge_summary",
            project_root,
            merge_summary_path,
            merge_summary_sha256,
        )


def collect_source_records(source_config, project_root):
    if source_config.get("format") != "scenario_library_sources_v1":
        raise ValueError("不支持的场景库来源配置格式")
    accumulators = {}
    stats = {
        "input_record_count": 0,
        "excluded_record_count": 0,
        "duplicate_record_count": 0,
        "source_count": len(source_config["sources"]),
    }
    collectors = {
        "run_bundle": _collect_run_bundle_source,
        "aggregate_feedback_dataset": _collect_aggregate_source,
    }
    for source in source_config["sources"]:
        kind = source.get("kind", "run_bundle")
        if kind not in collectors:
            raise ValueError(f"不支持的场景库来源类型: {kind}")
        collectors[kind](source, source_config, project_root, accumulators, stats)
    return accumulators, stats


def _aggregate_risk_metrics(rows):
    repeat_counts = [int(row["repeat_count"]) for row in rows]
    total_count = sum(repeat_counts)
    means = [float(row["observed_risk_score_mean"]) for row in rows]
    score_mean = sum(
        count * mean for count, mean in zip(repeat_counts, means)
    ) / total_count
    variance_numerator = 0.0
    for row, count, mean in zip(rows, repeat_counts, means):
        score_std = float(row["observed_risk_score_std"])
        variance_numerator += (count - 1) * score_std**2
        variance_numerator += count * (mean - score_mean) ** 2
    score_std = (
        math.sqrt(variance_numerator / (total_count - 1))
        if total_count > 1
        else 0.0
    )
    level_counts = Counter()
    for row, count in zip(rows, repeat_counts):
        level_counts[row["observed_risk_level_mode"]] += count
    modal_level = max(
        RISK_LEVELS,
        key=lambda level: (level_counts[level], RISK_LEVELS.index(level)),
    )
    target_match_rate = None
    if all(float(row["observed_risk_level_consistency"]) == 1.0 for row in rows):
        target_match_rate = sum(
            count
            for row, count in zip(rows, repeat_counts)
            if row["observed_risk_level_mode"] == row["target_risk_level"]
        ) / total_count
    collision_run_count = sum(
        int(round(float(row["collision_run_rate"]) * count))
        for row, count in zip(rows, repeat_counts)
    )
    traffic_seeds = sorted(
        {
            int(seed.strip())
            for row in rows
            for seed in row["traffic_manager_seeds"].split(",")
            if seed.strip()
        }
    )
    return {
        "expected_count": total_count,
        "score_mean": score_mean,
        "score_std": score_std,
        "score_min": min(float(row["observed_risk_score_min"]) for row in rows),
        "score_max": max(float(row["observed_risk_score_max"]) for row in rows),
        "modal_level": modal_level,
        "target_match_rate": target_match_rate,
        "collision_run_count": collision_run_count,
        "collision_event_count": sum(
            int(row["collision_event_total"]) for row in rows
        ),
        "minimum_ttc_seconds": min(
            float(row["minimum_ttc_seconds_min"]) for row in rows
        ),
        "minimum_lead_gap_m": min(
            float(row["minimum_lead_gap_m_min"]) for row in rows
        ),
        "minimum_pedestrian_distance_m": min(
            float(row["minimum_pedestrian_distance_m_min"]) for row in rows
        ),
        "traffic_seeds": traffic_seeds,
    }


def _finalize_entry(scenario_hash, accumulator, quality_config):
    record = accumulator["record"]
    expected_runs = list(accumulator["expected_runs"].values())
    rows = list(accumulator["result_rows"].values())
    rows.sort(key=lambda row: row["run_id"])
    aggregate_rows = list(accumulator["aggregate_rows"].values())
    evidence_granularity = "run_level" if rows else "aggregate"
    if rows:
        expected_count = len(expected_runs)
        completed_rows = [row for row in rows if row.get("status") == "completed"]
        accepted_rows = [
            row
            for row in rows
            if row.get("status") == "completed"
            and row.get("acceptance_status") == "completed"
        ]
        if not accepted_rows:
            raise ValueError(f"{record['sample_id']}: 没有可用的严格验收运行")
        completed_count = len(completed_rows)
        accepted_count = len(accepted_rows)
        runtime_verified_count = sum(
            parse_bool(row.get("runtime_verified")) is True for row in rows
        )
        route_verified_count = sum(
            parse_bool(row.get("route_verified")) is True for row in rows
        )
        verification_level = "static_validated"
        if expected_count and completed_count == expected_count:
            verification_level = "runtime_completed"
        if expected_count and accepted_count == expected_count:
            verification_level = "strictly_accepted"
        scores = [float(row["risk_score"]) for row in accepted_rows]
        score_mean = statistics.fmean(scores)
        score_std = statistics.stdev(scores) if len(scores) > 1 else 0.0
        score_min = min(scores)
        score_max = max(scores)
        modal_level = _modal_risk_level(accepted_rows)
        target_matches = [
            parse_bool(row.get("target_match"))
            for row in accepted_rows
            if parse_bool(row.get("target_match")) is not None
        ]
        target_match_rate = (
            statistics.fmean(target_matches) if target_matches else None
        )
        collision_counts = [
            optional_int(row.get("collision_count")) or 0 for row in accepted_rows
        ]
        collision_run_count = sum(count > 0 for count in collision_counts)
        collision_event_count = sum(collision_counts)
        minimum_ttc_seconds = _minimum(accepted_rows, "minimum_ttc_seconds")
        minimum_lead_gap_m = _minimum(accepted_rows, "minimum_lead_gap_m")
        minimum_pedestrian_distance_m = _minimum(
            accepted_rows,
            "minimum_pedestrian_distance_m",
        )
        traffic_seeds = sorted(
            {
                int(row["traffic_manager_seed"])
                for row in rows
                if str(row.get("traffic_manager_seed") or "").strip()
            }
        )
        evidence = evidence_completeness_score(rows)
        sensor_statuses = sorted(
            {row["sensor_status"] for row in rows if row.get("sensor_status")}
        )
        server_statuses = sorted(
            {row["server_status"] for row in rows if row.get("server_status")}
        )
        run_ids = [row["run_id"] for row in rows]
        metadata_paths = sorted(
            {row["metadata_path"] for row in rows if row.get("metadata_path")}
        )
    elif aggregate_rows:
        aggregate_metrics = _aggregate_risk_metrics(aggregate_rows)
        expected_count = aggregate_metrics["expected_count"]
        completed_count = expected_count
        accepted_count = expected_count
        runtime_verified_count = expected_count
        route_verified_count = expected_count
        verification_level = "strictly_accepted"
        score_mean = aggregate_metrics["score_mean"]
        score_std = aggregate_metrics["score_std"]
        score_min = aggregate_metrics["score_min"]
        score_max = aggregate_metrics["score_max"]
        modal_level = aggregate_metrics["modal_level"]
        target_match_rate = aggregate_metrics["target_match_rate"]
        collision_run_count = aggregate_metrics["collision_run_count"]
        collision_event_count = aggregate_metrics["collision_event_count"]
        minimum_ttc_seconds = aggregate_metrics["minimum_ttc_seconds"]
        minimum_lead_gap_m = aggregate_metrics["minimum_lead_gap_m"]
        minimum_pedestrian_distance_m = aggregate_metrics[
            "minimum_pedestrian_distance_m"
        ]
        traffic_seeds = aggregate_metrics["traffic_seeds"]
        evidence = aggregate_evidence_completeness_score()
        sensor_statuses = sorted(accumulator["aggregate_sensor_statuses"])
        server_statuses = sorted(accumulator["aggregate_server_statuses"])
        run_ids = []
        metadata_paths = []
    else:
        raise ValueError(f"{record['sample_id']}: 缺少运行级和聚合级证据")

    executability = accepted_count / expected_count if expected_count else 0.0
    repeatability_reference = float(
        quality_config["repeatability_score_std_reference"]
    )
    repeatability = max(0.0, 1.0 - score_std / repeatability_reference)
    operational_score = statistics.fmean((executability, evidence, repeatability))
    carla_versions = sorted(
        {
            str(version).strip()
            for row in rows
            for version in (
                row.get("carla_client_version"),
                row.get("carla_server_version"),
            )
            if str(version or "").strip()
        }
    )
    flags = ["realism_not_assessed"]
    if not carla_versions:
        flags.append("carla_version_not_recorded")
    if any(str(path).startswith(("F:\\", "D:\\")) for path in metadata_paths):
        flags.append("historical_runtime_paths")
    if evidence_granularity == "aggregate":
        flags.extend(["aggregate_evidence_only", "run_level_evidence_not_embedded"])
    if target_match_rate is not None and target_match_rate < 0.5:
        flags.append("target_condition_mismatch")
    if collision_run_count > 0:
        flags.append("collision_observed")

    aliases = sorted(accumulator["aliases"])
    return {
        "schema_version": "1.0",
        "library_id": f"slv1_{scenario_hash[:16]}",
        "scenario_hash": scenario_hash,
        "canonical_sample_id": aliases[0],
        "aliases": aliases,
        "family": record["family"],
        "parameters": {
            "duration_seconds": float(record["scenario"]["duration_seconds"]),
            "weather": record["weather"],
            "lead_vehicle": record["lead_vehicle"],
            "pedestrian": record["pedestrian"],
        },
        "labels": {
            "target_risk_levels": sorted(
                accumulator["target_risk_levels"],
                key=RISK_LEVELS.index,
            ),
            "observed_risk_level": modal_level,
            "weather_tags": sorted(accumulator["weather_tags"]),
            "hazard_tags": sorted(accumulator["hazard_tags"]),
            "generators": sorted(accumulator["generators"]),
        },
        "provenance": {
            "source_refs": sorted(
                accumulator["source_refs"],
                key=lambda item: (item["source_id"], item["source_record_path"]),
            )
        },
        "execution_evidence": {
            "verification_level": verification_level,
            "evidence_granularity": evidence_granularity,
            "expected_run_count": expected_count,
            "completed_run_count": completed_count,
            "accepted_run_count": accepted_count,
            "runtime_verified_run_count": runtime_verified_count,
            "route_verified_run_count": route_verified_count,
            "acceptance_rate": executability,
            "traffic_manager_seeds": traffic_seeds,
            "carla_versions": carla_versions,
            "sensor_statuses": sensor_statuses,
            "server_statuses": server_statuses,
            "run_ids": run_ids,
            "metadata_paths": metadata_paths,
            "config_refs": [
                accumulator["config_refs"][run_id]
                for run_id in sorted(accumulator["config_refs"])
            ],
            "aggregate_refs": [
                accumulator["aggregate_refs"][key]
                for key in sorted(accumulator["aggregate_refs"])
            ],
        },
        "observed_risk": {
            "methods": sorted(accumulator["risk_methods"]),
            "score_mean": score_mean,
            "score_std": score_std,
            "score_min": score_min,
            "score_max": score_max,
            "modal_level": modal_level,
            "target_match_rate": target_match_rate,
            "high_or_critical": modal_level in {"high", "critical"},
            "collision_observed": collision_run_count > 0,
            "collision_run_count": collision_run_count,
            "collision_event_count": collision_event_count,
            "minimum_ttc_seconds": minimum_ttc_seconds,
            "minimum_lead_gap_m": minimum_lead_gap_m,
            "minimum_pedestrian_distance_m": minimum_pedestrian_distance_m,
        },
        "quality": {
            "assessment_status": "partial",
            "operational_score": operational_score,
            "tier": _quality_tier(executability, evidence, repeatability),
            "executability": {"status": "assessed", "score": executability},
            "evidence_completeness": {"status": "assessed", "score": evidence},
            "repeatability": {
                "status": "assessed",
                "score": repeatability,
                "score_std_reference": repeatability_reference,
            },
            "dangerousness": {"status": "assessed", "score": score_mean / 100.0},
            "diversity": {
                "status": "not_assessed",
                "score": None,
                "nearest_neighbor_distance": None,
                "reference_distance": float(
                    quality_config["diversity_reference_distance"]
                ),
            },
            "realism": {"status": "not_assessed", "score": None},
            "flags": sorted(flags),
        },
        "_normalized_vector": normalized_parameter_vector(record),
    }


def _apply_diversity(entries):
    nearest_distances = {}
    for entry in entries:
        other_distances = [
            normalized_distance(
                entry["_normalized_vector"],
                other["_normalized_vector"],
            )
            for other in entries
            if other is not entry
        ]
        nearest_distances[entry["library_id"]] = (
            min(other_distances) if other_distances else None
        )

    for entry in entries:
        diversity = entry["quality"]["diversity"]
        nearest = nearest_distances[entry["library_id"]]
        if nearest is not None:
            reference = diversity["reference_distance"]
            diversity.update(
                {
                    "status": "assessed",
                    "score": min(1.0, nearest / reference) if reference else 0.0,
                    "nearest_neighbor_distance": nearest,
                }
            )
            if diversity["score"] < 0.25:
                entry["quality"]["flags"].append("low_relative_diversity")
                entry["quality"]["flags"] = sorted(set(entry["quality"]["flags"]))
        entry.pop("_normalized_vector")


def build_library_entries(source_config, schema, project_root):
    accumulators, stats = collect_source_records(source_config, project_root)
    entries = [
        _finalize_entry(scenario_hash, accumulator, source_config["quality"])
        for scenario_hash, accumulator in sorted(accumulators.items())
    ]
    _apply_diversity(entries)
    for entry in entries:
        errors = validate_schema_value(entry, schema)
        if errors:
            raise ValueError(
                f"{entry['canonical_sample_id']}: 场景库 Schema 校验失败\n"
                + "\n".join(errors)
            )
    stats["entry_count"] = len(entries)
    stats["accepted_run_evidence_count"] = sum(
        entry["execution_evidence"]["accepted_run_count"] for entry in entries
    )
    return entries, stats
