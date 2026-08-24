"""Run a reproducible generation-vs-rule baseline benchmark.

The benchmark deliberately keeps the comparison at the parameter-generation
layer.  Both generators use the same Python process, CPU-only execution,
15-dimensional declared ranges, risk-level allocation, record builder and
schema validation.  It does not claim an end-to-end CARLA or road-test result.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.scenario_features import (  # noqa: E402
    FEATURE_NAMES,
    build_generated_record,
    normalize_vector,
)
from tools.generate_seed_dataset import RANGES  # noqa: E402
from tools.generate_with_model import lhs_candidates  # noqa: E402


RISK_LEVELS = ("low", "medium", "high", "critical")
CONTRACT_VERSION = "stage5_generation_same_cpu_v1"


def _uniform_candidates(risk: str, count: int, seed: int) -> np.ndarray:
    rng = random.Random(int(seed))
    values = []
    for _ in range(int(count)):
        row = []
        for name in FEATURE_NAMES:
            short_name = name.split(".", 1)[1]
            low, high = RANGES[risk][short_name]
            row.append(rng.uniform(float(low), float(high)))
        values.append(row)
    return normalize_vector(np.asarray(values, dtype=np.float64), clip=True)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _generate(
    model: str,
    output_path: Path,
    count_per_level: int,
    seed: int,
    repeats: int = 1,
) -> dict:
    elapsed = 0.0
    records = []
    for repeat_index in range(int(repeats)):
        started = perf_counter()
        records = []
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        repeat_seed = int(seed) + repeat_index * 100003
        for level_index, risk in enumerate(RISK_LEVELS):
            level_seed = repeat_seed + level_index * 1009
            if model == "lhs":
                vectors = lhs_candidates(risk, count_per_level, level_seed)
                generator_name = "balanced_latin_hypercube_v1"
            elif model == "uniform_rule":
                vectors = _uniform_candidates(risk, count_per_level, level_seed)
                generator_name = "uniform_rule_parameter_sampling_v1"
            else:
                raise ValueError(f"unsupported model: {model}")
            for index, vector in enumerate(vectors, 1):
                records.append(
                    build_generated_record(
                        vector,
                        risk,
                        [],
                        f"{model}_{risk}_{repeat_seed}_{index:04d}",
                        generator_name,
                        generator_seed=level_seed,
                        source_kind="synthetic_parameter_design",
                        traffic_manager_seed=(level_seed + index) % 2147483648,
                        created_at=created_at,
                    )
                )
        _write_jsonl(output_path, records)
        elapsed += perf_counter() - started
    output_record_count = len(records)
    summary = {
        "format": "stage5_generation_benchmark_summary_v1",
        "model": model,
        "generator": (
            "balanced_latin_hypercube_v1"
            if model == "lhs"
            else "uniform_rule_parameter_sampling_v1"
        ),
        "requested_count": output_record_count * int(repeats),
        "accepted_count": output_record_count * int(repeats),
        "attempted_count": output_record_count * int(repeats),
        "acceptance_rate": 1.0,
        "elapsed_seconds": elapsed,
        "random_seed": int(seed),
        "output": str(output_path.resolve()),
        "measurement_contract": {
            "version": CONTRACT_VERSION,
            "python_executable": sys.executable,
            "cpu_only": True,
            "risk_levels": list(RISK_LEVELS),
            "count_per_level": int(count_per_level),
            "measurement_repeats": int(repeats),
            "output_record_count": output_record_count,
            "feature_names": list(FEATURE_NAMES),
            "declared_ranges": RANGES,
            "record_builder": "core.scenario_features.build_generated_record",
            "schema_validation": "build_generated_record.require_valid_scenario",
            "requested_weather_tags": [],
        },
    }
    summary_path = output_path.with_name(output_path.stem + "_summary.json")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _fixed_template(reference_path: Path, output_path: Path) -> dict:
    """Create a transparent manual-template coverage comparator.

    A conventional rule editor reusing one approved template contributes one
    condition signature to the explicit reference universe.  It is used only
    for coverage comparison, not as the generation-throughput baseline.
    """
    first = next(
        json.loads(line)
        for line in reference_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    template = dict(first)
    template["sample_id"] = "fixed_rule_template_v1"
    template["provenance"] = dict(template["provenance"])
    template["provenance"]["generator"] = "manual_rule_template_v1"
    template["provenance"]["generator_seed"] = 0
    template["provenance"]["created_at"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )
    _write_jsonl(output_path, [template])
    return {
        "format": "stage5_fixed_template_baseline_v1",
        "model": "fixed_rule_template",
        "candidate_count": 1,
        "reference": str(reference_path.resolve()),
        "output": str(output_path.resolve()),
        "coverage_role": "coverage_only",
        "measurement_contract": {
            "version": "stage5_coverage_same_reference_v1",
            "signature_definition": "target_risk_level + sorted weather_tags + sorted hazard_tags",
            "reference_universe": str(reference_path.resolve()),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成阶段五同口径离线 baseline")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--reference",
        default=str(PROJECT_ROOT / "data" / "scenarios" / "seed_v1" / "scenarios.jsonl"),
    )
    parser.add_argument("--count-per-level", type=int, default=512)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260824)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count_per_level < 1:
        raise ValueError("--count-per-level 必须大于 0")
    if args.repeats < 1:
        raise ValueError("--repeats 必须大于 0")
    output_dir = Path(args.output_dir).expanduser().resolve()
    reference = Path(args.reference).expanduser().resolve()
    if not reference.is_file():
        raise FileNotFoundError(reference)
    output_dir.mkdir(parents=True, exist_ok=True)
    lhs = _generate(
        "lhs", output_dir / "system_lhs.jsonl", args.count_per_level, args.seed, args.repeats
    )
    uniform = _generate(
        "uniform_rule",
        output_dir / "baseline_uniform_rule.jsonl",
        args.count_per_level,
        args.seed,
        args.repeats,
    )
    fixed = _fixed_template(reference, output_dir / "baseline_fixed_template.jsonl")
    manifest = {
        "format": "stage5_generation_baseline_manifest_v1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference": str(reference),
        "same_process": True,
        "cpu_only": True,
        "summaries": [lhs, uniform],
        "coverage_baseline": fixed,
    }
    manifest_path = output_dir / "benchmark_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[STAGE5-BASELINE] output={output_dir}")
    print(json.dumps({"lhs": lhs, "uniform_rule": uniform}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
