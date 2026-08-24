"""Create a deterministic train/dev/test plan before CARLA RL training."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.carla_rl_plan import build_multiscene_plan  # noqa: E402


DEFAULT_ENTRIES = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "entries.jsonl"
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "manifest.json"


def parse_args():
    parser = argparse.ArgumentParser(description="生成 CARLA 在线 RL 多场景固定划分计划")
    parser.add_argument("--entries", default=str(DEFAULT_ENTRIES))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=20260824)
    parser.add_argument("--train-fraction", type=float, default=0.6)
    parser.add_argument("--dev-fraction", type=float, default=0.2)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    return parser.parse_args()


def main():
    args = parse_args()
    plan = build_multiscene_plan(
        args.entries,
        args.manifest,
        args.output,
        seed=args.seed,
        fractions={
            "train": args.train_fraction,
            "dev": args.dev_fraction,
            "test": args.test_fraction,
        },
    )
    print(json.dumps({
        "format": plan["format"],
        "plan_sha256": plan["plan_sha256"],
        "counts": plan["counts"],
        "strata": plan["strata"],
        "output": str(Path(args.output).expanduser().resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
