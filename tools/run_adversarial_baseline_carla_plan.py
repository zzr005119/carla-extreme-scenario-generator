"""Execute and aggregate shared-baseline CARLA comparison plans."""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import (  # noqa: E402
    AdversarialTestAgentV1,
    EpisodeResult,
    canonical_parameter_fingerprint,
    count_reward_events,
    load_agent_config,
)
from core.scenario_validator import load_json, require_valid_scenario  # noqa: E402
from tools.collect_carla_repeatability import collect_row  # noqa: E402
from tools.evaluate_adversarial_baselines import git_state  # noqa: E402


SCENE_RUNNER = os.path.join(
    PROJECT_ROOT,
    "scenes",
    "scene_04_parameterized.py",
)
DEFAULT_AGENT_CONFIG = os.path.join(
    PROJECT_ROOT,
    "configs",
    "adversarial_agent_v1.json",
)
DEFAULT_STRATEGIES = ("fixed", "random", "lhs", "rule_guided_lhs")
SUPPORTED_PLAN_FORMATS = {
    "adversarial_baseline_carla_run_plan_v1",
    "adversarial_policy_carla_run_plan_v1",
    "adversarial_policy_carla_repeat_run_plan_v1",
}


def _write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_csv(path, rows):
    fields = (
        "run_order",
        "pair_id",
        "phase",
        "strategy",
        "run_id",
        "sample_id",
        "execution_disposition",
        "process_returncode",
        "timed_out",
        "status",
        "acceptance_status",
        "strict_acceptance_passed",
        "acceptance_failures",
        "risk_method",
        "risk_score",
        "risk_delta",
        "reward",
        "collision_count",
        "collision_observed",
        "event_count",
        "raw_event_count",
        "sensor_status",
        "rgb_frames",
        "server_status",
        "carla_client_version",
        "carla_server_version",
        "carla_version_match",
        "route_verified",
        "route_both_on_route_rate",
        "route_maximum_ego_deviation_m",
        "route_maximum_lead_deviation_m",
        "run_dir",
        "metadata_path",
        "metadata_snapshot_path",
    )
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fields} for row in rows)


def _relative(base, path):
    return os.path.relpath(path, base).replace("\\", "/")


def _resolve_plan_path(plan_dir, path):
    return path if os.path.isabs(path) else os.path.join(plan_dir, path)


def load_run_plan(path):
    plan = load_json(os.path.abspath(path))
    if plan.get("format") not in SUPPORTED_PLAN_FORMATS:
        raise ValueError("Unsupported adversarial baseline CARLA plan format")
    if not plan.get("runs"):
        raise ValueError("Run plan contains no runs")
    return plan


def select_pair_ids(plan, requested_pair_ids=None, pair_count=None):
    available = []
    for run in sorted(plan["runs"], key=lambda row: int(row["run_order"])):
        pair_id = run["pair_id"]
        if pair_id not in available:
            available.append(pair_id)
    if requested_pair_ids:
        missing = [pair_id for pair_id in requested_pair_ids if pair_id not in available]
        if missing:
            raise ValueError(f"Unknown pair_id: {', '.join(missing)}")
        return list(dict.fromkeys(requested_pair_ids))
    count = 1 if pair_count is None else int(pair_count)
    if count < 1:
        raise ValueError("pair_count must be greater than zero")
    return available[:count]


def _collection_run(run):
    return {
        "run_id": run["run_id"],
        "sample_id": run["sample_id"],
        "target_risk_level": run["target_risk_level"],
        "traffic_manager_seed": run["traffic_manager_seed"],
        "repeat_round": run["run_order"],
        "source": "adversarial_baseline_carla_plan_v1",
        "expected_run_root": run["expected_run_root"],
    }


def _load_metadata(row):
    path = row.get("metadata_path")
    if not path or not os.path.isfile(path):
        return {}
    return load_json(path)


def _result_payload(
    row,
    metadata,
    agent_config=None,
    process_returncode=0,
    timed_out=False,
):
    risk = ((metadata.get("result") or {}).get("risk_evaluation") or {})
    events = metadata.get("events") or []
    collision_count = int(row.get("collision_count") or 0)
    failures = [
        value
        for value in str(row.get("acceptance_failures") or "").split(";")
        if value
    ]
    if timed_out:
        failures.append("scene_timeout")
    if process_returncode not in (None, 0):
        failures.append(f"scene_exit_{process_returncode}")
    strict_passed = (
        process_returncode in (None, 0)
        and not timed_out
        and row.get("acceptance_status") == "completed"
    )
    status = (
        "completed"
        if process_returncode in (None, 0)
        and not timed_out
        and row.get("status") == "completed"
        else "failed"
    )
    return {
        "status": status,
        "observed_risk_score": row.get("risk_score"),
        "observed_risk_level": row.get("observed_risk_level"),
        "risk_method": risk.get("method"),
        "collision_count": collision_count,
        "event_count": count_reward_events(events, agent_config),
        "raw_event_count": len(events),
        "collision_observed": collision_count > 0,
        "run_valid": bool(row.get("runtime_verified")) and status == "completed",
        "strict_acceptance_passed": strict_passed,
        "carla_service_healthy": row.get("server_status") == "healthy",
        "run_dir": row.get("run_dir"),
        "failure_reason": ";".join(dict.fromkeys(failures)) or None,
    }


def _snapshot_metadata(output_dir, run_id, row):
    metadata_path = row.get("metadata_path")
    if not metadata_path or not os.path.isfile(metadata_path):
        return None
    destination = os.path.join(output_dir, "metadata", f"{run_id}.json")
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(metadata_path, destination)
    return _relative(output_dir, destination)


def execute_planned_run(
    run,
    plan_dir,
    output_dir,
    acceptance_requirements,
    traffic_manager_port,
    timeout_seconds,
    agent_config,
    force=False,
):
    collection_run = _collection_run(run)
    existing = collect_row(
        collection_run,
        route_lock_required=True,
        acceptance_requirements=acceptance_requirements,
    )
    process_returncode = 0
    timed_out = False
    disposition = "skipped_existing"
    log_path = os.path.join(output_dir, "logs", f"{run['run_id']}.log")
    if existing.get("acceptance_status") != "completed" or force:
        disposition = "executed"
        config_path = _resolve_plan_path(plan_dir, run["config_path"])
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"Missing CARLA config: {config_path}")
        command = [
            sys.executable,
            "-u",
            SCENE_RUNNER,
            "--config",
            config_path,
            "--traffic-manager-port",
            str(traffic_manager_port),
        ]
        print(f"[RUN] {run['run_id']}", flush=True)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        try:
            completed = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
                env={
                    **os.environ,
                    "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUNBUFFERED": "1",
                },
            )
            process_returncode = completed.returncode
            output = (completed.stdout or "") + (completed.stderr or "")
        except subprocess.TimeoutExpired as exc:
            process_returncode = 124
            timed_out = True
            stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            output = stdout + stderr + f"\n[PLAN] scene timeout after {timeout_seconds} seconds\n"
        with open(log_path, "w", encoding="utf-8") as file:
            file.write(output)
        if output:
            print(output, end="" if output.endswith("\n") else "\n", flush=True)
        existing = collect_row(
            collection_run,
            route_lock_required=True,
            acceptance_requirements=acceptance_requirements,
        )

    metadata = _load_metadata(existing)
    result = _result_payload(
        existing,
        metadata,
        agent_config=agent_config,
        process_returncode=process_returncode,
        timed_out=timed_out,
    )
    snapshot_path = _snapshot_metadata(output_dir, run["run_id"], existing)
    row = {
        **run,
        **existing,
        "execution_disposition": disposition,
        "process_returncode": process_returncode,
        "timed_out": timed_out,
        "status": result["status"],
        "acceptance_status": (
            "completed" if result["strict_acceptance_passed"] else "failed"
        ),
        "strict_acceptance_passed": result["strict_acceptance_passed"],
        "acceptance_failures": result["failure_reason"] or "",
        "risk_method": result["risk_method"],
        "event_count": result["event_count"],
        "raw_event_count": result["raw_event_count"],
        "collision_observed": result["collision_observed"],
        "metadata_snapshot_path": snapshot_path,
        "result": result,
    }
    if disposition == "executed":
        print(
            f"[RESULT] {run['run_id']} acceptance={existing.get('acceptance_status')} "
            f"risk={existing.get('risk_score')} collisions={existing.get('collision_count')}",
            flush=True,
        )
    return row


def build_candidate_comparison(
    baseline_record,
    baseline_result,
    candidate_run,
    candidate_record,
    candidate_result,
    agent_config,
):
    agent = AdversarialTestAgentV1(agent_config)
    agent.reset(baseline_record, baseline_result)
    proposal = agent.propose(candidate_run["selected_action"])
    if not proposal["valid"]:
        raise ValueError(
            f"Planned candidate became invalid: {candidate_run['run_id']}"
        )
    planned_fingerprint = candidate_run.get("candidate_fingerprint")
    record_fingerprint = canonical_parameter_fingerprint(candidate_record)
    if planned_fingerprint and proposal["fingerprint"] != planned_fingerprint:
        raise ValueError(
            f"Candidate action fingerprint mismatch: {candidate_run['run_id']}"
        )
    if planned_fingerprint and record_fingerprint != planned_fingerprint:
        raise ValueError(
            f"Candidate record fingerprint mismatch: {candidate_run['run_id']}"
        )
    transition = agent.record_result(candidate_result).to_dict()
    baseline_score = baseline_result.observed_risk_score
    candidate_score = candidate_result.observed_risk_score
    return {
        "risk_delta": (
            round(candidate_score - baseline_score, 6)
            if baseline_score is not None and candidate_score is not None
            else None
        ),
        "reward": transition["reward"],
        "reward_breakdown": transition["reward_breakdown"],
        "terminated": transition["terminated"],
        "truncated": transition["truncated"],
        "reason": transition["reason"],
    }


def _execution_row(run_result):
    row = dict(run_result)
    row.pop("result", None)
    return row


def _write_report(path, summary, rows):
    lines = [
        "# Adversarial Baseline CARLA Runtime Report V1",
        "",
        f"- Evidence: `{summary['evidence_kind']}`",
        f"- Selected pairs: `{summary['selected_pair_count']}`",
        f"- Planned runs: `{summary['selected_run_count']}`",
        f"- Strictly accepted: `{summary['strictly_accepted_run_count']}`",
        f"- Runtime gate: `{'passed' if summary['runtime_gate_passed'] else 'failed'}`",
        f"- CARLA version check: `{'passed' if summary['carla_version_check_passed'] else 'failed'}`",
        f"- Risk method check: `{'passed' if summary['risk_method_check_passed'] else 'failed'}`",
        "",
        "This is a runtime smoke/comparison result. It does not establish that one strategy is generally superior.",
        "",
        "| Pair | Phase | Strategy | Acceptance | Risk | Delta | Reward | Collisions |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {pair_id} | {phase} | {strategy} | {acceptance} | {risk} | "
            "{delta} | {reward} | {collisions} |".format(
                pair_id=row["pair_id"],
                phase=row["phase"],
                strategy=row.get("strategy") or "shared baseline",
                acceptance=row.get("acceptance_status"),
                risk="" if row.get("risk_score") is None else f"{row['risk_score']:.3f}",
                delta="" if row.get("risk_delta") is None else f"{row['risk_delta']:+.3f}",
                reward="" if row.get("reward") is None else f"{row['reward']:.6f}",
                collisions=row.get("collision_count"),
            )
        )
    lines.extend(
        [
            "",
            "Candidate deltas and rewards are calculated independently against the shared baseline in the same pair.",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines))


def execute_plan(
    plan_path,
    output_dir,
    requested_pair_ids=None,
    pair_count=None,
    agent_config_path=DEFAULT_AGENT_CONFIG,
    traffic_manager_port=None,
    timeout_seconds=240,
    pause_seconds=10.0,
    force=False,
):
    plan_path = os.path.abspath(plan_path)
    plan_dir = os.path.dirname(plan_path)
    plan = load_run_plan(plan_path)
    expected_strategies = tuple(plan["summary"].get("strategy_order") or ())
    if not expected_strategies:
        first_pair_id = select_pair_ids(plan, pair_count=1)[0]
        expected_strategies = tuple(
            run["strategy"]
            for run in sorted(plan["runs"], key=lambda row: int(row["run_order"]))
            if run["pair_id"] == first_pair_id and run["phase"] == "candidate"
        )
    if not expected_strategies:
        expected_strategies = DEFAULT_STRATEGIES
    if not expected_strategies or len(set(expected_strategies)) != len(
        expected_strategies
    ):
        raise ValueError("Run plan strategy_order must be non-empty and unique")
    pair_ids = select_pair_ids(plan, requested_pair_ids, pair_count)
    selected = [
        run
        for run in sorted(plan["runs"], key=lambda row: int(row["run_order"]))
        if run["pair_id"] in pair_ids
    ]
    acceptance = plan["acceptance_requirements"]
    traffic_manager_port = int(
        traffic_manager_port
        or os.environ.get("CARLA_TRAFFIC_MANAGER_PORT")
        or plan["summary"]["traffic_manager_port"]
    )
    agent_config = load_agent_config(os.path.abspath(agent_config_path))
    os.makedirs(output_dir, exist_ok=True)
    state_path = os.path.join(output_dir, "execution_state.json")
    results = []
    pair_summaries = []
    abort_all = False

    def persist(status):
        _write_json(
            state_path,
            {
                "format": "adversarial_baseline_carla_execution_state_v1",
                "status": status,
                "plan_path": plan_path,
                "selected_pair_ids": pair_ids,
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "runs": results,
                "pairs": pair_summaries,
            },
        )

    persist("running")
    for pair_id in pair_ids:
        pair_runs = [run for run in selected if run["pair_id"] == pair_id]
        baseline_runs = [run for run in pair_runs if run["phase"] == "baseline"]
        candidate_runs = [run for run in pair_runs if run["phase"] == "candidate"]
        if len(baseline_runs) != 1:
            raise ValueError(f"{pair_id} must contain exactly one baseline")
        strategies = tuple(run.get("strategy") for run in candidate_runs)
        if strategies != expected_strategies:
            raise ValueError(
                f"{pair_id} strategy order must be {expected_strategies}, got {strategies}"
            )
        baseline_run = baseline_runs[0]
        baseline_record = load_json(
            _resolve_plan_path(plan_dir, baseline_run["record_path"])
        )
        require_valid_scenario(baseline_record)
        baseline_row = execute_planned_run(
            baseline_run,
            plan_dir,
            output_dir,
            acceptance,
            traffic_manager_port,
            timeout_seconds,
            agent_config,
            force=force,
        )
        baseline_row["risk_delta"] = None
        baseline_row["reward"] = None
        baseline_row["reward_breakdown"] = None
        results.append(baseline_row)
        persist("running")
        baseline_result = EpisodeResult.from_mapping(baseline_row["result"])
        pair_summary = {
            "pair_id": pair_id,
            "baseline_run_id": baseline_run["run_id"],
            "candidate_run_ids": [run["run_id"] for run in candidate_runs],
            "status": "running",
        }
        pair_summaries.append(pair_summary)
        if not baseline_result.successful:
            pair_summary["status"] = "baseline_failed"
            pair_summary["failure_reason"] = baseline_result.failure_reason
            abort_all = not baseline_result.carla_service_healthy
            persist("running")
            if abort_all:
                break
            continue

        for candidate_run in candidate_runs:
            candidate_record = load_json(
                _resolve_plan_path(plan_dir, candidate_run["record_path"])
            )
            require_valid_scenario(candidate_record)
            candidate_row = execute_planned_run(
                candidate_run,
                plan_dir,
                output_dir,
                acceptance,
                traffic_manager_port,
                timeout_seconds,
                agent_config,
                force=force,
            )
            candidate_result = EpisodeResult.from_mapping(candidate_row["result"])
            comparison = build_candidate_comparison(
                baseline_record,
                baseline_result,
                candidate_run,
                candidate_record,
                candidate_result,
                agent_config,
            )
            candidate_row.update(comparison)
            results.append(candidate_row)
            persist("running")
            if pause_seconds > 0:
                time.sleep(pause_seconds)
            if not candidate_result.successful and not candidate_result.carla_service_healthy:
                abort_all = True
                break

        pair_rows = [row for row in results if row["pair_id"] == pair_id]
        pair_summary["strictly_accepted_run_count"] = sum(
            row.get("strict_acceptance_passed") is True for row in pair_rows
        )
        pair_summary["executed_run_count"] = len(pair_rows)
        pair_summary["status"] = (
            "accepted"
            if len(pair_rows) == len(pair_runs)
            and pair_summary["strictly_accepted_run_count"] == len(pair_runs)
            else "failed"
        )
        persist("running")
        if abort_all:
            break

    accepted_count = sum(
        row.get("strict_acceptance_passed") is True for row in results
    )
    risk_method_check = bool(results) and all(
        row.get("risk_method") == "heuristic_v2" for row in results
    )
    version_check = bool(results) and all(
        row.get("carla_client_version") == "0.9.16"
        and row.get("carla_server_version") == "0.9.16"
        and row.get("carla_version_match") is True
        for row in results
    )
    runtime_gate = (
        len(results) == len(selected)
        and accepted_count == len(selected)
        and risk_method_check
        and version_check
    )
    strategy_counts = Counter(
        row["strategy"] for row in results if row["phase"] == "candidate"
    )
    summary = {
        "format": "adversarial_baseline_carla_runtime_summary_v1",
        "evidence_kind": "carla_runtime",
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_plan": plan_path,
        "source_git": plan["summary"].get("source_git"),
        "execution_git": git_state(),
        "selected_pair_ids": pair_ids,
        "selected_pair_count": len(pair_ids),
        "selected_run_count": len(selected),
        "collected_run_count": len(results),
        "executed_run_count": sum(
            row["execution_disposition"] == "executed" for row in results
        ),
        "skipped_existing_run_count": sum(
            row["execution_disposition"] == "skipped_existing" for row in results
        ),
        "strictly_accepted_run_count": accepted_count,
        "acceptance_failed_run_count": len(results) - accepted_count,
        "strategy_result_counts": dict(sorted(strategy_counts.items())),
        "strategy_order": list(expected_strategies),
        "risk_method_check_passed": risk_method_check,
        "carla_version_check_passed": version_check,
        "runtime_gate_passed": runtime_gate,
        "aborted_for_service_health": abort_all,
        "runtime_boundary": (
            "Measured rewards are single-pair runtime observations and do not prove "
            "general strategy superiority or RL policy effectiveness."
        ),
        "artifacts": {
            "run_results_json": "run_results.json",
            "run_results_csv": "run_results.csv",
            "pair_summaries_json": "pair_summaries.json",
            "report_markdown": "report.md",
            "execution_state_json": "execution_state.json",
        },
    }
    flat_rows = [_execution_row(row) for row in results]
    _write_json(os.path.join(output_dir, "run_results.json"), results)
    _write_csv(os.path.join(output_dir, "run_results.csv"), flat_rows)
    _write_json(os.path.join(output_dir, "pair_summaries.json"), pair_summaries)
    _write_json(os.path.join(output_dir, "summary.json"), summary)
    _write_report(os.path.join(output_dir, "report.md"), summary, flat_rows)
    persist("completed" if runtime_gate else "failed")
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Execute shared-baseline CARLA comparison pairs"
    )
    parser.add_argument("--plan", required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--pair-id", action="append", dest="pair_ids")
    selection.add_argument("--pair-count", type=int)
    parser.add_argument("--output-dir")
    parser.add_argument("--agent-config", default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--traffic-manager-port", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--pause-seconds", type=float, default=10.0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    plan_path = os.path.abspath(args.plan)
    output_dir = os.path.abspath(
        args.output_dir or os.path.join(os.path.dirname(plan_path), "execution")
    )
    summary = execute_plan(
        plan_path,
        output_dir,
        requested_pair_ids=args.pair_ids,
        pair_count=args.pair_count,
        agent_config_path=args.agent_config,
        traffic_manager_port=args.traffic_manager_port,
        timeout_seconds=args.timeout_seconds,
        pause_seconds=args.pause_seconds,
        force=args.force,
    )
    print(
        f"[SUMMARY] accepted={summary['strictly_accepted_run_count']}/"
        f"{summary['selected_run_count']} gate={summary['runtime_gate_passed']}",
        flush=True,
    )
    print(f"[RESULT_DIR] {output_dir}", flush=True)
    return 0 if summary["runtime_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
