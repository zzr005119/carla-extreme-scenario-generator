import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.physical_constraints import (
    PHYSICAL_CONSTRAINTS_VERSION,
    build_physical_constraint_report,
    evaluate_physical_constraints,
    load_json_records,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = PROJECT_ROOT / "data" / "scenarios" / "seed_v1" / "example_record.json"
SEED_JSONL = PROJECT_ROOT / "data" / "scenarios" / "seed_v1" / "scenarios.jsonl"


class PhysicalConstraintTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_valid_record_returns_explainable_metrics(self):
        result = evaluate_physical_constraints(self.record)

        self.assertTrue(result["valid"])
        self.assertEqual(result["version"], PHYSICAL_CONSTRAINTS_VERSION)
        self.assertGreater(result["metrics"]["pedestrian_crossing_time_s"], 0.0)
        self.assertIn("lead_braking_demand_index", result["metrics"])

    def test_crossing_after_scene_end_has_failure_reason(self):
        invalid = copy.deepcopy(self.record)
        invalid["scenario"]["duration_seconds"] = 10.0
        invalid["pedestrian"]["trigger_seconds"] = 9.5

        result = evaluate_physical_constraints(invalid)

        self.assertFalse(result["valid"])
        self.assertIn("crossing_after_scene_end", {item["code"] for item in result["errors"]})

    def test_nominal_overlap_is_warning_not_invalid(self):
        risky = copy.deepcopy(self.record)
        risky["lead_vehicle"]["initial_distance_m"] = 12.0
        risky["lead_vehicle"]["brake_trigger_seconds"] = 4.0

        result = evaluate_physical_constraints(risky)

        self.assertTrue(result["valid"])
        self.assertIn("nominal_overlap_at_brake", {item["code"] for item in result["warnings"]})

    def test_seed_dataset_report_preserves_record_count(self):
        records = load_json_records(SEED_JSONL)
        report = build_physical_constraint_report(records, source=SEED_JSONL)

        self.assertEqual(report["record_count"], 256)
        self.assertEqual(report["invalid_count"], 0)
        self.assertGreater(report["warning_count"], 0)
        self.assertEqual(len(report["results"]), 256)

    def test_missing_field_is_reported(self):
        invalid = copy.deepcopy(self.record)
        del invalid["pedestrian"]["speed_mps"]

        result = evaluate_physical_constraints(invalid)

        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "missing_or_nonfinite")


if __name__ == "__main__":
    unittest.main()
