"""Controlled, read-only scenario-library query contract.

The query surface deliberately accepts structured fields and a whitelist-based
keyword search. It does not interpret free-form natural-language requests.
"""

from dataclasses import dataclass
import re


RISK_LEVELS = ("low", "medium", "high", "critical")
EVIDENCE_GRANULARITIES = ("run_level", "aggregate")
VERIFICATION_BASES = ("direct_run_evidence", "inherited_batch_acceptance")
QUALITY_TIERS = ("bronze", "silver", "gold")
SORT_MODES = ("risk_desc", "risk_asc", "diversity_desc", "quality_desc", "sample_id")


def _split_values(value):
    if value is None:
        return ()
    if isinstance(value, (tuple, list, set)):
        values = value
    else:
        values = re.split(r"[,，\s]+", str(value))
    return tuple(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _optional_float(value, name):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数字") from exc


def _one_of(value, allowed, name):
    if value in (None, ""):
        return None
    value = str(value).strip()
    if value not in allowed:
        raise ValueError(f"{name} 不支持: {value}")
    return value


def _optional_collision(value):
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized in {"yes", "true", "1", "on"}:
        return True
    if normalized in {"no", "false", "0", "off"}:
        return False
    raise ValueError("collision 必须是 yes 或 no")


@dataclass(frozen=True)
class QuerySpec:
    generator: str | None = None
    target_risk: str | None = None
    observed_risk: str | None = None
    collision: bool | None = None
    evidence_granularity: str | None = None
    verification_basis: str | None = None
    carla_version: str | None = None
    quality_tier: str | None = None
    weather_tags: tuple[str, ...] = ()
    hazard_tags: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    min_score: float | None = None
    max_score: float | None = None
    min_diversity: float | None = None


def spec_from_mapping(mapping):
    """Build and validate a spec from CLI/API-like scalar or list values."""
    keyword_values = _split_values(
        mapping.get("keyword", mapping.get("keywords"))
    )
    return QuerySpec(
        generator=(str(mapping.get("generator")).strip() if mapping.get("generator") else None),
        target_risk=_one_of(mapping.get("target_risk", mapping.get("target-risk")), RISK_LEVELS, "target_risk"),
        observed_risk=_one_of(mapping.get("observed_risk", mapping.get("observed-risk")), RISK_LEVELS, "observed_risk"),
        collision=_optional_collision(mapping.get("collision")),
        evidence_granularity=_one_of(
            mapping.get("evidence_granularity", mapping.get("evidence-granularity")),
            EVIDENCE_GRANULARITIES,
            "evidence_granularity",
        ),
        verification_basis=_one_of(
            mapping.get("verification_basis", mapping.get("verification-basis")),
            VERIFICATION_BASES,
            "verification_basis",
        ),
        carla_version=(str(mapping.get("carla_version", mapping.get("carla-version"))).strip()
                       if mapping.get("carla_version", mapping.get("carla-version")) else None),
        quality_tier=_one_of(
            mapping.get("quality_tier", mapping.get("quality-tier")),
            QUALITY_TIERS,
            "quality_tier",
        ),
        weather_tags=_split_values(mapping.get("weather_tag", mapping.get("weather_tags"))),
        hazard_tags=_split_values(mapping.get("hazard_tag", mapping.get("hazard_tags"))),
        keywords=tuple(item.lower() for item in keyword_values),
        min_score=_optional_float(mapping.get("min_score", mapping.get("min-score")), "min_score"),
        max_score=_optional_float(mapping.get("max_score", mapping.get("max-score")), "max_score"),
        min_diversity=_optional_float(
            mapping.get("min_diversity", mapping.get("min-diversity")),
            "min_diversity",
        ),
    )


def _search_text(entry):
    labels = entry["labels"]
    evidence = entry["execution_evidence"]
    risk = entry["observed_risk"]
    quality = entry["quality"]
    values = [
        entry.get("library_id"),
        entry.get("canonical_sample_id"),
        *labels.get("generators", ()),
        *labels.get("target_risk_levels", ()),
        *labels.get("weather_tags", ()),
        *labels.get("hazard_tags", ()),
        labels.get("observed_risk_level"),
        evidence.get("verification_basis"),
        evidence.get("evidence_granularity"),
        quality.get("tier"),
        "collision" if risk.get("collision_observed") else "no_collision",
    ]
    return " ".join(str(value) for value in values if value is not None).lower()


def matches(entry, spec):
    labels = entry["labels"]
    evidence = entry["execution_evidence"]
    risk = entry["observed_risk"]
    quality = entry["quality"]
    if spec.generator and spec.generator not in labels["generators"]:
        return False
    if spec.target_risk and spec.target_risk not in labels["target_risk_levels"]:
        return False
    if spec.observed_risk and spec.observed_risk != labels["observed_risk_level"]:
        return False
    if spec.collision is not None and bool(risk["collision_observed"]) != spec.collision:
        return False
    if spec.evidence_granularity and spec.evidence_granularity != evidence["evidence_granularity"]:
        return False
    if spec.verification_basis and spec.verification_basis != evidence["verification_basis"]:
        return False
    if spec.carla_version:
        versions = evidence["carla_versions"]
        if spec.carla_version == "unknown":
            if versions:
                return False
        elif spec.carla_version not in versions:
            return False
    if spec.quality_tier and spec.quality_tier != quality["tier"]:
        return False
    if not set(spec.weather_tags).issubset(labels["weather_tags"]):
        return False
    if not set(spec.hazard_tags).issubset(labels["hazard_tags"]):
        return False
    if spec.min_score is not None and risk["score_mean"] < spec.min_score:
        return False
    if spec.max_score is not None and risk["score_mean"] > spec.max_score:
        return False
    diversity_score = quality["diversity"]["score"]
    if spec.min_diversity is not None and (
        diversity_score is None or diversity_score < spec.min_diversity
    ):
        return False
    search_text = _search_text(entry)
    return all(keyword in search_text for keyword in spec.keywords)


def sort_entries(entries, mode):
    if mode not in SORT_MODES:
        raise ValueError(f"sort 不支持: {mode}")
    key_functions = {
        "risk_desc": lambda entry: (-entry["observed_risk"]["score_mean"], entry["library_id"]),
        "risk_asc": lambda entry: (entry["observed_risk"]["score_mean"], entry["library_id"]),
        "diversity_desc": lambda entry: (
            -(entry["quality"]["diversity"]["score"] or 0.0),
            entry["library_id"],
        ),
        "quality_desc": lambda entry: (
            -entry["quality"]["operational_score"],
            entry["library_id"],
        ),
        "sample_id": lambda entry: entry["canonical_sample_id"],
    }
    return sorted(entries, key=key_functions[mode])


def query_entries(entries, spec, sort="risk_desc", limit=20):
    if limit < 0:
        raise ValueError("limit 不能小于 0")
    matched = sort_entries([entry for entry in entries if matches(entry, spec)], sort)
    return matched if limit == 0 else matched[:limit]
