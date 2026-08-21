"""Scenario-library sampling for adversarial environment resets."""

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from core.scenario_features import condition_text_zh
from core.scenario_validator import require_valid_scenario


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY_PATH = (
    PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "entries.jsonl"
)
DEFAULT_MANIFEST_PATH = (
    PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "manifest.json"
)
DEFAULT_SAMPLER_SEED = 20260821


class ScenarioSamplingError(ValueError):
    """Raised when the library cannot satisfy a sampling request."""


def load_library_entries(path=DEFAULT_LIBRARY_PATH):
    entries = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ScenarioSamplingError(
                    f"{path}:{line_number}: JSON parse failed: {exc}"
                ) from exc
    if not entries:
        raise ScenarioSamplingError(f"scenario library is empty: {path}")
    return entries


def _single_label(entry, field):
    values = entry["labels"][field]
    if len(values) != 1:
        raise ScenarioSamplingError(
            f"{entry.get('library_id')}: labels.{field} must contain one value"
        )
    return values[0]


def _fallback_generator_seed(entry):
    for source in entry.get("provenance", {}).get("source_refs", []):
        value = source.get("generator_seed")
        if isinstance(value, int) and value >= 0:
            return value
    digest = str(entry.get("scenario_hash") or entry["library_id"])
    return int(hashlib.sha256(digest.encode("utf-8")).hexdigest()[:8], 16)


def library_entry_to_record(entry, traffic_manager_seed, created_at):
    """Convert a library entry back to the generated-scenario runtime contract."""
    target_risk_level = _single_label(entry, "target_risk_levels")
    generator = _single_label(entry, "generators")
    weather_tags = list(entry["labels"]["weather_tags"])
    parameters = entry["parameters"]
    record = {
        "schema_version": "1.0",
        "sample_id": entry["canonical_sample_id"],
        "family": entry["family"],
        "conditions": {
            "target_risk_level": target_risk_level,
            "weather_tags": weather_tags,
            "hazard_tags": list(entry["labels"]["hazard_tags"]),
            "condition_text_zh": condition_text_zh(
                target_risk_level,
                weather_tags,
            ),
        },
        "scenario": {
            "duration_seconds": float(parameters["duration_seconds"]),
            "traffic_manager_seed": int(traffic_manager_seed),
        },
        "weather": copy.deepcopy(parameters["weather"]),
        "lead_vehicle": copy.deepcopy(parameters["lead_vehicle"]),
        "pedestrian": copy.deepcopy(parameters["pedestrian"]),
        "observed_risk": {
            "status": "not_simulated",
            "method": None,
            "score": None,
            "level": None,
            "run_dir": None,
        },
        "provenance": {
            "source_kind": "real_carla_run",
            "generator": generator,
            "generator_seed": _fallback_generator_seed(entry),
            "split": "inference",
            "created_at": str(created_at),
        },
    }
    require_valid_scenario(record)
    return record


def _option_values(options, name):
    value = options.get(name)
    if value is None:
        return None
    if isinstance(value, str):
        return (value,)
    try:
        values = tuple(str(item) for item in value)
    except TypeError as exc:
        raise ScenarioSamplingError(f"{name} must be a string or sequence") from exc
    return values or None


def _matches_tags(actual, requested, mode):
    if requested is None:
        return True
    actual = set(actual)
    requested = set(requested)
    if mode == "all":
        return requested.issubset(actual)
    if mode == "any":
        return bool(requested & actual)
    raise ScenarioSamplingError("tag match mode must be 'all' or 'any'")


class ScenarioLibrarySampler:
    """Balanced generator/risk sampler with tag and traffic-seed coverage."""

    def __init__(
        self,
        entries_path=DEFAULT_LIBRARY_PATH,
        manifest_path=DEFAULT_MANIFEST_PATH,
        seed=DEFAULT_SAMPLER_SEED,
    ):
        self.entries_path = Path(entries_path).resolve()
        self.manifest_path = Path(manifest_path).resolve()
        self.entries = load_library_entries(self.entries_path)
        with self.manifest_path.open("r", encoding="utf-8") as file:
            self.manifest = json.load(file)
        expected = int(self.manifest.get("entry_count", 0))
        if expected and expected != len(self.entries):
            raise ScenarioSamplingError(
                f"library entry count mismatch: {len(self.entries)} != {expected}"
            )
        self.default_seed = int(seed)
        self._sequence_seed = None
        self._option_signature = None
        self._rng = None
        self._stratum_order = []
        self._stratum_cursor = 0
        self._selection_index = 0
        self._entry_counts = Counter()
        self._weather_counts = Counter()
        self._hazard_counts = Counter()
        self._traffic_seed_counts = Counter()
        self._entry_seed_counts = Counter()

    @staticmethod
    def _normalized_options(options):
        options = dict(options or {})
        normalized = {
            "generators": _option_values(options, "generators"),
            "target_risk_levels": _option_values(options, "target_risk_levels"),
            "weather_tags": _option_values(options, "weather_tags"),
            "hazard_tags": _option_values(options, "hazard_tags"),
            "weather_match": str(options.get("weather_match", "all")),
            "hazard_match": str(options.get("hazard_match", "all")),
        }
        if normalized["weather_match"] not in {"all", "any"}:
            raise ScenarioSamplingError("weather_match must be 'all' or 'any'")
        if normalized["hazard_match"] not in {"all", "any"}:
            raise ScenarioSamplingError("hazard_match must be 'all' or 'any'")
        return normalized

    @staticmethod
    def _signature(options):
        return json.dumps(options, sort_keys=True, separators=(",", ":"))

    def _eligible_entries(self, options):
        generators = set(options["generators"] or ())
        risks = set(options["target_risk_levels"] or ())
        eligible = []
        for entry in self.entries:
            generator = _single_label(entry, "generators")
            risk = _single_label(entry, "target_risk_levels")
            if generators and generator not in generators:
                continue
            if risks and risk not in risks:
                continue
            if not _matches_tags(
                entry["labels"]["weather_tags"],
                options["weather_tags"],
                options["weather_match"],
            ):
                continue
            if not _matches_tags(
                entry["labels"]["hazard_tags"],
                options["hazard_tags"],
                options["hazard_match"],
            ):
                continue
            eligible.append(entry)
        if not eligible:
            raise ScenarioSamplingError("no scenario-library entries match the filters")
        return eligible

    def _reset_sequence(self, seed, option_signature, eligible):
        self._sequence_seed = int(seed)
        self._option_signature = option_signature
        self._rng = np.random.default_rng(self._sequence_seed)
        self._stratum_order = []
        self._stratum_cursor = 0
        self._selection_index = 0
        self._entry_counts.clear()
        self._weather_counts.clear()
        self._hazard_counts.clear()
        self._traffic_seed_counts.clear()
        self._entry_seed_counts.clear()
        self._start_stratum_cycle(eligible)

    def _start_stratum_cycle(self, eligible):
        strata = sorted(
            {
                (
                    _single_label(entry, "generators"),
                    _single_label(entry, "target_risk_levels"),
                )
                for entry in eligible
            }
        )
        order = self._rng.permutation(len(strata)).tolist()
        self._stratum_order = [strata[index] for index in order]
        self._stratum_cursor = 0

    def _select_entry(self, eligible, stratum):
        candidates = [
            entry
            for entry in eligible
            if (
                _single_label(entry, "generators"),
                _single_label(entry, "target_risk_levels"),
            )
            == stratum
        ]
        minimum_uses = min(self._entry_counts[entry["library_id"]] for entry in candidates)
        candidates = [
            entry
            for entry in candidates
            if self._entry_counts[entry["library_id"]] == minimum_uses
        ]

        def tag_load(entry):
            weather = sum(
                self._weather_counts[tag] for tag in entry["labels"]["weather_tags"]
            )
            hazard = sum(
                self._hazard_counts[tag] for tag in entry["labels"]["hazard_tags"]
            )
            return weather + hazard

        minimum_tag_load = min(tag_load(entry) for entry in candidates)
        candidates = [entry for entry in candidates if tag_load(entry) == minimum_tag_load]
        candidates.sort(key=lambda entry: entry["library_id"])
        return candidates[int(self._rng.integers(0, len(candidates)))]

    def _select_traffic_seed(self, entry):
        seeds = sorted(entry["execution_evidence"]["traffic_manager_seeds"])
        minimum = min(
            (
                self._entry_seed_counts[(entry["library_id"], seed)],
                self._traffic_seed_counts[seed],
            )
            for seed in seeds
        )
        candidates = [
            seed
            for seed in seeds
            if (
                self._entry_seed_counts[(entry["library_id"], seed)],
                self._traffic_seed_counts[seed],
            )
            == minimum
        ]
        return int(candidates[int(self._rng.integers(0, len(candidates)))])

    def __call__(self, seed=None, options=None):
        normalized_options = self._normalized_options(options)
        signature = self._signature(normalized_options)
        eligible = self._eligible_entries(normalized_options)
        if seed is not None:
            self._reset_sequence(int(seed), signature, eligible)
        elif self._rng is None or signature != self._option_signature:
            self._reset_sequence(self.default_seed, signature, eligible)
        elif self._stratum_cursor >= len(self._stratum_order):
            self._start_stratum_cycle(eligible)

        stratum = self._stratum_order[self._stratum_cursor]
        self._stratum_cursor += 1
        entry = self._select_entry(eligible, stratum)
        traffic_seed = self._select_traffic_seed(entry)
        record = library_entry_to_record(
            entry,
            traffic_manager_seed=traffic_seed,
            created_at=self.manifest.get("build_date", "scenario_library_v1"),
        )

        self._entry_counts[entry["library_id"]] += 1
        self._weather_counts.update(entry["labels"]["weather_tags"])
        self._hazard_counts.update(entry["labels"]["hazard_tags"])
        self._traffic_seed_counts[traffic_seed] += 1
        self._entry_seed_counts[(entry["library_id"], traffic_seed)] += 1
        sampling_info = {
            "source": "scenario_library_v1",
            "library_id": entry["library_id"],
            "canonical_sample_id": entry["canonical_sample_id"],
            "generator": stratum[0],
            "target_risk_level": stratum[1],
            "weather_tags": list(entry["labels"]["weather_tags"]),
            "hazard_tags": list(entry["labels"]["hazard_tags"]),
            "traffic_manager_seed": traffic_seed,
            "sequence_seed": self._sequence_seed,
            "selection_index": self._selection_index,
            "eligible_entry_count": len(eligible),
            "historical_observed_risk": {
                "score_mean": entry["observed_risk"]["score_mean"],
                "modal_level": entry["observed_risk"]["modal_level"],
                "collision_observed": entry["observed_risk"]["collision_observed"],
            },
        }
        self._selection_index += 1
        return record, sampling_info

    def coverage_snapshot(self):
        return {
            "selection_count": self._selection_index,
            "entry_counts": dict(sorted(self._entry_counts.items())),
            "weather_tag_counts": dict(sorted(self._weather_counts.items())),
            "hazard_tag_counts": dict(sorted(self._hazard_counts.items())),
            "traffic_manager_seed_counts": {
                str(key): value
                for key, value in sorted(self._traffic_seed_counts.items())
            },
        }
