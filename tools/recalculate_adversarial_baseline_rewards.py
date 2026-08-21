"""Recalculate comparison rewards from collected CARLA runtime metadata."""

import argparse
import copy
import json
import os
import sys
from collections import Counter
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import (  # noqa: E402
    EpisodeResult,
    count_reward_events,
    load_agent_config,
)
from core.scenario_validator import load_json  # noqa: E402
from tools.run_adversarial_baseline_carla_plan import (  # noqa: E402
    DEFAULT_AGENT_CONFIG,
    _resolve_plan_path,
    _write_csv,
    _write_json,
    _write_report,
    build_candidate_comparison,
    load_run_plan,
)


def _metadata_for_row(results_dir, row):
    snapshot = row.get("metadata_snapshot_path")
    if snapshot:
        path = snapshot if os.path.isabs(snapshot) else os.path.join(results_dir, snapshot)
        if os.path.isfile(path):
            return load_json(path), os.path.abspath(path)
    path = row.get("metadata_path")
    if path and os.path.isfile(path):
        return load_json(path), os.path.abspath(path)
    raise FileNotFoundError(f"Missing metadata for {row['run_id']}")


def recalculate_rewards(plan_path, results_path, output_dir, agent_config_path):
    plan_path = os.path.abspath(plan_path)
    results_path = os.path.abspath(results_path)
    plan_dir = os.path.dirname(plan_path)
    results_dir = os.path.dirname(results_path)
    plan = load_run_plan(plan_path)
    prior_rows = load_json(results_path)
    if not isinstance(prior_rows, list) or not prior_rows:
        raise ValueError("Runtime results must be a non-empty JSON array")
    plan_runs = {run["run_id"]: run for run in plan["runs"]}
    agent_config = load_agent_config(os.path.abspath(agent_config_path))
    rows = []
    old_rewards = {}

    for prior in prior_rows:
        run_id = prior["run_id"]
        if run_id not in plan_runs:
            raise ValueError(f"Run is not present in plan: {run_id}")
        row = copy.deepcopy(prior)
        metadata, metadata_path = _metadata_for_row(results_dir, row)
        events = metadata.get("events") or []
        row["metadata_reanalysis_path"] = metadata_path
        row["raw_event_count"] = len(events)
        row["event_count"] = count_reward_events(events, agent_config)
        row["collision_observed"] = int(row.get("collision_count") or 0) > 0
        result = copy.deepcopy(row.get("result") or {})
        result["event_count"] = row["event_count"]
        result["collision_count"] = int(row.get("collision_count") or 0)
        row["result"] = result
        old_rewards[run_id] = prior.get("reward")
        row["legacy_reward"] = prior.get("reward")
        row["reward"] = None
        row["reward_breakdown"] = None
        row["risk_delta"] = None
        rows.append(row)

    for pair_id in dict.fromkeys(row["pair_id"] for row in rows):
        pair_rows = [row for row in rows if row["pair_id"] == pair_id]
        baseline_rows = [row for row in pair_rows if row["phase"] == "baseline"]
        if len(baseline_rows) != 1:
            raise ValueError(f"{pair_id} must contain exactly one baseline result")
        baseline_row = baseline_rows[0]
        baseline_run = plan_runs[baseline_row["run_id"]]
        baseline_record = load_json(
            _resolve_plan_path(plan_dir, baseline_run["record_path"])
        )
        baseline_result = EpisodeResult.from_mapping(baseline_row["result"])
        if not baseline_result.successful:
            raise ValueError(f"Baseline did not pass strict acceptance: {pair_id}")
        for row in pair_rows:
            if row["phase"] != "candidate":
                continue
            candidate_run = plan_runs[row["run_id"]]
            candidate_record = load_json(
                _resolve_plan_path(plan_dir, candidate_run["record_path"])
            )
            comparison = build_candidate_comparison(
                baseline_record,
                baseline_result,
                candidate_run,
                candidate_record,
                EpisodeResult.from_mapping(row["result"]),
                agent_config,
            )
            row.update(comparison)

    candidate_rows = [row for row in rows if row["phase"] == "candidate"]
    sign_flip_count = sum(
        old_rewards[row["run_id"]] is not None
        and row["reward"] is not None
        and float(old_rewards[row["run_id"]]) * float(row["reward"]) < 0
        for row in candidate_rows
    )
    pair_ids = list(dict.fromkeys(row["pair_id"] for row in rows))
    accepted_count = sum(row.get("strict_acceptance_passed") is True for row in rows)
    summary = {
        "format": "adversarial_baseline_reward_reanalysis_v2",
        "evidence_kind": "carla_runtime_offline_reanalysis",
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_plan": plan_path,
        "source_results": results_path,
        "reward_comparison_mode": agent_config["reward"]["comparison_mode"],
        "reward_event_types": agent_config["reward"]["event_types"],
        "selected_pair_ids": pair_ids,
        "selected_pair_count": len(pair_ids),
        "selected_run_count": len(rows),
        "strictly_accepted_run_count": accepted_count,
        "candidate_run_count": len(candidate_rows),
        "reward_sign_flip_count": sign_flip_count,
        "strategy_result_counts": dict(
            sorted(Counter(row["strategy"] for row in candidate_rows).items())
        ),
        "risk_method_check_passed": all(
            row.get("risk_method") == "heuristic_v2" for row in rows
        ),
        "carla_version_check_passed": all(
            row.get("carla_client_version") == "0.9.16"
            and row.get("carla_server_version") == "0.9.16"
            for row in rows
        ),
        "runtime_gate_passed": accepted_count == len(rows),
        "runtime_boundary": (
            "Rewards were recalculated from previously collected CARLA runtime "
            "metadata; no new simulation was executed by this command."
        ),
    }
    os.makedirs(output_dir, exist_ok=False)
    _write_json(os.path.join(output_dir, "run_results.json"), rows)
    _write_csv(os.path.join(output_dir, "run_results.csv"), rows)
    _write_json(os.path.join(output_dir, "summary.json"), summary)
    _write_report(os.path.join(output_dir, "report.md"), summary, rows)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Recalculate adversarial baseline rewards from CARLA metadata"
    )
    parser.add_argument("--plan", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--agent-config", default=DEFAULT_AGENT_CONFIG)
    return parser.parse_args()


def main():
    args = parse_args()
    summary = recalculate_rewards(
        args.plan,
        args.results,
        os.path.abspath(args.output_dir),
        args.agent_config,
    )
    print(
        f"[REWARD] candidates={summary['candidate_run_count']} "
        f"sign_flips={summary['reward_sign_flip_count']}",
        flush=True,
    )
    print(f"[RESULT_DIR] {os.path.abspath(args.output_dir)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
