"""生成场景库 V1 的质量分析基线、审查表和可复用图表。"""

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import matplotlib
import numpy as np


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENTRIES = (
    PROJECT_ROOT
    / "data"
    / "scenarios"
    / "scenario_library_v1"
    / "entries.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "scenarios"
    / "scenario_library_v1"
    / "quality_analysis_v1"
)
RISK_LEVELS = ("low", "medium", "high", "critical")
RISK_INDEX = {level: index for index, level in enumerate(RISK_LEVELS)}
GENERATOR_COLORS = {
    "lhs": "#0072B2",
    "gmm": "#E69F00",
    "cvae": "#009E73",
}


def parse_args():
    parser = argparse.ArgumentParser(description="分析极端场景库 V1 的质量基线")
    parser.add_argument("--entries", default=str(DEFAULT_ENTRIES))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def load_entries(path):
    entries = []
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: JSON 解析失败") from exc
    if not entries:
        raise ValueError("场景库没有可分析条目")
    return entries


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_entries(entries):
    required_sections = (
        "library_id",
        "canonical_sample_id",
        "scenario_hash",
        "labels",
        "observed_risk",
        "execution_evidence",
        "quality",
    )
    library_ids = set()
    scenario_hashes = set()
    for index, entry in enumerate(entries, 1):
        missing = [name for name in required_sections if name not in entry]
        if missing:
            raise ValueError(f"第 {index} 个条目缺少字段: {missing}")
        library_id = entry["library_id"]
        scenario_hash = entry["scenario_hash"]
        if library_id in library_ids:
            raise ValueError(f"重复 library_id: {library_id}")
        if scenario_hash in scenario_hashes:
            raise ValueError(f"重复 scenario_hash: {scenario_hash}")
        library_ids.add(library_id)
        scenario_hashes.add(scenario_hash)
        labels = entry["labels"]
        if not labels["generators"] or not labels["target_risk_levels"]:
            raise ValueError(f"{library_id}: 生成器或目标风险标签为空")
        if labels["observed_risk_level"] not in RISK_INDEX:
            raise ValueError(f"{library_id}: 非法实测风险等级")
        if any(level not in RISK_INDEX for level in labels["target_risk_levels"]):
            raise ValueError(f"{library_id}: 非法目标风险等级")


def safe_mean(values):
    return float(np.mean(values)) if values else None


def safe_std(values):
    return float(np.std(values)) if values else None


def safe_quantiles(values):
    if not values:
        return {"p10": None, "p25": None, "median": None, "p75": None, "p90": None}
    quantiles = np.quantile(np.asarray(values, dtype=float), [0.1, 0.25, 0.5, 0.75, 0.9])
    return {
        "p10": float(quantiles[0]),
        "p25": float(quantiles[1]),
        "median": float(quantiles[2]),
        "p75": float(quantiles[3]),
        "p90": float(quantiles[4]),
    }


def average_ranks(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        average_rank = (cursor + end - 1) / 2.0
        for position in range(cursor, end):
            ranks[order[position]] = average_rank
        cursor = end
    return np.asarray(ranks, dtype=float)


def spearman(values_a, values_b):
    if len(values_a) < 2 or len(values_a) != len(values_b):
        return None
    ranks_a = average_ranks(values_a)
    ranks_b = average_ranks(values_b)
    if np.std(ranks_a) == 0.0 or np.std(ranks_b) == 0.0:
        return None
    return float(np.corrcoef(ranks_a, ranks_b)[0, 1])


def flatten_entry(entry):
    labels = entry["labels"]
    risk = entry["observed_risk"]
    evidence = entry["execution_evidence"]
    quality = entry["quality"]
    target_levels = labels["target_risk_levels"]
    target_indices = [RISK_INDEX[level] for level in target_levels]
    target_index = float(np.mean(target_indices))
    observed_level = labels["observed_risk_level"]
    observed_index = RISK_INDEX[observed_level]
    return {
        "library_id": entry["library_id"],
        "sample_id": entry["canonical_sample_id"],
        "scenario_hash": entry["scenario_hash"],
        "generators": labels["generators"],
        "generator": ";".join(labels["generators"]),
        "target_risk_levels": target_levels,
        "target_risk": ";".join(target_levels),
        "target_index": target_index,
        "observed_risk": observed_level,
        "observed_index": observed_index,
        "risk_gap": observed_index - target_index,
        "target_match": observed_level in target_levels,
        "risk_score_mean": float(risk["score_mean"]),
        "risk_score_std": float(risk["score_std"]),
        "collision_observed": bool(risk["collision_observed"]),
        "collision_run_count": int(risk["collision_run_count"]),
        "accepted_run_count": int(evidence["accepted_run_count"]),
        "verification_basis": evidence["verification_basis"],
        "evidence_granularity": evidence["evidence_granularity"],
        "carla_versions": evidence["carla_versions"],
        "quality_tier": quality["tier"],
        "operational_quality": float(quality["operational_score"]),
        "diversity_score": float(quality["diversity"]["score"]),
        "nearest_neighbor_distance": float(
            quality["diversity"]["nearest_neighbor_distance"]
        ),
        "quality_flags": quality["flags"],
        "quality_flag_text": ";".join(quality["flags"]),
    }


def group_summary(records, generator):
    selected = [record for record in records if generator in record["generators"]]
    scores = [record["risk_score_mean"] for record in selected]
    high_or_critical = sum(
        record["observed_risk"] in ("high", "critical") for record in selected
    )
    collisions = sum(record["collision_observed"] for record in selected)
    target_matches = sum(record["target_match"] for record in selected)
    return {
        "generator": generator,
        "scene_count": len(selected),
        "risk_score_mean": safe_mean(scores),
        "risk_score_std": safe_std(scores),
        "risk_score_min": min(scores) if scores else None,
        "risk_score_max": max(scores) if scores else None,
        "high_or_critical_count": high_or_critical,
        "high_or_critical_rate": high_or_critical / len(selected),
        "collision_scene_count": collisions,
        "collision_scene_rate": collisions / len(selected),
        "target_match_count": target_matches,
        "target_match_rate": target_matches / len(selected),
        "operational_quality_mean": safe_mean(
            [record["operational_quality"] for record in selected]
        ),
        "diversity_score_mean": safe_mean(
            [record["diversity_score"] for record in selected]
        ),
        "low_diversity_count": sum(
            "low_relative_diversity" in record["quality_flags"]
            for record in selected
        ),
        "run_level_count": sum(
            record["evidence_granularity"] == "run_level" for record in selected
        ),
        "aggregate_count": sum(
            record["evidence_granularity"] == "aggregate" for record in selected
        ),
    }


def build_analysis(entries, top_k):
    records = [flatten_entry(entry) for entry in entries]
    generator_names = sorted(
        {generator for record in records for generator in record["generators"]}
    )
    generator_summaries = [
        group_summary(records, generator) for generator in generator_names
    ]
    target_observed_matrix = {
        target: {observed: 0 for observed in RISK_LEVELS} for target in RISK_LEVELS
    }
    for record in records:
        for target in record["target_risk_levels"]:
            target_observed_matrix[target][record["observed_risk"]] += 1
    quality_flags = Counter(
        flag for record in records for flag in record["quality_flags"]
    )
    evidence_counts = Counter(record["evidence_granularity"] for record in records)
    verification_basis_counts = Counter(
        record["verification_basis"] for record in records
    )
    quality_tiers = Counter(record["quality_tier"] for record in records)
    generator_counts = Counter(
        generator for record in records for generator in record["generators"]
    )
    target_counts = Counter(
        target for record in records for target in record["target_risk_levels"]
    )
    observed_counts = Counter(record["observed_risk"] for record in records)
    collision_count = sum(record["collision_observed"] for record in records)
    high_or_critical_count = sum(
        record["observed_risk"] in ("high", "critical") for record in records
    )
    target_match_count = sum(record["target_match"] for record in records)
    all_versions = Counter(
        version for record in records for version in record["carla_versions"]
    )
    unknown_version_count = sum(not record["carla_versions"] for record in records)
    risk_scores = [record["risk_score_mean"] for record in records]
    diversity_scores = [record["diversity_score"] for record in records]
    operational_scores = [record["operational_quality"] for record in records]
    repeatability_stds = [record["risk_score_std"] for record in records]
    sorted_dangerous = sorted(
        records,
        key=lambda record: (
            -record["risk_score_mean"],
            -int(record["collision_observed"]),
            record["sample_id"],
        ),
    )
    sorted_diversity = sorted(
        records,
        key=lambda record: (
            record["nearest_neighbor_distance"],
            record["sample_id"],
        ),
    )
    sorted_operational = sorted(
        records,
        key=lambda record: (
            record["operational_quality"],
            record["sample_id"],
        ),
    )
    mismatches = sorted(
        [record for record in records if not record["target_match"]],
        key=lambda record: (
            -abs(record["risk_gap"]),
            -record["risk_score_mean"],
            record["sample_id"],
        ),
    )
    summary = {
        "format": "scenario_library_quality_analysis_v1",
        "analysis_date": date.today().isoformat(),
        "entry_count": len(records),
        "accepted_run_evidence_count": sum(
            record["accepted_run_count"] for record in records
        ),
        "generator_counts": dict(sorted(generator_counts.items())),
        "target_risk_level_counts": {
            level: target_counts[level] for level in RISK_LEVELS
        },
        "observed_risk_level_counts": {
            level: observed_counts[level] for level in RISK_LEVELS
        },
        "collision_scene_count": collision_count,
        "collision_scene_rate": collision_count / len(records),
        "high_or_critical_scene_count": high_or_critical_count,
        "high_or_critical_scene_rate": high_or_critical_count / len(records),
        "target_match_count": target_match_count,
        "target_match_rate": target_match_count / len(records),
        "target_score_spearman": spearman(
            [record["target_index"] for record in records],
            risk_scores,
        ),
        "target_observed_level_spearman": spearman(
            [record["target_index"] for record in records],
            [record["observed_index"] for record in records],
        ),
        "risk_score": {
            "mean": safe_mean(risk_scores),
            "std": safe_std(risk_scores),
            "quantiles": safe_quantiles(risk_scores),
        },
        "operational_quality": {
            "mean": safe_mean(operational_scores),
            "std": safe_std(operational_scores),
            "quantiles": safe_quantiles(operational_scores),
        },
        "diversity": {
            "mean": safe_mean(diversity_scores),
            "std": safe_std(diversity_scores),
            "quantiles": safe_quantiles(diversity_scores),
            "low_relative_diversity_count": quality_flags[
                "low_relative_diversity"
            ],
        },
        "repeatability_risk_score_std": {
            "mean": safe_mean(repeatability_stds),
            "maximum": max(repeatability_stds),
            "quantiles": safe_quantiles(repeatability_stds),
        },
        "evidence_granularity_counts": dict(sorted(evidence_counts.items())),
        "verification_basis_counts": dict(
            sorted(verification_basis_counts.items())
        ),
        "quality_tier_counts": dict(sorted(quality_tiers.items())),
        "carla_version_counts": dict(sorted(all_versions.items())),
        "carla_version_unknown_count": unknown_version_count,
        "realism_not_assessed_count": quality_flags["realism_not_assessed"],
        "quality_flag_counts": dict(sorted(quality_flags.items())),
        "generator_summaries": generator_summaries,
        "target_observed_matrix": target_observed_matrix,
        "top_dangerous": sorted_dangerous[:top_k],
        "lowest_diversity": sorted_diversity[:top_k],
        "lowest_operational_quality": sorted_operational[:top_k],
        "largest_target_mismatches": mismatches[:top_k],
    }
    return records, summary


def write_csv(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_scenario_index(path, records):
    fieldnames = (
        "library_id",
        "sample_id",
        "generator",
        "target_risk",
        "observed_risk",
        "risk_score_mean",
        "risk_score_std",
        "risk_gap",
        "target_match",
        "collision_observed",
        "collision_run_count",
        "accepted_run_count",
        "verification_basis",
        "evidence_granularity",
        "quality_tier",
        "operational_quality",
        "diversity_score",
        "nearest_neighbor_distance",
        "quality_flag_text",
    )
    rows = [{field: record[field] for field in fieldnames} for record in records]
    write_csv(path, fieldnames, rows)


def write_generator_summary(path, summaries):
    fieldnames = tuple(summaries[0].keys())
    write_csv(path, fieldnames, summaries)


def write_target_matrix(path, matrix):
    fieldnames = ("target_risk", *RISK_LEVELS, "total")
    rows = []
    for target in RISK_LEVELS:
        row = {"target_risk": target, **matrix[target]}
        row["total"] = sum(matrix[target].values())
        rows.append(row)
    write_csv(path, fieldnames, rows)


def write_quality_flags(path, flag_counts, entry_count):
    rows = [
        {
            "quality_flag": flag,
            "scene_count": count,
            "scene_rate": count / entry_count,
        }
        for flag, count in sorted(
            flag_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    write_csv(path, ("quality_flag", "scene_count", "scene_rate"), rows)


def configure_plot_style():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "svg.hashsalt": "scenario-library-v1",
        }
    )


def plot_quality_overview(path_png, path_svg, records, summary):
    configure_plot_style()
    figure, axes = plt.subplots(2, 2, figsize=(11.0, 8.0))
    generator_names = [item["generator"] for item in summary["generator_summaries"]]
    box_values = [
        [
            record["risk_score_mean"]
            for record in records
            if generator in record["generators"]
        ]
        for generator in generator_names
    ]
    boxplot = axes[0, 0].boxplot(
        box_values,
        tick_labels=[name.upper() for name in generator_names],
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#000000", "linewidth": 1.4},
    )
    for patch, generator in zip(boxplot["boxes"], generator_names):
        patch.set_facecolor(GENERATOR_COLORS.get(generator, "#999999"))
        patch.set_alpha(0.65)
    for position, (generator, values) in enumerate(
        zip(generator_names, box_values), 1
    ):
        jitter = np.linspace(-0.12, 0.12, len(values))
        axes[0, 0].scatter(
            position + jitter,
            sorted(values),
            s=11,
            color=GENERATOR_COLORS.get(generator, "#666666"),
            edgecolors="white",
            linewidths=0.3,
            alpha=0.75,
        )
    axes[0, 0].axhline(50.0, color="#666666", linestyle="--", linewidth=0.8)
    axes[0, 0].axhline(75.0, color="#333333", linestyle=":", linewidth=0.8)
    axes[0, 0].set_ylabel("Observed risk score")
    axes[0, 0].set_title("A  Risk distribution by generator")

    matrix = np.asarray(
        [
            [summary["target_observed_matrix"][target][observed] for observed in RISK_LEVELS]
            for target in RISK_LEVELS
        ],
        dtype=float,
    )
    image = axes[0, 1].imshow(matrix, cmap="viridis", aspect="auto")
    axes[0, 1].set_xticks(range(len(RISK_LEVELS)), [level.title() for level in RISK_LEVELS])
    axes[0, 1].set_yticks(range(len(RISK_LEVELS)), [level.title() for level in RISK_LEVELS])
    axes[0, 1].set_xlabel("Observed risk level")
    axes[0, 1].set_ylabel("Target risk level")
    axes[0, 1].set_title("B  Target-observed matrix")
    threshold = matrix.max() / 2.0 if matrix.size else 0.0
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            axes[0, 1].text(
                column_index,
                row_index,
                str(int(matrix[row_index, column_index])),
                ha="center",
                va="center",
                color="white" if matrix[row_index, column_index] > threshold else "black",
                fontsize=9,
            )
    figure.colorbar(image, ax=axes[0, 1], fraction=0.046, pad=0.04, label="Scene count")

    evidence = summary["evidence_granularity_counts"]
    tiers = summary["quality_tier_counts"]
    category_names = ["Run-level", "Aggregate", "Silver", "Bronze"]
    category_values = [
        evidence.get("run_level", 0),
        evidence.get("aggregate", 0),
        tiers.get("silver", 0),
        tiers.get("bronze", 0),
    ]
    category_colors = ["#56B4E9", "#D55E00", "#0072B2", "#E69F00"]
    axes[1, 0].bar(category_names, category_values, color=category_colors)
    axes[1, 0].set_ylabel("Scene count")
    axes[1, 0].set_title("C  Evidence and quality tiers")
    axes[1, 0].tick_params(axis="x", rotation=18)
    for position, value in enumerate(category_values):
        axes[1, 0].text(position, value + 1.5, str(value), ha="center", va="bottom")
    axes[1, 0].set_ylim(0, max(category_values) * 1.18)

    for generator in generator_names:
        selected = [record for record in records if generator in record["generators"]]
        non_collision = [record for record in selected if not record["collision_observed"]]
        collision = [record for record in selected if record["collision_observed"]]
        color = GENERATOR_COLORS.get(generator, "#666666")
        axes[1, 1].scatter(
            [record["diversity_score"] for record in non_collision],
            [record["risk_score_mean"] for record in non_collision],
            s=24,
            color=color,
            alpha=0.65,
            label=generator.upper(),
        )
        axes[1, 1].scatter(
            [record["diversity_score"] for record in collision],
            [record["risk_score_mean"] for record in collision],
            s=42,
            facecolors="none",
            edgecolors=color,
            linewidths=1.2,
            marker="o",
        )
    axes[1, 1].axhline(75.0, color="#333333", linestyle=":", linewidth=0.8)
    axes[1, 1].set_xlabel("Library-relative diversity score")
    axes[1, 1].set_ylabel("Observed risk score")
    axes[1, 1].set_title("D  Risk-diversity map (rings = collision)")
    axes[1, 1].legend(frameon=False, ncols=3, loc="lower right")

    figure.suptitle("Scenario Library V1 Quality Baseline", fontsize=13, fontweight="bold")
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    figure.savefig(path_png, bbox_inches="tight")
    figure.savefig(path_svg, bbox_inches="tight", metadata={"Date": None})
    plt.close(figure)
    svg_path = Path(path_svg)
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
        encoding="utf-8",
    )


def format_rate(value):
    return f"{value * 100:.1f}%"


def compact_scene_table(records):
    lines = [
        "| 场景 | 生成器 | 目标 | 实测 | 分数 | 碰撞 | 证据 | 质量 | 多样性 |",
        "|---|---|---|---|---:|---:|---|---|---:|",
    ]
    for record in records:
        lines.append(
            "| {sample} | {generator} | {target} | {observed} | {score:.3f} | "
            "{collision} | {evidence} | {tier} | {diversity:.3f} |".format(
                sample=record["sample_id"],
                generator=record["generator"],
                target=record["target_risk"],
                observed=record["observed_risk"],
                score=record["risk_score_mean"],
                collision="是" if record["collision_observed"] else "否",
                evidence=record["evidence_granularity"],
                tier=record["quality_tier"],
                diversity=record["diversity_score"],
            )
        )
    return lines


def write_report(path, entries_path, entries_sha256, summary):
    generator_lines = [
        "| 生成器 | 场景数 | 平均风险 | 高/临界 | 碰撞 | 目标命中 | 平均多样性 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["generator_summaries"]:
        generator_lines.append(
            "| {generator} | {count} | {risk:.3f} | {high} | {collision} | "
            "{match} | {diversity:.3f} |".format(
                generator=item["generator"].upper(),
                count=item["scene_count"],
                risk=item["risk_score_mean"],
                high=format_rate(item["high_or_critical_rate"]),
                collision=format_rate(item["collision_scene_rate"]),
                match=format_rate(item["target_match_rate"]),
                diversity=item["diversity_score_mean"],
            )
        )
    matrix_lines = [
        "| 目标\\实测 | low | medium | high | critical | 合计 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for target in RISK_LEVELS:
        row = summary["target_observed_matrix"][target]
        matrix_lines.append(
            f"| {target} | {row['low']} | {row['medium']} | {row['high']} | "
            f"{row['critical']} | {sum(row.values())} |"
        )
    evidence = summary["evidence_granularity_counts"]
    verification_bases = summary["verification_basis_counts"]
    tiers = summary["quality_tier_counts"]
    lines = [
        "# 场景库 V1 质量分析基线",
        "",
        f"- 分析日期：`{summary['analysis_date']}`。",
        f"- 输入：`{entries_path}`。",
        f"- 输入 SHA-256：`{entries_sha256}`。",
        "- 本报告仅离线分析已归档场景条目，没有重新运行 CARLA。",
        "",
        "![场景库质量总览](scenario_library_quality_overview.png)",
        "",
        "## 总体结论",
        "",
        f"- 当前库包含 `{summary['entry_count']}` 个独立场景和 "
        f"`{summary['accepted_run_evidence_count']}` 次来源批次严格验收运行。",
        f"- 实测 high/critical 场景 `{summary['high_or_critical_scene_count']}` 个，"
        f"占 `{format_rate(summary['high_or_critical_scene_rate'])}`；碰撞场景 "
        f"`{summary['collision_scene_count']}` 个，占 "
        f"`{format_rate(summary['collision_scene_rate'])}`。",
        f"- 目标风险与实测主档完全一致的场景 `{summary['target_match_count']}` 个，"
        f"命中率 `{format_rate(summary['target_match_rate'])}`；目标档序号与实测分数的 "
        f"Spearman 为 `{summary['target_score_spearman']:.3f}`。",
        f"- 场景库内相对多样性均值为 `{summary['diversity']['mean']:.3f}`，"
        f"其中 `{summary['diversity']['low_relative_diversity_count']}` 个场景被标记为低相对多样性。",
        f"- 逐次证据 `{evidence.get('run_level', 0)}` 个、聚合证据 "
        f"`{evidence.get('aggregate', 0)}` 个；质量等级为 silver "
        f"`{tiers.get('silver', 0)}` 个、bronze `{tiers.get('bronze', 0)}` 个。",
        f"- 直接逐次验收依据 `{verification_bases.get('direct_run_evidence', 0)}` 个；"
        f"继承来源批次验收依据 "
        f"`{verification_bases.get('inherited_batch_acceptance', 0)}` 个。",
        f"- `{summary['carla_version_unknown_count']}` 个条目未记录场景级 CARLA 版本，"
        f"`{summary['realism_not_assessed_count']}` 个条目的真实性尚未评估。",
        "",
        "## 生成器分布",
        "",
        *generator_lines,
        "",
        "这些指标描述当前风险反馈驱动样本库，不代表各生成器在自然交通分布中的总体表现。",
        "",
        "## 目标与实测风险",
        "",
        *matrix_lines,
        "",
        f"目标档序号与实测风险档序号的 Spearman 为 "
        f"`{summary['target_observed_level_spearman']:.3f}`。当前库以 high/critical "
        "目标为主，适合作为压力测试库，但不适合直接估计真实道路风险发生率。",
        "",
        "## 证据与质量边界",
        "",
        "- `run_level/silver` 条目保留逐次运行证据；`aggregate/bronze` 条目只保留场景级聚合血缘。",
        "- 聚合条目继承来源批次的严格验收结论，但不能据此补造逐次 `run_id`、配置路径或元数据路径。",
        "- 当前所有条目均缺少可直接查询的场景级 CARLA 版本字段，因此不能评为 gold。",
        "- 真实性保持 `not_assessed`；获得同口径真实世界参数分布前，不计算真实性分数。",
        "- 多样性是当前 117 条记录内部的 15 维归一化最近邻指标，扩库后必须重新计算。",
        "",
        "## 高风险优先审查场景",
        "",
        *compact_scene_table(summary["top_dangerous"]),
        "",
        "## 低多样性优先审查场景",
        "",
        *compact_scene_table(summary["lowest_diversity"]),
        "",
        "## 后续动作",
        "",
        "1. 使用本基线为构建器和查询 CLI 增加固定样本回归测试，冻结 Schema、哈希和检索字段。",
        "2. 新增运行必须记录 CARLA 客户端/服务端版本、配置哈希和逐次元数据路径，逐步提升 gold 条目比例。",
        "3. 后续扩库继续保留生成器、目标风险、碰撞和多样性配额，避免只堆积高分近重复样本。",
        "4. 真实性评估单独等待可映射到 15 维参数的公开或真实世界参考数据，不与当前危险性评分混合。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(output_dir, entries_path, entries_sha256, output_names):
    outputs = {}
    for name in output_names:
        output_path = output_dir / name
        outputs[name] = {
            "sha256": sha256_file(output_path),
            "size_bytes": output_path.stat().st_size,
        }
    manifest = {
        "format": "scenario_library_quality_analysis_v1_manifest",
        "analysis_date": date.today().isoformat(),
        "input": {
            "path": str(entries_path),
            "sha256": entries_sha256,
        },
        "outputs": outputs,
    }
    with open(output_dir / "manifest.json", "w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    args = parse_args()
    if args.top_k <= 0:
        raise ValueError("--top-k 必须大于 0")
    entries_path = Path(os.path.abspath(args.entries))
    output_dir = Path(os.path.abspath(args.output_dir))
    entries = load_entries(entries_path)
    validate_entries(entries)
    records, summary = build_analysis(entries, args.top_k)
    print(
        "[QUALITY] entries={entries} | runs={runs} | high_or_critical={high} | "
        "collisions={collisions} | target_match={match:.3f}".format(
            entries=summary["entry_count"],
            runs=summary["accepted_run_evidence_count"],
            high=summary["high_or_critical_scene_count"],
            collisions=summary["collision_scene_count"],
            match=summary["target_match_rate"],
        )
    )
    if args.validate_only:
        print("[VALID] 场景库质量分析输入与统计计算通过")
        return 0
    output_dir.mkdir(parents=True, exist_ok=True)
    entries_sha256 = sha256_file(entries_path)
    summary["input"] = {
        "path": str(entries_path),
        "sha256": entries_sha256,
    }
    summary_path = output_dir / "analysis_summary.json"
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2, allow_nan=False)
    write_scenario_index(output_dir / "scenario_quality_index.csv", records)
    write_generator_summary(
        output_dir / "generator_quality_summary.csv",
        summary["generator_summaries"],
    )
    write_target_matrix(
        output_dir / "target_observed_matrix.csv",
        summary["target_observed_matrix"],
    )
    write_quality_flags(
        output_dir / "quality_flag_counts.csv",
        summary["quality_flag_counts"],
        summary["entry_count"],
    )
    plot_quality_overview(
        output_dir / "scenario_library_quality_overview.png",
        output_dir / "scenario_library_quality_overview.svg",
        records,
        summary,
    )
    write_report(
        output_dir / "quality_analysis_report.md",
        entries_path,
        entries_sha256,
        summary,
    )
    output_names = (
        "analysis_summary.json",
        "scenario_quality_index.csv",
        "generator_quality_summary.csv",
        "target_observed_matrix.csv",
        "quality_flag_counts.csv",
        "scenario_library_quality_overview.png",
        "scenario_library_quality_overview.svg",
        "quality_analysis_report.md",
    )
    write_manifest(output_dir, entries_path, entries_sha256, output_names)
    print(f"[DONE] 分析目录: {output_dir}")
    print(f"[DONE] 报告: {output_dir / 'quality_analysis_report.md'}")
    print(f"[DONE] 图表: {output_dir / 'scenario_library_quality_overview.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
