"""Run the P4 boundary demo and write one JSON-safe evidence manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.differentiable_closed_loop import (  # noqa: E402
    DifferentiableLoopConfig,
    build_p4_boundary_manifest,
)
from core.physical_constraints import build_physical_constraint_report, load_json_records  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="P4 可微运动学代理与 PyBullet 离散校验边界演示")
    parser.add_argument(
        "--output",
        default="artifacts/p4_differentiable_boundary_v1/manifest.json",
        help="JSON manifest 输出路径",
    )
    parser.add_argument("--horizon", type=int, default=32)
    parser.add_argument(
        "--profile",
        choices=("zero", "closing", "alternating"),
        default="closing",
        help="动作序列：零动作、持续加速逼近或交替控制",
    )
    parser.add_argument(
        "--record",
        default="data/scenarios/seed_v1/example_record.json",
        help="用于独立硬约束质量门的 JSON/JSONL 记录；传空字符串可跳过",
    )
    return parser.parse_args()


def build_actions(horizon, profile):
    if profile == "zero":
        return torch.zeros(horizon)
    if profile == "closing":
        return torch.full((horizon,), 4.0)
    values = torch.tensor([4.0 if index % 2 == 0 else -4.0 for index in range(horizon)])
    return values


def main():
    args = parse_args()
    config = DifferentiableLoopConfig(horizon=args.horizon)
    hard_report = None
    if args.record:
        record_path = (PROJECT_ROOT / args.record).resolve()
        hard_report = build_physical_constraint_report(
            load_json_records(record_path), source=record_path
        )
    manifest = build_p4_boundary_manifest(
        build_actions(args.horizon, args.profile),
        config,
        hard_constraint_report=hard_report,
    )
    manifest["action_profile"] = args.profile
    manifest["hard_constraint_source"] = str((PROJECT_ROOT / args.record).resolve()) if args.record else None
    output = (PROJECT_ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[P4] quality_gate={manifest['quality_gate']} "
        f"loss={manifest['torch_surrogate']['loss']:.6f} "
        f"min_gap_m={manifest['torch_surrogate']['min_gap_m']:.3f}"
    )
    print(f"[P4] manifest={output}")
    return 0 if manifest["quality_gate"] != "blocked_hard_constraint" else 1


if __name__ == "__main__":
    raise SystemExit(main())
