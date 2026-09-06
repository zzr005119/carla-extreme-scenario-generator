"""Freeze an independent, stratified blind split for the P3.1 checkpoint."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.carla_rl_plan import _plan_digest, build_multiscene_plan, load_multiscene_plan  # noqa: E402
from core.scenario_features import FEATURE_SPECS, build_generated_record  # noqa: E402
from core.scenario_library import scenario_identity_payload, value_sha256  # noqa: E402
from core.scenario_validator import require_valid_scenario  # noqa: E402
from core.adversarial_sampling import load_library_entries  # noqa: E402


DEFAULT_ENTRIES = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "entries.jsonl"
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "manifest.json"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "scenarios"
    / "carla_rl_p3_1_independent_blind_v1"
    / "carla_rl_multiscene_plan_p3_1_blind_v1.json"
)
GENERATOR_STRATA = ("lhs", "gmm", "cvae")
RISK_LEVELS = ("low", "medium", "high", "critical")
RISK_CENTERS = {"low": 0.20, "medium": 0.43, "high": 0.66, "critical": 0.86}
RISK_WIDTHS = {"low": 0.34, "medium": 0.34, "high": 0.30, "critical": 0.24}


def _normalized_vector(record):
    values = []
    for dotted_name, low, high in FEATURE_SPECS:
        value = record
        for part in dotted_name.split("."):
            value = value[part]
        values.append((float(value) - low) / (high - low))
    return np.asarray(values, dtype=float)


def _sample_unit_vector(rng, family, risk, ordinal, total):
    center = RISK_CENTERS[risk]
    width = RISK_WIDTHS[risk]
    if family == "lhs":
        # A seeded, within-stratum Latin-hypercube-like point.
        base = (ordinal + rng.random(15)) / max(total, 1)
        rng.shuffle(base)
        point = center + (base - 0.5) * width
    elif family == "gmm":
        point = rng.normal(center, width / 3.0, size=15)
    else:
        beta = rng.beta(2.0 + center * 4.0, 2.0 + (1.0 - center) * 4.0, size=15)
        point = center + (beta - 0.5) * width
    return np.clip(point, 0.0, 1.0)


def generate_blind_rows(entries, *, seed, per_stratum=2, minimum_distance=0.04):
    """Generate valid records that are independent of the frozen library."""
    existing_vectors = [_normalized_vector(entry["parameters"]) for entry in entries]
    existing_hashes = {str(entry.get("scenario_hash") or "") for entry in entries}
    existing_ids = {str(entry.get("canonical_sample_id") or "") for entry in entries}
    rng = np.random.default_rng(int(seed))
    rows = []
    blind_hashes = set()
    blind_ids = set()
    accepted_distances = []
    total = len(GENERATOR_STRATA) * len(RISK_LEVELS) * int(per_stratum)
    ordinal = 0
    for family in GENERATOR_STRATA:
        for risk in RISK_LEVELS:
            accepted = 0
            attempts = 0
            while accepted < int(per_stratum):
                attempts += 1
                if attempts > 2000:
                    raise RuntimeError(f"盲测场景采样无法满足独立距离约束: {family}/{risk}")
                vector = _sample_unit_vector(
                    rng, family, risk, ordinal + accepted, total
                )
                sample_id = f"blind_{family}_{risk}_{int(seed)}_{ordinal:04d}"
                record = build_generated_record(
                    vector,
                    risk,
                    (),
                    sample_id,
                    f"independent_blind_{family}_v1",
                    int(seed) + ordinal,
                    source_kind="synthetic_parameter_design",
                    traffic_manager_seed=300000000 + int(seed) + ordinal,
                    created_at=f"carla_rl_independent_blind_seed_{int(seed)}",
                )
                require_valid_scenario(record)
                scenario_hash = value_sha256(scenario_identity_payload(record))
                distance = min(
                    float(np.sqrt(np.mean((vector - old) ** 2)))
                    for old in existing_vectors
                )
                if (
                    scenario_hash in existing_hashes
                    or scenario_hash in blind_hashes
                    or sample_id in existing_ids
                    or sample_id in blind_ids
                    or distance < float(minimum_distance)
                ):
                    ordinal += 1
                    continue
                row = {
                    "library_id": f"blindv1_{scenario_hash[:16]}",
                    "canonical_sample_id": sample_id,
                    "scenario_hash": scenario_hash,
                    "split": "blind",
                    "generator": family,
                    "target_risk_level": risk,
                    "record": record,
                }
                rows.append(row)
                blind_hashes.add(scenario_hash)
                blind_ids.add(sample_id)
                accepted_distances.append(distance)
                accepted += 1
                ordinal += 1
    if len(rows) != total:
        raise RuntimeError(f"盲测计划数量错误: {len(rows)} != {total}")
    return rows, {
        "generator_strata": list(GENERATOR_STRATA),
        "target_risk_levels": list(RISK_LEVELS),
        "per_stratum": int(per_stratum),
        "minimum_normalized_distance": float(minimum_distance),
        "accepted_min_normalized_distance": min(accepted_distances),
        "accepted_mean_normalized_distance": float(np.mean(accepted_distances)),
        "generator_seed": int(seed),
        "source_entry_count": len(entries),
        "source_canonical_sample_id_overlap": len(blind_ids & existing_ids),
        "source_scenario_hash_overlap": len(blind_hashes & existing_hashes),
    }


def build_independent_blind_plan(
    entries_path=DEFAULT_ENTRIES,
    manifest_path=DEFAULT_MANIFEST,
    output_path=DEFAULT_OUTPUT,
    *,
    seed=20260906,
    base_plan_seed=20260903,
    per_stratum=2,
    minimum_distance=0.04,
):
    entries = load_library_entries(entries_path)
    base_plan = build_multiscene_plan(
        entries_path,
        manifest_path,
        seed=int(base_plan_seed),
    )
    blind_rows, design = generate_blind_rows(
        entries,
        seed=int(seed),
        per_stratum=int(per_stratum),
        minimum_distance=float(minimum_distance),
    )
    plan = copy.deepcopy(base_plan)
    plan["splits"]["blind"] = blind_rows
    plan["counts"]["blind"] = len(blind_rows)
    plan["strata"]["blind"] = {
        f"{family}__{risk}": int(per_stratum)
        for family in GENERATOR_STRATA
        for risk in RISK_LEVELS
    }
    plan["blind_design"] = design
    plan["blind_design"]["base_plan_seed"] = int(base_plan_seed)
    plan["blind_design"]["plan_format"] = "independent_blind_stratified_v1"
    plan["evidence_kind"] = "offline_frozen_split_with_independent_blind"
    plan["leakage_check"]["blind_canonical_sample_id_overlap"] = design[
        "source_canonical_sample_id_overlap"
    ]
    plan["leakage_check"]["blind_scenario_hash_overlap"] = design[
        "source_scenario_hash_overlap"
    ]
    if plan["leakage_check"]["blind_canonical_sample_id_overlap"] != 0:
        raise ValueError("blind canonical_sample_id 与场景库重叠")
    if plan["leakage_check"]["blind_scenario_hash_overlap"] != 0:
        raise ValueError("blind scenario_hash 与场景库重叠")
    plan["plan_sha256"] = _plan_digest(plan)
    loaded = load_multiscene_plan(_write_plan(output_path, plan))
    return loaded


def _write_plan(output_path, plan):
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def parse_args():
    parser = argparse.ArgumentParser(description="生成 P3.1 独立盲测场景计划")
    parser.add_argument("--entries", default=str(DEFAULT_ENTRIES))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--base-plan-seed", type=int, default=20260903)
    parser.add_argument("--per-stratum", type=int, default=2)
    parser.add_argument("--minimum-distance", type=float, default=0.04)
    return parser.parse_args()


def main():
    args = parse_args()
    plan = build_independent_blind_plan(
        args.entries,
        args.manifest,
        args.output,
        seed=args.seed,
        base_plan_seed=args.base_plan_seed,
        per_stratum=args.per_stratum,
        minimum_distance=args.minimum_distance,
    )
    print(json.dumps({
        "format": plan["format"],
        "plan_sha256": plan["plan_sha256"],
        "counts": plan["counts"],
        "blind_design": plan["blind_design"],
        "output": str(Path(args.output).expanduser().resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
