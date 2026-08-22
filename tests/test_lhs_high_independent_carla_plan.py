import json
import os
import tempfile
import unittest

from core.scenario_validator import load_json
from tools.prepare_lhs_high_independent_carla_plan import (
    load_plan_config,
    prepare_plan,
)
from tools.run_adversarial_baseline_carla_plan import (
    load_run_plan,
    select_pair_ids,
)


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class LhsHighIndependentPlanTests(unittest.TestCase):
    def test_config_and_records_are_frozen_three_candidate_boundary(self):
        config = load_plan_config()
        self.assertEqual(config["expected_sample_ids"], [
            "lhs_high_20260817_0203",
            "lhs_high_20260817_0022",
            "lhs_high_20260817_0041",
        ])

    def test_prepare_plan_emits_independent_runs_without_baselines(self):
        config = load_plan_config()
        with tempfile.TemporaryDirectory() as directory:
            plan_root = os.path.join(directory, "plan")
            runtime_root = os.path.join(directory, "runtime")
            summary = prepare_plan(
                config,
                plan_root,
                runtime_root,
                traffic_manager_port=8100,
                validate_runner=False,
            )
            plan = load_run_plan(os.path.join(plan_root, "run_plan.json"))
            self.assertEqual(summary["independent_run_count"], 3)
            self.assertEqual(plan["format"], "lhs_high_independent_carla_run_plan_v1")
            self.assertEqual(len(plan["runs"]), 3)
            self.assertTrue(all(row["phase"] == "independent" for row in plan["runs"]))
            self.assertEqual(
                select_pair_ids(plan),
                [
                    "lhs_high_boundary_v1_01",
                    "lhs_high_boundary_v1_02",
                    "lhs_high_boundary_v1_03",
                ],
            )
            self.assertFalse(any(row["phase"] == "baseline" for row in plan["runs"]))
            for row in plan["runs"]:
                record = load_json(os.path.join(plan_root, row["record_path"]))
                self.assertEqual(record["sample_id"], row["sample_id"])
                self.assertTrue(os.path.isfile(os.path.join(plan_root, row["config_path"])))

    def test_plan_round_trip_keeps_boundary_metadata(self):
        config = load_plan_config()
        with tempfile.TemporaryDirectory() as directory:
            plan_root = os.path.join(directory, "plan")
            prepare_plan(config, plan_root, os.path.join(directory, "runtime"), validate_runner=False)
            manifest_path = os.path.join(plan_root, "candidate_manifest.jsonl")
            with open(manifest_path, "r", encoding="utf-8") as file:
                rows = [json.loads(line) for line in file if line.strip()]
            self.assertEqual(rows[1]["selection_metadata"]["reason"], "near_critical_boundary")
            self.assertGreater(float(rows[1]["selection_metadata"]["collision_boundary_score"]), 0.5)


if __name__ == "__main__":
    unittest.main()
