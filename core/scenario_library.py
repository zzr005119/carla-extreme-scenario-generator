"""极端场景库条目构建、哈希去重和质量评估。"""

import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath

from core.scenario_features import FEATURE_SPECS
from core.scenario_validator import require_valid_scenario, validate_schema_value


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
        "config_refs": {},
        "risk_methods": set(),
    }


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

    for source in source_config["sources"]:
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

            payload = scenario_identity_payload(record)
            scenario_hash = value_sha256(payload)
            if scenario_hash in accumulators:
                stats["duplicate_record_count"] += 1
            accumulator = accumulators.setdefault(
                scenario_hash,
                _new_accumulator(record),
            )
            generator = _source_generator(planned_runs, record)
            accumulator["aliases"].add(sample_id)
            accumulator["target_risk_levels"].add(
                record["conditions"]["target_risk_level"]
            )
            accumulator["weather_tags"].update(record["conditions"]["weather_tags"])
            accumulator["hazard_tags"].update(record["conditions"]["hazard_tags"])
            accumulator["generators"].add(generator)
            accumulator["risk_methods"].add(source["risk_method"])
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
            for run in planned_runs:
                accumulator["expected_runs"][run["run_id"]] = run
                accumulator["config_refs"][run["run_id"]] = _config_ref(
                    project_root,
                    source_dir,
                    run,
                )
            for row in actual_rows:
                accumulator["result_rows"][row["run_id"]] = row
    return accumulators, stats


def _finalize_entry(scenario_hash, accumulator, quality_config):
    record = accumulator["record"]
    expected_runs = list(accumulator["expected_runs"].values())
    rows = list(accumulator["result_rows"].values())
    rows.sort(key=lambda row: row["run_id"])
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
    modal_level = _modal_risk_level(accepted_rows)
    target_matches = [
        parse_bool(row.get("target_match"))
        for row in accepted_rows
        if parse_bool(row.get("target_match")) is not None
    ]
    collision_counts = [optional_int(row.get("collision_count")) or 0 for row in accepted_rows]
    executability = accepted_count / expected_count if expected_count else 0.0
    evidence = evidence_completeness_score(rows)
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
    if any(str(row.get("metadata_path") or "").startswith(("F:\\", "D:\\")) for row in rows):
        flags.append("historical_runtime_paths")
    if target_matches and statistics.fmean(target_matches) < 0.5:
        flags.append("target_condition_mismatch")
    if any(count > 0 for count in collision_counts):
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
            "expected_run_count": expected_count,
            "completed_run_count": completed_count,
            "accepted_run_count": accepted_count,
            "runtime_verified_run_count": runtime_verified_count,
            "route_verified_run_count": route_verified_count,
            "acceptance_rate": executability,
            "traffic_manager_seeds": sorted(
                {
                    int(row["traffic_manager_seed"])
                    for row in rows
                    if str(row.get("traffic_manager_seed") or "").strip()
                }
            ),
            "carla_versions": carla_versions,
            "sensor_statuses": sorted(
                {row["sensor_status"] for row in rows if row.get("sensor_status")}
            ),
            "server_statuses": sorted(
                {row["server_status"] for row in rows if row.get("server_status")}
            ),
            "run_ids": [row["run_id"] for row in rows],
            "metadata_paths": sorted(
                {row["metadata_path"] for row in rows if row.get("metadata_path")}
            ),
            "config_refs": [
                accumulator["config_refs"][run_id]
                for run_id in sorted(accumulator["config_refs"])
            ],
        },
        "observed_risk": {
            "methods": sorted(accumulator["risk_methods"]),
            "score_mean": score_mean,
            "score_std": score_std,
            "score_min": min(scores),
            "score_max": max(scores),
            "modal_level": modal_level,
            "target_match_rate": statistics.fmean(target_matches) if target_matches else 0.0,
            "high_or_critical": modal_level in {"high", "critical"},
            "collision_observed": any(count > 0 for count in collision_counts),
            "collision_run_count": sum(count > 0 for count in collision_counts),
            "collision_event_count": sum(collision_counts),
            "minimum_ttc_seconds": _minimum(accepted_rows, "minimum_ttc_seconds"),
            "minimum_lead_gap_m": _minimum(accepted_rows, "minimum_lead_gap_m"),
            "minimum_pedestrian_distance_m": _minimum(
                accepted_rows,
                "minimum_pedestrian_distance_m",
            ),
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
