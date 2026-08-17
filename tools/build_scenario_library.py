"""构建极端场景库 V1 的 JSONL、CSV 索引和质量汇总。"""

import argparse
import csv
import json
import os
import statistics
import sys
from collections import Counter


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_library import (  # noqa: E402
    build_library_entries,
    file_sha256,
    load_json,
    portable_path,
)


DEFAULT_SOURCES = os.path.join(
    PROJECT_ROOT,
    "configs",
    "scenario_library_sources_v1.json",
)
DEFAULT_SCHEMA = os.path.join(
    PROJECT_ROOT,
    "schemas",
    "scenario_library_entry.schema.json",
)
DEFAULT_OUTPUT = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "scenario_library_v1",
)


INDEX_FIELDS = (
    "library_id",
    "scenario_hash",
    "canonical_sample_id",
    "aliases",
    "generators",
    "target_risk_levels",
    "observed_risk_level",
    "risk_score_mean",
    "risk_score_std",
    "collision_observed",
    "verification_level",
    "evidence_granularity",
    "carla_versions",
    "accepted_run_count",
    "expected_run_count",
    "quality_tier",
    "quality_status",
    "executability_score",
    "evidence_completeness_score",
    "repeatability_score",
    "dangerousness_score",
    "diversity_score",
    "quality_flags",
)


def parse_args():
    parser = argparse.ArgumentParser(description="构建极端场景库 V1")
    parser.add_argument("--sources", default=DEFAULT_SOURCES)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_jsonl(path, entries):
    with open(path, "w", encoding="utf-8") as file:
        for entry in entries:
            file.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def index_row(entry):
    evidence = entry["execution_evidence"]
    risk = entry["observed_risk"]
    quality = entry["quality"]
    return {
        "library_id": entry["library_id"],
        "scenario_hash": entry["scenario_hash"],
        "canonical_sample_id": entry["canonical_sample_id"],
        "aliases": ";".join(entry["aliases"]),
        "generators": ";".join(entry["labels"]["generators"]),
        "target_risk_levels": ";".join(entry["labels"]["target_risk_levels"]),
        "observed_risk_level": entry["labels"]["observed_risk_level"],
        "risk_score_mean": risk["score_mean"],
        "risk_score_std": risk["score_std"],
        "collision_observed": risk["collision_observed"],
        "verification_level": evidence["verification_level"],
        "evidence_granularity": evidence["evidence_granularity"],
        "carla_versions": ";".join(evidence["carla_versions"]) or "unknown",
        "accepted_run_count": evidence["accepted_run_count"],
        "expected_run_count": evidence["expected_run_count"],
        "quality_tier": quality["tier"],
        "quality_status": quality["assessment_status"],
        "executability_score": quality["executability"]["score"],
        "evidence_completeness_score": quality["evidence_completeness"]["score"],
        "repeatability_score": quality["repeatability"]["score"],
        "dangerousness_score": quality["dangerousness"]["score"],
        "diversity_score": quality["diversity"]["score"],
        "quality_flags": ";".join(quality["flags"]),
    }


def write_index(path, entries):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(index_row(entry) for entry in entries)


def build_summary(entries, stats, source_config):
    generator_counts = Counter()
    target_counts = Counter()
    observed_counts = Counter()
    quality_tiers = Counter()
    verification_levels = Counter()
    evidence_granularities = Counter()
    quality_flags = Counter()
    for entry in entries:
        generator_counts.update(entry["labels"]["generators"])
        target_counts.update(entry["labels"]["target_risk_levels"])
        observed_counts.update([entry["labels"]["observed_risk_level"]])
        quality_tiers.update([entry["quality"]["tier"]])
        verification_levels.update(
            [entry["execution_evidence"]["verification_level"]]
        )
        evidence_granularities.update(
            [entry["execution_evidence"]["evidence_granularity"]]
        )
        quality_flags.update(entry["quality"]["flags"])
    high_target_count = sum(
        "high" in entry["labels"]["target_risk_levels"]
        or "critical" in entry["labels"]["target_risk_levels"]
        for entry in entries
    )
    collision_scene_count = sum(
        entry["observed_risk"]["collision_observed"] for entry in entries
    )
    high_observed_count = sum(
        entry["observed_risk"]["high_or_critical"] for entry in entries
    )
    run_level_count = evidence_granularities["run_level"]
    return {
        "format": "scenario_library_v1_summary",
        "library_version": source_config["library_version"],
        "build_date": source_config["build_date"],
        **stats,
        "generator_counts": dict(sorted(generator_counts.items())),
        "target_risk_level_counts": dict(sorted(target_counts.items())),
        "observed_risk_level_counts": dict(sorted(observed_counts.items())),
        "verification_level_counts": dict(sorted(verification_levels.items())),
        "evidence_granularity_counts": dict(
            sorted(evidence_granularities.items())
        ),
        "quality_tier_counts": dict(sorted(quality_tiers.items())),
        "quality_flag_counts": dict(sorted(quality_flags.items())),
        "target_high_or_critical_scene_count": high_target_count,
        "target_high_or_critical_scene_rate": high_target_count / len(entries),
        "collision_scene_count": collision_scene_count,
        "collision_scene_rate": collision_scene_count / len(entries),
        "high_or_critical_scene_count": high_observed_count,
        "high_or_critical_scene_rate": high_observed_count / len(entries),
        "run_level_evidence_rate": run_level_count / len(entries),
        "mean_risk_score": statistics.fmean(
            entry["observed_risk"]["score_mean"] for entry in entries
        ),
        "mean_operational_quality": statistics.fmean(
            entry["quality"]["operational_score"] for entry in entries
        ),
        "mean_diversity_score": statistics.fmean(
            entry["quality"]["diversity"]["score"] for entry in entries
        ),
        "quality_scope": {
            "executability": "assessed_from_strict_acceptance",
            "evidence_completeness": "assessed_from_run_level_fields_or_aggregate_lineage",
            "repeatability": "assessed_from_three_seed_risk_score_std",
            "dangerousness": "assessed_from_heuristic_v2_mean_score",
            "diversity": "assessed_within_current_library_in_normalized_15d_space",
            "realism": "not_assessed_without_real_world_reference_distribution"
        }
    }


def render_readme(summary):
    return f"""# 极端场景库 V1

## 当前内容

- 独立场景：`{summary['entry_count']}` 个；内容哈希已去重。
- 严格验收运行证据：`{summary['accepted_run_evidence_count']}` 次。
- 生成器分布：`{json.dumps(summary['generator_counts'], ensure_ascii=False)}`。
- 目标风险分布：`{json.dumps(summary['target_risk_level_counts'], ensure_ascii=False)}`。
- 实测高风险及以上：`{summary['high_or_critical_scene_count']}` 个；碰撞场景：`{summary['collision_scene_count']}` 个。

## 文件

- `entries.jsonl`：完整场景库条目，符合 `schemas/scenario_library_entry.schema.json`。
- `index.csv`：面向筛选和后续检索的扁平索引。
- `summary.json`：数量、风险、质量和证据范围汇总。
- `manifest.json`：输入、Schema 与输出文件哈希。

## 查询示例

```cmd
python tools\query_scenario_library.py --collision yes --sort risk_desc --limit 10
python tools\query_scenario_library.py --generator cvae --target-risk critical --min-score 70
python tools\query_scenario_library.py --evidence-granularity run_level --quality-tier silver
```

## 质量边界

- 可执行性、证据完整性和重复性来自 CARLA 运行与严格验收记录。
- 危险性来自 `heuristic_v2` 实测风险均值，不等同于真实道路事故概率。
- 多样性仅表示当前库内 15 维归一化参数空间的最近邻距离，会随场景库扩展而变化。
- 真实性尚未评估，因为当前没有同口径真实世界参数分布；条目保持 `partial`，不得表述为真实性验证通过。
- `run_level` 条目保留逐次运行、配置与历史元数据路径；`aggregate` 条目只保留 V5 场景级聚合结果和来源文件哈希，不能反向伪造逐次运行路径。
- 当前聚合数据和首批历史运行结果均未在场景级表中记录 CARLA 客户端/服务端版本，因此证据完整性不会被评为满分；这不改变来源批次通过严格验收的事实。
- 当前库是风险反馈驱动的压力测试库，高/临界目标占比较高，不代表真实交通场景自然分布。
"""


def main():
    args = parse_args()
    sources_path = os.path.abspath(args.sources)
    schema_path = os.path.abspath(args.schema)
    output_dir = os.path.abspath(args.output_dir)
    source_config = load_json(sources_path)
    schema = load_json(schema_path)
    entries, stats = build_library_entries(
        source_config,
        schema,
        PROJECT_ROOT,
    )
    summary = build_summary(entries, stats, source_config)
    print(
        f"[LIBRARY] entries={summary['entry_count']} | "
        f"strict_runs={summary['accepted_run_evidence_count']} | "
        f"duplicates={summary['duplicate_record_count']} | "
        f"excluded={summary['excluded_record_count']}"
    )
    if args.validate_only:
        print("[VALID] 场景库来源、条目 Schema 和质量字段校验通过")
        return 0

    os.makedirs(output_dir, exist_ok=True)
    entries_path = os.path.join(output_dir, "entries.jsonl")
    index_path = os.path.join(output_dir, "index.csv")
    summary_path = os.path.join(output_dir, "summary.json")
    readme_path = os.path.join(output_dir, "README.md")
    manifest_path = os.path.join(output_dir, "manifest.json")
    write_jsonl(entries_path, entries)
    write_index(index_path, entries)
    write_json(summary_path, summary)
    with open(readme_path, "w", encoding="utf-8") as file:
        file.write(render_readme(summary))
    manifest = {
        "format": "scenario_library_v1_manifest",
        "library_version": source_config["library_version"],
        "build_date": source_config["build_date"],
        "schema": {
            "path": portable_path(PROJECT_ROOT, schema_path),
            "sha256": file_sha256(schema_path),
        },
        "source_config": {
            "path": portable_path(PROJECT_ROOT, sources_path),
            "sha256": file_sha256(sources_path),
        },
        "source_ids": [source["source_id"] for source in source_config["sources"]],
        "entry_count": len(entries),
        "accepted_run_evidence_count": summary["accepted_run_evidence_count"],
        "outputs": {
            "entries.jsonl": file_sha256(entries_path),
            "index.csv": file_sha256(index_path),
            "summary.json": file_sha256(summary_path),
            "README.md": file_sha256(readme_path),
        },
    }
    write_json(manifest_path, manifest)
    print(f"[DONE] 场景条目: {entries_path}")
    print(f"[DONE] 检索索引: {index_path}")
    print(f"[DONE] 汇总: {summary_path}")
    print(f"[DONE] 清单: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
