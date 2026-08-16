"""合并基础风险反馈数据与外部验证新增数据。"""

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_DATASET = (
    PROJECT_ROOT / "data" / "scenarios" / "risk_feedback_v1" / "dataset.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "scenarios" / "risk_feedback_v2"
FEATURE_PREFIX = "feature_"
REQUIRED_COLUMNS = {
    "sample_id",
    "generator",
    "target_risk_level",
    "repeat_count",
    "traffic_manager_seeds",
    "observed_risk_score_mean",
    "collision_run_rate",
}


def parse_args():
    parser = argparse.ArgumentParser(description="合并风险反馈数据集")
    parser.add_argument("--base-dataset", default=str(DEFAULT_BASE_DATASET))
    parser.add_argument("--addition-dataset", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--version-label", default="V2")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset(path, source_name):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    missing = sorted(REQUIRED_COLUMNS - set(fieldnames))
    if missing:
        raise ValueError(f"{source_name} 缺少字段: {missing}")
    feature_columns = [
        column for column in fieldnames if column.startswith(FEATURE_PREFIX)
    ]
    if len(feature_columns) != 15:
        raise ValueError(
            f"{source_name} 需要 15 个归一化参数特征，实际为 {len(feature_columns)}"
        )
    if not rows:
        raise ValueError(f"{source_name} 没有数据行")

    sample_ids = []
    for row in rows:
        sample_id = row["sample_id"].strip()
        if not sample_id:
            raise ValueError(f"{source_name} 存在空 sample_id")
        sample_ids.append(sample_id)
        repeat_count = int(row["repeat_count"])
        seeds = [
            int(seed)
            for seed in row["traffic_manager_seeds"].split(",")
            if seed.strip()
        ]
        if repeat_count != len(seeds) or len(seeds) != len(set(seeds)):
            raise ValueError(
                f"{source_name} 样本 {sample_id} 的重复次数与交通种子不一致"
            )
        float(row["observed_risk_score_mean"])
        collision_run_rate = float(row["collision_run_rate"])
        if not 0.0 <= collision_run_rate <= 1.0:
            raise ValueError(
                f"{source_name} 样本 {sample_id} 的 collision_run_rate 越界"
            )
        for feature in feature_columns:
            float(row[feature])

    duplicates = sorted(
        sample_id
        for sample_id, count in Counter(sample_ids).items()
        if count > 1
    )
    if duplicates:
        raise ValueError(f"{source_name} 存在重复 sample_id: {duplicates[:5]}")
    return fieldnames, rows


def write_csv(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def counter_by(rows, key):
    return dict(sorted(Counter(row[key] for row in rows).items()))


def main():
    args = parse_args()
    base_path = Path(os.path.abspath(args.base_dataset))
    addition_path = Path(os.path.abspath(args.addition_dataset))
    output_dir = Path(os.path.abspath(args.output_dir))
    if output_dir.exists() and any(output_dir.iterdir()) and not args.force:
        raise FileExistsError(f"输出目录非空，如需覆盖请使用 --force: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    base_fields, base_rows = load_dataset(base_path, "基础数据集")
    addition_fields, addition_rows = load_dataset(addition_path, "新增数据集")
    if base_fields != addition_fields:
        raise ValueError("基础数据集与新增数据集字段或字段顺序不一致")

    base_ids = {row["sample_id"] for row in base_rows}
    addition_ids = {row["sample_id"] for row in addition_rows}
    overlap = sorted(base_ids & addition_ids)
    if overlap:
        raise ValueError(f"基础数据集与新增数据集 sample_id 重复: {overlap[:5]}")

    merged_rows = sorted(
        [*base_rows, *addition_rows], key=lambda row: row["sample_id"]
    )
    version_label = args.version_label.strip()
    if not version_label:
        raise ValueError("--version-label 不能为空")

    addition_copy = output_dir / "external_validation_addition.csv"
    dataset_path = output_dir / "dataset.csv"
    write_csv(addition_copy, base_fields, addition_rows)
    write_csv(dataset_path, base_fields, merged_rows)
    with open(output_dir / "dataset.jsonl", "w", encoding="utf-8") as file:
        for row in merged_rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "format": "risk_feedback_dataset_merge_v2",
        "version_label": version_label,
        "analysis_unit": "independent_scenario",
        "traffic_seed_role": "repeated_measurement",
        "feature_count": len(
            [column for column in base_fields if column.startswith(FEATURE_PREFIX)]
        ),
        "base_dataset": {
            "path": str(base_path),
            "sha256": file_sha256(base_path),
            "independent_scenario_count": len(base_rows),
        },
        "addition_dataset": {
            "source_path": str(addition_path),
            "source_sha256": file_sha256(addition_path),
            "copied_path": str(addition_copy),
            "copied_sha256": file_sha256(addition_copy),
            "independent_scenario_count": len(addition_rows),
        },
        "merged_dataset": {
            "path": str(dataset_path),
            "sha256": file_sha256(dataset_path),
            "independent_scenario_count": len(merged_rows),
        },
        "generator_counts": counter_by(merged_rows, "generator"),
        "target_level_counts": counter_by(merged_rows, "target_risk_level"),
        "generator_target_cell_counts": counter_by(
            merged_rows, "generator_target_cell"
        ),
        "collision_scenario_count": sum(
            float(row["collision_run_rate"]) > 0.0 for row in merged_rows
        ),
        "sample_id_overlap_count": 0,
    }
    write_json(output_dir / "merge_summary.json", summary)

    report_lines = [
        f"# 风险反馈数据集 {version_label}",
        "",
        f"- 基础数据：`{len(base_rows)}` 个独立场景。",
        f"- 外部验证新增：`{len(addition_rows)}` 个独立场景。",
        f"- 合并结果：`{len(merged_rows)}` 个独立场景，重复 `sample_id` 为 `0`。",
        f"- 碰撞场景：`{summary['collision_scenario_count']}` 个。",
        "- Traffic Manager 种子仍作为同一场景的重复测量，不计为独立样本。",
        "- `target_risk_level` 和 `generator` 仅用于分层与诊断，不作为风险代理输入。",
        "",
        "## 文件",
        "",
        f"- `external_validation_addition.csv`：{len(addition_rows)} 个外部验证新增场景。",
        "- `dataset.csv`：合并后的场景级训练数据。",
        "- `dataset.jsonl`：与 CSV 等价的逐行 JSON。",
        "- `merge_summary.json`：来源哈希、计数和合并校验。",
    ]
    (output_dir / "README.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )
    print(
        f"[MERGE] base={len(base_rows)} | addition={len(addition_rows)} | "
        f"merged={len(merged_rows)} | collisions={summary['collision_scenario_count']}"
    )
    print(f"[MERGE] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
