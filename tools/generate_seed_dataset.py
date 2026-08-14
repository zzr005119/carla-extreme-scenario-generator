"""生成平衡、可复现的参数级 CARLA 场景种子数据集。"""

import argparse
import json
import os
import random
import shutil
import sys
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_validator import (  # noqa: E402
    compile_carla_config,
    derive_weather_tags,
    load_json,
    rebase_output_root,
    require_valid_scenario,
)


RISK_LEVELS = ("low", "medium", "high", "critical")
RANGES = {
    "low": {
        "cloudiness": (35.0, 75.0),
        "precipitation": (20.0, 60.0),
        "precipitation_deposits": (20.0, 60.0),
        "wind_intensity": (5.0, 45.0),
        "fog_density": (15.0, 50.0),
        "fog_distance": (28.0, 60.0),
        "sun_altitude_angle": (-5.0, 20.0),
        "wetness": (30.0, 65.0),
        "initial_distance_m": (34.0, 46.0),
        "brake_trigger_seconds": (7.0, 10.0),
        "brake_intensity": (0.55, 0.78),
        "forward_distance_m": (30.0, 45.0),
        "roadside_offset_m": (7.0, 9.0),
        "trigger_seconds": (5.0, 7.5),
        "speed_mps": (2.0, 3.4)
    },
    "medium": {
        "cloudiness": (60.0, 90.0),
        "precipitation": (50.0, 78.0),
        "precipitation_deposits": (45.0, 78.0),
        "wind_intensity": (30.0, 70.0),
        "fog_density": (45.0, 72.0),
        "fog_distance": (14.0, 35.0),
        "sun_altitude_angle": (-12.0, 8.0),
        "wetness": (55.0, 82.0),
        "initial_distance_m": (27.0, 37.0),
        "brake_trigger_seconds": (5.5, 8.0),
        "brake_intensity": (0.70, 0.88),
        "forward_distance_m": (26.0, 40.0),
        "roadside_offset_m": (6.5, 8.5),
        "trigger_seconds": (3.8, 6.0),
        "speed_mps": (3.0, 4.5)
    },
    "high": {
        "cloudiness": (82.0, 100.0),
        "precipitation": (76.0, 100.0),
        "precipitation_deposits": (70.0, 100.0),
        "wind_intensity": (55.0, 90.0),
        "fog_density": (70.0, 92.0),
        "fog_distance": (6.0, 18.0),
        "sun_altitude_angle": (-22.0, 0.0),
        "wetness": (75.0, 100.0),
        "initial_distance_m": (19.0, 29.0),
        "brake_trigger_seconds": (3.8, 6.0),
        "brake_intensity": (0.85, 1.0),
        "forward_distance_m": (22.0, 36.0),
        "roadside_offset_m": (5.8, 8.0),
        "trigger_seconds": (2.5, 4.5),
        "speed_mps": (4.2, 6.0)
    },
    "critical": {
        "cloudiness": (92.0, 100.0),
        "precipitation": (88.0, 100.0),
        "precipitation_deposits": (85.0, 100.0),
        "wind_intensity": (70.0, 100.0),
        "fog_density": (88.0, 100.0),
        "fog_distance": (3.0, 8.0),
        "sun_altitude_angle": (-30.0, -8.0),
        "wetness": (88.0, 100.0),
        "initial_distance_m": (12.0, 20.0),
        "brake_trigger_seconds": (2.8, 4.5),
        "brake_intensity": (0.95, 1.0),
        "forward_distance_m": (18.0, 32.0),
        "roadside_offset_m": (5.0, 7.0),
        "trigger_seconds": (1.8, 3.5),
        "speed_mps": (5.5, 8.0)
    }
}


def latin_hypercube(count, dimensions, rng):
    columns = {}
    for name, (low, high) in dimensions.items():
        positions = [(index + rng.random()) / count for index in range(count)]
        rng.shuffle(positions)
        columns[name] = [low + position * (high - low) for position in positions]
    return [
        {name: columns[name][index] for name in dimensions}
        for index in range(count)
    ]


def split_labels(count, rng):
    train_count = round(count * 0.70)
    validation_count = round(count * 0.15)
    test_count = count - train_count - validation_count
    labels = (
        ["train"] * train_count
        + ["validation"] * validation_count
        + ["test"] * test_count
    )
    rng.shuffle(labels)
    return labels


def round_parameters(values):
    return {name: round(value, 3) for name, value in values.items()}


def condition_text(level, weather_tags):
    tag_names = {
        "rain": "降雨",
        "heavy_rain": "暴雨",
        "fog": "雾天",
        "dense_fog": "浓雾",
        "night": "夜间",
        "day": "日间",
        "wet_road": "湿滑路面",
        "strong_wind": "强风"
    }
    level_names = {
        "low": "低风险",
        "medium": "中风险",
        "high": "高风险",
        "critical": "临界风险"
    }
    weather_text = "、".join(tag_names[tag] for tag in weather_tags)
    return f"{weather_text}条件下，前车急刹与行人横穿叠加的{level_names[level]}场景"


def build_record(level, index, values, split, seed, created_at):
    values = round_parameters(values)
    weather = {
        name: values[name]
        for name in (
            "cloudiness",
            "precipitation",
            "precipitation_deposits",
            "wind_intensity",
            "fog_density",
            "fog_distance",
            "sun_altitude_angle",
            "wetness"
        )
    }
    weather_tags = derive_weather_tags(weather)
    sample_id = f"seed_v1_{level}_{index:04d}"
    return {
        "schema_version": "1.0",
        "sample_id": sample_id,
        "family": "multi_hazard_parameter_v1",
        "conditions": {
            "target_risk_level": level,
            "weather_tags": weather_tags,
            "hazard_tags": [
                "lead_vehicle_braking",
                "pedestrian_crossing"
            ],
            "condition_text_zh": condition_text(level, weather_tags)
        },
        "scenario": {
            "duration_seconds": 20.0,
            "traffic_manager_seed": seed + index
        },
        "weather": weather,
        "lead_vehicle": {
            "initial_distance_m": values["initial_distance_m"],
            "brake_trigger_seconds": values["brake_trigger_seconds"],
            "brake_intensity": values["brake_intensity"]
        },
        "pedestrian": {
            "forward_distance_m": values["forward_distance_m"],
            "roadside_offset_m": values["roadside_offset_m"],
            "spawn_z_offset_m": 0.5,
            "trigger_seconds": values["trigger_seconds"],
            "speed_mps": values["speed_mps"]
        },
        "observed_risk": {
            "status": "not_simulated",
            "method": None,
            "score": None,
            "level": None,
            "run_dir": None
        },
        "provenance": {
            "source_kind": "synthetic_parameter_design",
            "generator": "balanced_latin_hypercube_v1",
            "generator_seed": seed,
            "split": split,
            "created_at": created_at
        }
    }


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def distribution(records, key_function):
    result = {}
    for record in records:
        key = key_function(record)
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def risk_split_distribution(records):
    result = {}
    for level in RISK_LEVELS:
        result[level] = distribution(
            [
                record
                for record in records
                if record["conditions"]["target_risk_level"] == level
            ],
            lambda item: item["provenance"]["split"]
        )
    return result


def create_readme(output_dir, manifest):
    content = f"""# Seed Scenario Dataset V1

该目录是生成式 AI 参数级场景模型的第一版种子数据，不是 CARLA 实测结果。

## 数据规模

- 总样本：{manifest['record_count']}
- 风险目标分布：`{json.dumps(manifest['target_risk_distribution'], ensure_ascii=False)}`
- 数据划分：`{json.dumps(manifest['split_distribution'], ensure_ascii=False)}`
- 各风险档划分：`{json.dumps(manifest['risk_split_distribution'], ensure_ascii=False)}`
- 生成方法：平衡风险分层 + Latin Hypercube 参数覆盖
- 随机种子：`{manifest['generator_seed']}`

## 文件

- `scenarios.jsonl`：全部场景记录。
- `train.jsonl`：训练集。
- `validation.jsonl`：验证集。
- `test.jsonl`：测试集，仅用于最终模型评估。
- `example_record.json`：单条场景记录示例。
- `example_compiled_config.json`：编译后的 CARLA 完整配置示例。
- `manifest.json`：数据来源、分布和校验结果。

## 复现与校验

```cmd
python tools\generate_seed_dataset.py --force
python core\scenario_validator.py data\scenarios\seed_v1\scenarios.jsonl
python scenes\scene_04_parameterized.py --config data\scenarios\seed_v1\example_compiled_config.json --validate-only
```

## 标签边界

`conditions.target_risk_level` 是参数设计目标，不是 CARLA 实测风险等级。
样本完成仿真后，应将结果写入 `observed_risk`，训练和论文分析时必须区分目标标签与实测标签。
"""
    with open(os.path.join(output_dir, "README.md"), "w", encoding="utf-8") as file:
        file.write(content)


def parse_args():
    parser = argparse.ArgumentParser(description="生成参数级场景种子数据集")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "data", "scenarios", "seed_v1")
    )
    parser.add_argument("--count-per-level", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument(
        "--base-config",
        default=os.path.join(
            PROJECT_ROOT,
            "configs",
            "multi_hazard_rainy_night.json"
        )
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.count_per_level < 8:
        raise ValueError("--count-per-level 至少为 8，避免数据划分过小")

    output_dir = os.path.abspath(args.output_dir)
    if os.path.isdir(output_dir) and os.listdir(output_dir):
        if not args.force:
            raise FileExistsError(
                f"输出目录非空: {output_dir}，如需覆盖请使用 --force"
            )
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    records = []
    global_index = 0
    for level_index, level in enumerate(RISK_LEVELS):
        level_rng = random.Random(args.seed + level_index * 1009)
        designs = latin_hypercube(
            args.count_per_level,
            RANGES[level],
            level_rng
        )
        splits = split_labels(args.count_per_level, level_rng)
        for local_index, (values, split) in enumerate(
            zip(designs, splits),
            1
        ):
            global_index += 1
            record = build_record(
                level,
                global_index,
                values,
                split,
                args.seed,
                created_at
            )
            require_valid_scenario(record)
            records.append(record)

    random.Random(args.seed + 100003).shuffle(records)
    sample_ids = [record["sample_id"] for record in records]
    parameter_vectors = [
        json.dumps(
            {
                section: record[section]
                for section in (
                    "scenario",
                    "weather",
                    "lead_vehicle",
                    "pedestrian"
                )
            },
            ensure_ascii=False,
            sort_keys=True
        )
        for record in records
    ]
    if len(sample_ids) != len(set(sample_ids)):
        raise RuntimeError("生成数据包含重复 sample_id")
    if len(parameter_vectors) != len(set(parameter_vectors)):
        raise RuntimeError("生成数据包含重复场景参数")

    by_split = {
        split: [
            record
            for record in records
            if record["provenance"]["split"] == split
        ]
        for split in ("train", "validation", "test")
    }

    write_jsonl(os.path.join(output_dir, "scenarios.jsonl"), records)
    for split, split_records in by_split.items():
        write_jsonl(
            os.path.join(output_dir, f"{split}.jsonl"),
            split_records
        )

    example_record = next(
        record
        for record in records
        if record["conditions"]["target_risk_level"] == "high"
        and record["provenance"]["split"] == "train"
    )
    write_json(os.path.join(output_dir, "example_record.json"), example_record)
    base_config = load_json(os.path.abspath(args.base_config))
    example_compiled_path = os.path.join(
        output_dir,
        "example_compiled_config.json"
    )
    example_compiled_config = compile_carla_config(example_record, base_config)
    rebase_output_root(
        example_compiled_config,
        args.base_config,
        example_compiled_path
    )
    write_json(
        example_compiled_path,
        example_compiled_config
    )

    manifest = {
        "dataset_name": "carla_extreme_scenario_seed_v1",
        "schema_version": "1.0",
        "record_count": len(records),
        "generator": "balanced_latin_hypercube_v1",
        "generator_seed": args.seed,
        "created_at": created_at,
        "source_kind": "synthetic_parameter_design",
        "record_order_randomized": True,
        "target_risk_distribution": distribution(
            records,
            lambda item: item["conditions"]["target_risk_level"]
        ),
        "split_distribution": distribution(
            records,
            lambda item: item["provenance"]["split"]
        ),
        "risk_split_distribution": risk_split_distribution(records),
        "observed_risk_status": "not_simulated",
        "validation": {
            "schema_valid_records": len(records),
            "schema_invalid_records": 0,
            "unique_sample_ids": len(set(sample_ids)),
            "unique_parameter_vectors": len(set(parameter_vectors))
        },
        "files": {
            "all": "scenarios.jsonl",
            "train": "train.jsonl",
            "validation": "validation.jsonl",
            "test": "test.jsonl",
            "example_record": "example_record.json",
            "example_compiled_config": "example_compiled_config.json"
        }
    }
    write_json(os.path.join(output_dir, "manifest.json"), manifest)
    create_readme(output_dir, manifest)

    print(f"[DATASET] 输出目录: {output_dir}")
    print(f"[DATASET] 总样本: {len(records)}")
    print(
        "[DATASET] 风险目标: "
        + json.dumps(manifest["target_risk_distribution"], ensure_ascii=False)
    )
    print(
        "[DATASET] 数据划分: "
        + json.dumps(manifest["split_distribution"], ensure_ascii=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
