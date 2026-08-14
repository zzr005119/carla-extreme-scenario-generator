"""训练并选择风险条件 GMM 对照基线。"""

import argparse
import json
import os
import sys
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_features import load_jsonl  # noqa: E402
from models.conditional_gmm import ConditionalDiagonalGMM  # noqa: E402


def parse_components(value):
    components = sorted({int(item.strip()) for item in value.split(",") if item.strip()})
    if not components or components[0] < 1:
        raise argparse.ArgumentTypeError("--components 必须是正整数列表")
    return components


def parse_args():
    parser = argparse.ArgumentParser(description="训练条件 GMM 场景生成基线")
    data_dir = os.path.join(PROJECT_ROOT, "data", "scenarios", "seed_v1")
    parser.add_argument("--train", default=os.path.join(data_dir, "train.jsonl"))
    parser.add_argument(
        "--validation",
        default=os.path.join(data_dir, "validation.jsonl"),
    )
    parser.add_argument("--test", default=os.path.join(data_dir, "test.jsonl"))
    parser.add_argument("--components", type=parse_components, default=[1, 2, 3])
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument(
        "--output",
        default=os.path.join(PROJECT_ROOT, "artifacts", "gmm", "seed_v1.json"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    train_records = load_jsonl(os.path.abspath(args.train))
    validation_records = load_jsonl(os.path.abspath(args.validation))
    test_records = load_jsonl(os.path.abspath(args.test))
    candidates = []
    for component_count in args.components:
        model = ConditionalDiagonalGMM(
            n_components=component_count,
            random_seed=args.seed,
        ).fit(train_records)
        candidate = {
            "components": component_count,
            "model": model,
            "train_mean_log_likelihood": model.mean_log_likelihood(train_records),
            "validation_mean_log_likelihood": model.mean_log_likelihood(
                validation_records
            ),
        }
        candidates.append(candidate)
        print(
            f"[GMM] k={component_count} | "
            f"train={candidate['train_mean_log_likelihood']:.6f} | "
            f"validation={candidate['validation_mean_log_likelihood']:.6f}"
        )

    best = max(candidates, key=lambda item: item["validation_mean_log_likelihood"])
    test_score = best["model"].mean_log_likelihood(test_records)
    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    summary = {
        "selected_by": "validation_mean_log_likelihood",
        "selected_components": best["components"],
        "train_records": len(train_records),
        "validation_records": len(validation_records),
        "test_records": len(test_records),
        "train_mean_log_likelihood": best["train_mean_log_likelihood"],
        "validation_mean_log_likelihood": best["validation_mean_log_likelihood"],
        "test_mean_log_likelihood": test_score,
        "random_seed": args.seed,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "candidates": [
            {
                key: value
                for key, value in candidate.items()
                if key != "model"
            }
            for candidate in candidates
        ],
    }
    best["model"].save(output_path, metadata=summary)
    summary_path = os.path.splitext(output_path)[0] + "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    print(
        f"[GMM] 已选择 k={best['components']} | test={test_score:.6f}"
    )
    print(f"[GMM] 模型: {output_path}")
    print(f"[GMM] 汇总: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
