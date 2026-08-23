"""Run the small offline Diffusion-vs-baselines comparison.

The command produces ignored artifacts and a lightweight evaluation report. It
never starts CARLA and never writes observed-risk values.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("low", "medium", "high", "critical")
MODELS = ("lhs", "gmm", "cvae", "diffusion")


def parse_args():
    parser = argparse.ArgumentParser(description="运行四生成器小规模离线对照")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "artifacts" / "diffusion_comparison_v1"),
    )
    parser.add_argument("--count-per-level", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20260900)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument(
        "--diffusion-artifact",
        help="已有 Diffusion 权重；未提供时在输出目录训练一份小模型",
    )
    parser.add_argument(
        "--gmm-artifact",
        default=str(PROJECT_ROOT / "artifacts" / "gmm" / "seed_v1.json"),
    )
    parser.add_argument(
        "--cvae-artifact",
        default=str(PROJECT_ROOT / "artifacts" / "cvae" / "final_seed_v1" / "best.pt"),
    )
    parser.add_argument(
        "--risk-proxy",
        default=str(PROJECT_ROOT / "artifacts" / "risk_proxy_v1" / "selected_model.joblib"),
    )
    return parser.parse_args()


def run(command, env):
    print("[COMPARE]", " ".join(str(item) for item in command))
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def main():
    args = parse_args()
    if args.count_per_level < 1:
        raise ValueError("--count-per-level 必须大于 0")
    output_dir = Path(args.output_dir).resolve()
    sample_dir = output_dir / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    python = sys.executable
    diffusion_artifact = Path(args.diffusion_artifact).resolve() if args.diffusion_artifact else None
    if diffusion_artifact is None:
        diffusion_artifact = output_dir / "diffusion" / "best.pt"
        run(
            [
                python,
                "training/train_diffusion.py",
                "--device",
                args.device,
                "--epochs",
                str(args.epochs),
                "--output-dir",
                str(diffusion_artifact.parent),
            ],
            env,
        )
    required = {
        "gmm": Path(args.gmm_artifact).resolve(),
        "cvae": Path(args.cvae_artifact).resolve(),
        "diffusion": diffusion_artifact,
    }
    for model, artifact in required.items():
        if not artifact.is_file():
            raise FileNotFoundError(
                f"{model} 模型工件不存在: {artifact}；请先完成对应基线训练"
            )

    inputs = []
    for model_index, model in enumerate(MODELS):
        for level_index, level in enumerate(LEVELS):
            output = sample_dir / f"{model}_{level}.jsonl"
            command = [
                python,
                "tools/generate_with_model.py",
                "--model",
                model,
                "--risk",
                level,
                "--count",
                str(args.count_per_level),
                "--max-attempts",
                str(args.count_per_level * 2),
                "--seed",
                str(args.seed + model_index * 100 + level_index),
                "--output",
                str(output),
            ]
            if model != "lhs":
                command.extend(["--artifact", str(required[model])])
            run(command, env)
            inputs.append(output)

    evaluation_dir = output_dir / "evaluation"
    command = [
        python,
        "analysis/evaluate_generators.py",
        "--reference",
        str(PROJECT_ROOT / "data" / "scenarios" / "seed_v1" / "train.jsonl"),
        "--output-dir",
        str(evaluation_dir),
    ]
    risk_proxy = Path(args.risk_proxy).resolve()
    if risk_proxy.is_file():
        command.extend(["--risk-proxy", str(risk_proxy)])
    command.extend(str(path) for path in inputs)
    run(command, env)
    print(f"[COMPARE] evaluation={evaluation_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
