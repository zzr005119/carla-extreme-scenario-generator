"""使用 LHS、条件 GMM、C-TabCVAE 或表格 Diffusion 生成可校验场景记录。"""

import argparse
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime
from time import perf_counter

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scenario_features import (  # noqa: E402
    FEATURE_NAMES,
    RISK_LEVELS,
    WEATHER_TAGS,
    build_generated_record,
    condition_vector,
    denormalize_vector,
    normalize_vector,
)
from models.conditional_gmm import ConditionalDiagonalGMM  # noqa: E402
from tools.generate_seed_dataset import RANGES, latin_hypercube  # noqa: E402


def parse_tags(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args():
    parser = argparse.ArgumentParser(description="统一参数级场景生成入口")
    parser.add_argument(
        "--model", choices=("lhs", "gmm", "cvae", "diffusion"), required=True
    )
    parser.add_argument("--artifact", help="GMM JSON 或 CVAE PT 模型路径")
    parser.add_argument("--risk", choices=RISK_LEVELS, required=True)
    parser.add_argument("--weather-tags", type=parse_tags, default=[])
    parser.add_argument("--count", type=int, default=16)
    parser.add_argument("--max-attempts", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument(
        "--output",
        default=os.path.join(PROJECT_ROOT, "output", "generated_scenarios.jsonl"),
    )
    return parser.parse_args()


def lhs_candidates(risk, count, seed):
    designs = latin_hypercube(count, RANGES[risk], random.Random(seed))
    vectors = []
    for design in designs:
        ordered = [design[name.split(".", 1)[1]] for name in FEATURE_NAMES]
        vectors.append(normalize_vector(ordered, clip=True))
    return np.asarray(vectors, dtype=np.float64)


def project_to_design_range(risk, vectors):
    """Project a generated pool into the declared risk-level feasible box.

    Diffusion is the only new comparison model and uses this explicit
    constraint-aware post-processing.  The projection is parameter-level
    validity, not a measured CARLA risk label.
    """
    values = denormalize_vector(np.asarray(vectors, dtype=np.float64), clip=True)
    ranges = RANGES[risk]
    for index, name in enumerate(FEATURE_NAMES):
        low, high = ranges[name.split(".", 1)[1]]
        values[:, index] = np.clip(values[:, index], low, high)
    return normalize_vector(values, clip=True)


def load_cvae(path):
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "生成 CVAE 场景需要 PyTorch，请先安装 requirements-models.txt"
        ) from exc
    from models.conditional_tabular_cvae import ConditionalTabularVAE

    checkpoint = torch.load(path, map_location="cpu")
    if checkpoint.get("format") != "conditional_tabular_cvae_v1":
        raise ValueError("不支持的 CVAE 模型格式")
    if tuple(checkpoint.get("feature_names", ())) != FEATURE_NAMES:
        raise ValueError("CVAE 特征定义与当前代码不一致")
    model = ConditionalTabularVAE(**checkpoint["model_config"])
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return torch, model


def load_diffusion(path):
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "生成 Diffusion 场景需要 PyTorch，请先安装 requirements-models.txt"
        ) from exc
    from models.conditional_tabular_diffusion import ConditionalTabularDiffusion

    checkpoint = torch.load(path, map_location="cpu")
    if checkpoint.get("format") != "conditional_tabular_diffusion_v1":
        raise ValueError("不支持的 Diffusion 模型格式")
    if tuple(checkpoint.get("feature_names", ())) != FEATURE_NAMES:
        raise ValueError("Diffusion 特征定义与当前代码不一致")
    model = ConditionalTabularDiffusion(**checkpoint["model_config"])
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return torch, model


def main():
    args = parse_args()
    started_at = perf_counter()
    if args.count < 1:
        raise ValueError("--count 必须大于 0")
    if args.max_attempts < args.count:
        raise ValueError("--max-attempts 不能小于 --count")
    if args.model in ("gmm", "cvae", "diffusion") and not args.artifact:
        raise ValueError(f"--model {args.model} 必须提供 --artifact")
    condition_vector(args.risk, args.weather_tags)

    gmm = None
    torch = None
    cvae = None
    diffusion = None
    if args.model == "gmm":
        gmm = ConditionalDiagonalGMM.load(os.path.abspath(args.artifact))
    elif args.model == "cvae":
        torch, cvae = load_cvae(os.path.abspath(args.artifact))
    elif args.model == "diffusion":
        torch, diffusion = load_diffusion(os.path.abspath(args.artifact))

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    accepted = []
    rejection_reasons = Counter()
    attempted_count = 0
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    if args.model == "lhs":
        pool = lhs_candidates(args.risk, args.max_attempts, args.seed)
    elif args.model == "gmm":
        pool = gmm.sample(args.risk, args.max_attempts, args.seed)
    elif args.model == "cvae":
        conditions = np.repeat(
            condition_vector(args.risk, args.weather_tags)[None, :],
            args.max_attempts,
            axis=0,
        ).astype(np.float32)
        generator = torch.Generator().manual_seed(args.seed)
        with torch.no_grad():
            pool = cvae.sample(
                torch.from_numpy(conditions),
                generator=generator,
            ).cpu().numpy()
    else:
        conditions = np.repeat(
            condition_vector(args.risk, args.weather_tags)[None, :],
            args.max_attempts,
            axis=0,
        ).astype(np.float32)
        generator = torch.Generator().manual_seed(args.seed)
        with torch.no_grad():
            pool = diffusion.sample(
                torch.from_numpy(conditions),
                generator=generator,
            ).cpu().numpy()
        pool = project_to_design_range(args.risk, pool)

    for attempt, vector in enumerate(pool, 1):
        attempted_count = attempt
        sample_id = f"{args.model}_{args.risk}_{args.seed}_{len(accepted) + 1:04d}"
        try:
            record = build_generated_record(
                vector,
                args.risk,
                args.weather_tags,
                sample_id,
                generator={
                    "lhs": "balanced_latin_hypercube_v1",
                    "gmm": "conditional_diagonal_gmm_v1",
                    "cvae": "conditional_tabular_cvae_v1",
                    "diffusion": "conditional_tabular_diffusion_v1",
                }[args.model],
                generator_seed=args.seed,
                source_kind=(
                    "synthetic_parameter_design"
                    if args.model == "lhs"
                    else "model_generated"
                ),
                traffic_manager_seed=(args.seed + attempt) % 2147483648,
                created_at=created_at,
            )
        except (ValueError, KeyError) as exc:
            rejection_reasons[str(exc).splitlines()[0]] += 1
            continue
        accepted.append(record)
        if len(accepted) >= args.count:
            break

    with open(output_path, "w", encoding="utf-8") as file:
        for record in accepted:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    summary = {
        "model": args.model,
        "artifact": os.path.abspath(args.artifact) if args.artifact else None,
        "target_risk_level": args.risk,
        "requested_weather_tags": args.weather_tags,
        "requested_count": args.count,
        "accepted_count": len(accepted),
        "attempted_count": attempted_count,
        "acceptance_rate": len(accepted) / max(1, attempted_count),
        "complete": len(accepted) == args.count,
        "rejection_reasons": dict(rejection_reasons.most_common()),
        "postprocessing": (
            "risk_level_design_range_projection_v1"
            if args.model == "diffusion"
            else None
        ),
        "random_seed": args.seed,
        "created_at": created_at,
        "output": output_path,
        "elapsed_seconds": perf_counter() - started_at,
    }
    summary["accepted_sample_latency_ms"] = (
        1000.0 * summary["elapsed_seconds"] / max(1, len(accepted))
    )
    summary_path = os.path.splitext(output_path)[0] + "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    print(
        f"[GENERATE] model={args.model} | accepted={len(accepted)}/{args.count} | "
        f"attempts={summary['attempted_count']}"
    )
    print(f"[GENERATE] 场景: {output_path}")
    print(f"[GENERATE] 汇总: {summary_path}")
    if len(accepted) != args.count:
        print("[GENERATE] 未达到请求数量，请检查汇总中的拒绝原因")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
