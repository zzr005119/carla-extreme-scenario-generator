import json
import tempfile
import unittest
from pathlib import Path

from tools.measure_stage5_metrics import (
    condition_coverage,
    generation_throughput,
    testing_cost,
)


class Stage5MetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stage5-metrics-")
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_json(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_generation_throughput_uses_recorded_elapsed_time(self):
        path = self.write_json(
            "summary.json",
            {"accepted_count": 8, "attempted_count": 10, "elapsed_seconds": 2.0},
        )
        result = generation_throughput([path])
        self.assertEqual(result["accepted_records_per_second"], 4.0)
        self.assertEqual(result["acceptance_rate"], 0.8)

    def test_testing_cost_requires_strict_acceptance(self):
        path = self.write_json(
            "metadata.json",
            {
                "carla_versions": {"match": True},
                "sensor_pipeline": {"status": "completed"},
                "server_health": {"status": "healthy"},
                "cleanup": {"status": "completed"},
                "route_control": {"enabled": False},
                "result": {"status": "completed", "wall_duration_seconds": 5.0},
            },
        )
        result = testing_cost([path])
        self.assertEqual(result["strictly_accepted_count"], 1)
        self.assertEqual(result["wall_duration_seconds_mean"], 5.0)

    def test_coverage_uses_explicit_condition_signatures(self):
        reference = self.root / "reference.jsonl"
        reference.write_text(
            "\n".join(
                json.dumps(
                    {
                        "conditions": {
                            "target_risk_level": level,
                            "weather_tags": [weather],
                            "hazard_tags": ["lead_vehicle_braking"],
                        }
                    }
                )
                for level, weather in (("high", "night"), ("critical", "heavy_rain"))
            )
            + "\n",
            encoding="utf-8",
        )
        candidate = self.write_json(
            "candidate.json",
            {
                "labels": {
                    "target_risk_levels": ["high"],
                    "weather_tags": ["night"],
                    "hazard_tags": ["lead_vehicle_braking"],
                }
            },
        )
        result = condition_coverage([reference], [candidate])
        self.assertEqual(result["reference_signature_count"], 2)
        self.assertEqual(result["covered_signature_count"], 1)
        self.assertEqual(result["coverage_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
