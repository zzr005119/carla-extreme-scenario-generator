"""Audit a completed CARLA RL training directory before the next stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 JSON: {path}") from exc


_EPISODE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_episode_id(episode_id):
    if episode_id is None:
        return None
    episode_id = str(episode_id).strip()
    if (
        episode_id in {".", ".."}
        or not episode_id
        or not _EPISODE_ID_RE.fullmatch(episode_id)
    ):
        raise ValueError(
            "episode_id 只能包含 ASCII 字母、数字、点、下划线和短横线"
        )
    return episode_id


def audit_training(
    output_root,
    expected_steps,
    expected_algorithm="SAC",
    episode_id=None,
    require_continuity=False,
):
    root = Path(output_root).expanduser().resolve()
    episode_id = _validate_episode_id(episode_id)
    audit_scope = {
        "mode": "episode" if episode_id else "all_episodes",
        "episode_id": episode_id,
    }
    checks = []

    def check(name, passed, actual=None, expected=None):
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "actual": actual,
                "expected": expected,
            }
        )

    summary_path = root / "rl_training_summary.json"
    run_manifest_path = root / "run_manifest.json"
    checkpoint_manifest_path = root / "checkpoint_manifest.json"
    check("training_summary_exists", summary_path.is_file(), str(summary_path), True)
    check("run_manifest_exists", run_manifest_path.is_file(), str(run_manifest_path), True)
    check(
        "checkpoint_manifest_exists",
        checkpoint_manifest_path.is_file(),
        str(checkpoint_manifest_path),
        True,
    )
    if not all(item["passed"] for item in checks):
        return _result(
            root, expected_steps, expected_algorithm, checks, [], audit_scope
        )

    summary = _load_json(summary_path)
    run_manifest = _load_json(run_manifest_path)
    checkpoint_manifest = _load_json(checkpoint_manifest_path)
    check("training_status", summary.get("status") == "completed", summary.get("status"), "completed")
    check("run_manifest_status", run_manifest.get("status") == "completed", run_manifest.get("status"), "completed")
    check(
        "algorithm",
        summary.get("algorithm") == expected_algorithm.upper(),
        summary.get("algorithm"),
        expected_algorithm.upper(),
    )
    check(
        "trained_num_timesteps",
        int(summary.get("trained_num_timesteps", -1)) == int(expected_steps),
        summary.get("trained_num_timesteps"),
        int(expected_steps),
    )
    model_path = Path(str(summary.get("model_path") or ""))
    check("final_model_exists", model_path.is_file(), str(model_path), True)
    sampler = summary.get("sampler_snapshot") or {}
    check(
        "training_split_only",
        sampler.get("selected_splits") == ["train"],
        sampler.get("selected_splits"),
        ["train"],
    )
    checkpoints = checkpoint_manifest.get("checkpoints") or []
    check("checkpoint_count_positive", len(checkpoints) > 0, len(checkpoints), ">0")
    check(
        "all_checkpoints_exist",
        bool(checkpoints) and all(Path(str(item.get("path") or "")).is_file() for item in checkpoints),
        sum(Path(str(item.get("path") or "")).is_file() for item in checkpoints),
        len(checkpoints),
    )
    check(
        "last_checkpoint_steps",
        bool(checkpoints) and int(checkpoints[-1].get("trained_num_timesteps", -1)) == int(expected_steps),
        checkpoints[-1].get("trained_num_timesteps") if checkpoints else None,
        int(expected_steps),
    )
    continuity_required = bool(require_continuity) or checkpoint_manifest.get(
        "format"
    ) == "carla_online_rl_checkpoint_manifest_v2"
    if continuity_required:
        check(
            "checkpoint_continuity_format",
            checkpoint_manifest.get("format")
            == "carla_online_rl_checkpoint_manifest_v2",
            checkpoint_manifest.get("format"),
            "carla_online_rl_checkpoint_manifest_v2",
        )
        continuity_rows = []
        for item in checkpoints:
            artifacts = item.get("artifacts") or {}
            artifact_checks = {}
            for name in ("model", "replay_buffer", "sampler_state"):
                artifact = artifacts.get(name) or {}
                required = bool(artifact.get("required"))
                path = Path(str(artifact.get("path") or ""))
                exists = path.is_file() if required else True
                artifact_checks[name] = {
                    "required": required,
                    "path": str(path) if required else None,
                    "exists": exists,
                }
            sampler_check = artifact_checks["sampler_state"]
            sampler_format_valid = True
            if sampler_check["required"] and sampler_check["exists"]:
                try:
                    sampler_format_valid = (
                        _load_json(sampler_check["path"]).get("format")
                        == "carla_online_rl_sampler_state_v2"
                    )
                except RuntimeError:
                    sampler_format_valid = False
            expected_replay = expected_algorithm.upper() == "SAC"
            expected_sampler = summary.get("scenario_plan_sha256") is not None
            continuity_rows.append(
                {
                    "trained_num_timesteps": item.get("trained_num_timesteps"),
                    "manifest_complete": item.get("continuity_complete") is True,
                    "expected_replay_buffer": expected_replay,
                    "expected_sampler_state": expected_sampler,
                    "artifact_checks": artifact_checks,
                    "sampler_format_valid": sampler_format_valid,
                    "passed": (
                        item.get("continuity_complete") is True
                        and artifact_checks["model"]["required"]
                        and artifact_checks["model"]["exists"]
                        and artifact_checks["replay_buffer"]["required"]
                        == expected_replay
                        and artifact_checks["replay_buffer"]["exists"]
                        and artifact_checks["sampler_state"]["required"]
                        == expected_sampler
                        and artifact_checks["sampler_state"]["exists"]
                        and sampler_format_valid
                    ),
                }
            )
        check(
            "checkpoint_resume_continuity",
            bool(continuity_rows) and all(row["passed"] for row in continuity_rows),
            continuity_rows,
            "all checkpoint model/replay/sampler artifacts complete",
        )

    execution_root = root / "episodes"
    if episode_id:
        scoped_root = execution_root / episode_id
        check("episode_scope_exists", scoped_root.is_dir(), str(scoped_root), True)
        execution_paths = (
            sorted(scoped_root.rglob("execution_result.json"))
            if scoped_root.is_dir()
            else []
        )
        audit_scope["execution_root"] = str(scoped_root)
    else:
        execution_paths = sorted(execution_root.rglob("execution_result.json"))
        audit_scope["execution_root"] = str(execution_root)

    execution_rows = []
    for path in execution_paths:
        payload = _load_json(path)
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        acceptance = payload.get("acceptance") or {}
        relative_parts = path.relative_to(root).parts
        row_episode_id = (
            relative_parts[1]
            if len(relative_parts) > 2 and relative_parts[0] == "episodes"
            else None
        )
        execution_rows.append(
            {
                "path": str(path),
                "episode_id": row_episode_id,
                "status": result.get("status"),
                "run_valid": result.get("run_valid"),
                "strict_acceptance_passed": result.get("strict_acceptance_passed"),
                "carla_service_healthy": result.get("carla_service_healthy"),
                "carla_client_version": acceptance.get("carla_client_version"),
                "carla_server_version": acceptance.get("carla_server_version"),
            }
        )
    check("carla_execution_count_positive", len(execution_rows) > 0, len(execution_rows), ">0")
    check(
        "all_executions_strict",
        bool(execution_rows)
        and all(
            row["status"] == "completed"
            and row["run_valid"] is True
            and row["strict_acceptance_passed"] is True
            and row["carla_service_healthy"] is True
            for row in execution_rows
        ),
        sum(
            row["status"] == "completed"
            and row["run_valid"] is True
            and row["strict_acceptance_passed"] is True
            and row["carla_service_healthy"] is True
            for row in execution_rows
        ),
        len(execution_rows),
    )
    version_rows = [
        row for row in execution_rows
        if row["carla_client_version"] is not None or row["carla_server_version"] is not None
    ]
    check(
        "carla_version_0916",
        len(version_rows) == len(execution_rows)
        and all(
            row["carla_client_version"] == "0.9.16"
            and row["carla_server_version"] == "0.9.16"
            for row in version_rows
        ),
        sum(
            row["carla_client_version"] == "0.9.16"
            and row["carla_server_version"] == "0.9.16"
            for row in version_rows
        ),
        len(execution_rows),
    )
    return _result(
        root,
        expected_steps,
        expected_algorithm,
        checks,
        execution_rows,
        audit_scope,
    )


def _result(
    root,
    expected_steps,
    expected_algorithm,
    checks,
    execution_rows,
    audit_scope,
):
    passed = all(item["passed"] for item in checks)
    return {
        "format": "carla_online_rl_training_quality_gate_v2",
        "status": "passed" if passed else "failed",
        "output_root": str(root),
        "expected_algorithm": expected_algorithm.upper(),
        "expected_steps": int(expected_steps),
        "audit_scope": audit_scope,
        "check_count": len(checks),
        "passed_check_count": sum(item["passed"] for item in checks),
        "failed_checks": [item["name"] for item in checks if not item["passed"]],
        "checks": checks,
        "execution_result_count": len(execution_rows),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="审计 CARLA RL 训练输出")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--expected-steps", type=int, required=True)
    parser.add_argument("--expected-algorithm", choices=("PPO", "SAC"), default="SAC")
    parser.add_argument(
        "--episode-id",
        help="只审计 episodes/<episode-id> 下的运行；默认审计整个输出目录",
    )
    parser.add_argument(
        "--require-continuity",
        action="store_true",
        help="要求 V2 checkpoint 模型/replay buffer/sampler state 三件套",
    )
    parser.add_argument("--output")
    return parser.parse_args()


def main():
    args = parse_args()
    result = audit_training(
        args.output_root,
        args.expected_steps,
        args.expected_algorithm,
        args.episode_id,
        args.require_continuity,
    )
    output = Path(args.output).expanduser().resolve() if args.output else Path(args.output_root).expanduser().resolve() / "quality_gate.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
