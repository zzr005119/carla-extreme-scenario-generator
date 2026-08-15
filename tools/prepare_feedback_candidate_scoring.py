"""生成同口径候选池并调用反馈候选评分器。"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DATASET = os.path.join(
    PROJECT_ROOT,
    "data",
    "scenarios",
    "risk_feedback_v1",
    "dataset.csv",
)
GENERATORS = ("lhs", "gmm", "cvae")
TARGET_LEVELS = ("high", "critical")
WEATHER_TAGS = {
    "high": "heavy_rain,fog,night,wet_road",
    "critical": "heavy_rain,dense_fog,night,wet_road,strong_wind",
}


def default_output_dir():
    output_root = os.environ.get(
        "PROJECT_OUTPUT_ROOT", os.path.join(PROJECT_ROOT, "output")
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(output_root, "feedback_candidate_scoring_v1", timestamp)


def default_model_path(relative_path):
    model_root = os.environ.get(
        "PROJECT_MODEL_ROOT", os.path.join(PROJECT_ROOT, "artifacts")
    )
    return os.path.join(model_root, relative_path)


def parse_args():
    parser = argparse.ArgumentParser(description="准备反馈候选评分 V1")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", default=default_output_dir())
    parser.add_argument(
        "--gmm-artifact", default=default_model_path(os.path.join("gmm", "seed_v1.json"))
    )
    parser.add_argument(
        "--cvae-artifact",
        default=default_model_path(os.path.join("cvae", "final_seed_v1", "best.pt")),
    )
    parser.add_argument("--pool-size", type=int, default=256)
    parser.add_argument("--max-attempts", type=int, default=4096)
    parser.add_argument("--bootstrap-models", type=int, default=50)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--select-per-channel", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260815)
    return parser.parse_args()


def run_command(command):
    print("[COMMAND] " + " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"命令失败，退出码 {completed.returncode}: {' '.join(command)}"
        )


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    args = parse_args()
    if args.pool_size < args.select_per_channel * len(TARGET_LEVELS):
        raise ValueError("候选池过小，无法支持三通道无重复选择")
    if args.max_attempts < args.pool_size:
        raise ValueError("--max-attempts 不能小于 --pool-size")
    for path in (args.dataset, args.gmm_artifact, args.cvae_artifact):
        if not os.path.isfile(os.path.abspath(path)):
            raise FileNotFoundError(f"缺少输入文件: {os.path.abspath(path)}")

    output_dir = Path(os.path.abspath(args.output_dir))
    candidate_dir = output_dir / "candidate_pools"
    score_dir = output_dir / "scoring"
    candidate_dir.mkdir(parents=True, exist_ok=False)
    score_dir.mkdir(parents=True, exist_ok=False)

    generated_paths = []
    generation_rows = []
    for level_index, level in enumerate(TARGET_LEVELS):
        level_seed = args.seed + level_index
        for model in GENERATORS:
            output_path = candidate_dir / f"{model}_{level}.jsonl"
            command = [
                sys.executable,
                os.path.join(PROJECT_ROOT, "tools", "generate_with_model.py"),
                "--model",
                model,
                "--risk",
                level,
                "--weather-tags",
                WEATHER_TAGS[level],
                "--count",
                str(args.pool_size),
                "--max-attempts",
                str(args.max_attempts),
                "--seed",
                str(level_seed),
                "--output",
                str(output_path),
            ]
            if model == "gmm":
                command.extend(["--artifact", os.path.abspath(args.gmm_artifact)])
            elif model == "cvae":
                command.extend(["--artifact", os.path.abspath(args.cvae_artifact)])
            run_command(command)
            generated_paths.append(str(output_path))
            generation_rows.append(
                {
                    "generator": model,
                    "target_risk_level": level,
                    "seed": level_seed,
                    "weather_tags": WEATHER_TAGS[level].split(","),
                    "candidate_count": args.pool_size,
                    "path": str(output_path),
                }
            )

    score_command = [
        sys.executable,
        os.path.join(PROJECT_ROOT, "analysis", "score_feedback_candidates.py"),
        "--dataset",
        os.path.abspath(args.dataset),
        "--output-dir",
        str(score_dir),
        "--bootstrap-models",
        str(args.bootstrap_models),
        "--n-estimators",
        str(args.n_estimators),
        "--select-per-channel",
        str(args.select_per_channel),
        "--random-state",
        str(args.seed),
    ]
    for generated_path in generated_paths:
        score_command.extend(["--candidates", generated_path])
    run_command(score_command)

    manifest = {
        "format": "feedback_candidate_scoring_run_v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": sys.executable,
        "dataset": os.path.abspath(args.dataset),
        "gmm_artifact": os.path.abspath(args.gmm_artifact),
        "cvae_artifact": os.path.abspath(args.cvae_artifact),
        "pool_size_per_generator_target": args.pool_size,
        "target_levels": list(TARGET_LEVELS),
        "candidate_count": args.pool_size * len(GENERATORS) * len(TARGET_LEVELS),
        "bootstrap_models": args.bootstrap_models,
        "n_estimators": args.n_estimators,
        "select_per_generator_channel": args.select_per_channel,
        "random_seed": args.seed,
        "generation": generation_rows,
        "scoring_directory": str(score_dir),
    }
    write_json(output_dir / "run_manifest.json", manifest)
    print(f"[DONE] 反馈候选评分目录: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
