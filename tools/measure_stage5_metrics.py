"""Measure the stage-five performance metrics without inventing a baseline.

The script reports three explicit proxies:

* generation throughput: accepted records per recorded wall second;
* testing cost proxy: wall seconds per strictly accepted CARLA run;
* condition-signature coverage: candidate signatures divided by a supplied
  reference signature universe.

Relative gains are only calculated when both baseline and system inputs use the
same command and data contract. Missing baseline evidence remains
``not_assessed``.
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FORMAT = "stage5_metrics_baseline_v1"


def _load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def _load_records(path):
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, 1):
                if line.strip():
                    records.append((line_number, json.loads(line)))
        return records
    payload = _load_json(path)
    if isinstance(payload, list):
        return list(enumerate(payload, 1))
    return [(1, payload)]


def _iter_input_paths(paths):
    for value in paths or ():
        path = Path(value).expanduser().resolve()
        if path.is_dir():
            yield from sorted(path.rglob("metadata.json"))
        elif path.is_file():
            yield path
        else:
            raise FileNotFoundError(path)


def _iter_summary_paths(paths):
    for value in paths or ():
        path = Path(value).expanduser().resolve()
        if path.is_dir():
            matches = sorted(path.rglob("*_summary.json"))
            if not matches:
                matches = sorted(path.rglob("training_summary.json"))
            yield from matches
        elif path.is_file():
            yield path
        else:
            raise FileNotFoundError(path)


def _condition_signature(record):
    labels = record.get("labels") or {}
    conditions = record.get("conditions") or {}
    if labels:
        target = labels.get("target_risk_levels") or []
        weather = labels.get("weather_tags") or []
        hazards = labels.get("hazard_tags") or []
    else:
        target = [conditions.get("target_risk_level")]
        weather = conditions.get("weather_tags") or []
        hazards = conditions.get("hazard_tags") or []
    target = tuple(sorted(str(value) for value in target if value))
    weather = tuple(sorted(str(value) for value in weather if value))
    hazards = tuple(sorted(str(value) for value in hazards if value))
    if not target or not weather:
        return None
    return target, weather, hazards


def condition_coverage(reference_paths, candidate_paths):
    reference = set()
    candidates = set()
    reference_records = 0
    candidate_records = 0
    for path in _iter_input_paths(reference_paths):
        for _, record in _load_records(path):
            reference_records += 1
            signature = _condition_signature(record)
            if signature:
                reference.add(signature)
    for path in _iter_input_paths(candidate_paths):
        for _, record in _load_records(path):
            candidate_records += 1
            signature = _condition_signature(record)
            if signature:
                candidates.add(signature)
    covered = reference & candidates
    return {
        "status": "measured" if reference else "not_assessed",
        "reference_record_count": reference_records,
        "candidate_record_count": candidate_records,
        "reference_signature_count": len(reference),
        "candidate_signature_count": len(candidates),
        "covered_signature_count": len(covered),
        "coverage_rate": (len(covered) / len(reference)) if reference else None,
        "signature_definition": "target_risk_level + sorted weather_tags + sorted hazard_tags",
    }


def generation_throughput(paths):
    summaries = [_load_json(path) for path in _iter_summary_paths(paths)]
    accepted = sum(int(item.get("accepted_count", 0)) for item in summaries)
    attempted = sum(int(item.get("attempted_count", 0)) for item in summaries)
    elapsed = sum(float(item.get("elapsed_seconds", 0.0)) for item in summaries)
    return {
        "status": "measured" if summaries and elapsed > 0 else "not_assessed",
        "summary_count": len(summaries),
        "accepted_count": accepted,
        "attempted_count": attempted,
        "elapsed_seconds": round(elapsed, 6),
        "accepted_records_per_second": round(accepted / elapsed, 6) if elapsed > 0 else None,
        "acceptance_rate": round(accepted / attempted, 6) if attempted > 0 else None,
        "measurement_definition": "sum(accepted_count) / sum(elapsed_seconds)",
    }


def _strict_acceptance(metadata):
    result = metadata.get("result") or {}
    sensor = metadata.get("sensor_pipeline") or {}
    health = metadata.get("server_health") or {}
    route = metadata.get("route_control") or {}
    if result.get("status") != "completed":
        return False
    if sensor.get("status") != "completed":
        return False
    if health.get("status") != "healthy":
        return False
    if metadata.get("cleanup", {}).get("status") != "completed":
        return False
    if route.get("enabled"):
        if route.get("status") != "completed":
            return False
        if min(
            float(route.get("ego_on_route_rate", 0.0)),
            float(route.get("lead_on_route_rate", 0.0)),
            float(route.get("both_on_route_rate", 0.0)),
        ) < 1.0:
            return False
    versions = metadata.get("carla_versions") or {}
    return versions.get("match") is True


def testing_cost(paths):
    records = [_load_json(path) for path in _iter_input_paths(paths)]
    wall_seconds = []
    strict_count = 0
    completed_count = 0
    for metadata in records:
        result = metadata.get("result") or {}
        if result.get("status") == "completed":
            completed_count += 1
        if _strict_acceptance(metadata):
            strict_count += 1
            value = result.get("wall_duration_seconds")
            if value is not None:
                wall_seconds.append(float(value))
    total = sum(wall_seconds)
    return {
        "status": "measured" if wall_seconds else "not_assessed",
        "metadata_count": len(records),
        "completed_count": completed_count,
        "strictly_accepted_count": strict_count,
        "wall_duration_seconds_total": round(total, 6),
        "wall_duration_seconds_mean": round(statistics.mean(wall_seconds), 6) if wall_seconds else None,
        "wall_duration_seconds_median": round(statistics.median(wall_seconds), 6) if wall_seconds else None,
        "cost_proxy_definition": "wall_duration_seconds per strictly accepted run; not monetary cost",
        "acceptance_definition": "completed result + sensor completed + healthy CARLA + cleanup completed + matching 0.9.16 versions + route gate when enabled",
    }


def _comparison(system, baseline, *, higher_is_better):
    if not system or not baseline:
        return {"status": "not_assessed", "reason": "baseline or system measurement missing"}
    if system is None or baseline is None:
        return {"status": "not_assessed", "reason": "measurement missing"}
    current = system.get("accepted_records_per_second") if higher_is_better else system.get("wall_duration_seconds_mean")
    previous = baseline.get("accepted_records_per_second") if higher_is_better else baseline.get("wall_duration_seconds_mean")
    if current is None or previous in (None, 0):
        return {"status": "not_assessed", "reason": "comparable numeric values missing"}
    ratio = current / previous
    return {
        "status": "measured",
        "system_value": current,
        "baseline_value": previous,
        "system_to_baseline_ratio": round(ratio, 6),
        "relative_change": round(ratio - 1.0, 6),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="建立阶段五成本、效率和覆盖率基线")
    parser.add_argument("--generation-summary", action="append", default=[])
    parser.add_argument("--baseline-generation-summary", action="append", default=[])
    parser.add_argument("--metadata", action="append", default=[])
    parser.add_argument("--baseline-metadata", action="append", default=[])
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--baseline-candidate", action="append", default=[])
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    system_generation = generation_throughput(args.generation_summary) if args.generation_summary else None
    baseline_generation = generation_throughput(args.baseline_generation_summary) if args.baseline_generation_summary else None
    system_testing = testing_cost(args.metadata) if args.metadata else None
    baseline_testing = testing_cost(args.baseline_metadata) if args.baseline_metadata else None
    system_coverage = condition_coverage(args.reference, args.candidate) if args.reference and args.candidate else None
    baseline_coverage = condition_coverage(args.reference, args.baseline_candidate) if args.reference and args.baseline_candidate else None
    payload = {
        "format": OUTPUT_FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_metrics": {
            "testing_cost_reduction": "not_assessed_until_same_unit_baseline",
            "generation_efficiency_gain": "not_assessed_until_same_command_baseline",
            "extreme_scene_coverage": "not_assessed_until_reference_universe_is_explicit",
        },
        "system": {
            "generation": system_generation,
            "testing": system_testing,
            "coverage": system_coverage,
        },
        "baseline": {
            "generation": baseline_generation,
            "testing": baseline_testing,
            "coverage": baseline_coverage,
        },
        "comparisons": {
            "generation_efficiency": _comparison(system_generation, baseline_generation, higher_is_better=True),
            "testing_cost_proxy": _comparison(
                system_testing,
                baseline_testing,
                higher_is_better=False,
            ),
            "coverage": (
                {
                    "status": "measured",
                    "system_rate": system_coverage.get("coverage_rate"),
                    "baseline_rate": baseline_coverage.get("coverage_rate"),
                    "absolute_change": round(system_coverage["coverage_rate"] - baseline_coverage["coverage_rate"], 6),
                }
                if system_coverage and baseline_coverage and system_coverage.get("coverage_rate") is not None and baseline_coverage.get("coverage_rate") is not None
                else {"status": "not_assessed", "reason": "baseline or system coverage missing"}
            ),
        },
        "claims_boundary": [
            "wall_duration_seconds is a reproducible execution-time proxy, not monetary cost",
            "coverage is over the explicitly supplied reference condition signatures, not real-world road coverage",
            "no target percentage or multiplier is declared without a same-denominator baseline",
        ],
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[METRICS] report={output}")
    print(json.dumps(payload["comparisons"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
