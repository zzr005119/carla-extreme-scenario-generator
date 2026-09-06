import unittest
from pathlib import Path
import tempfile

from core.carla_rl_plan import load_multiscene_plan
from tools.prepare_carla_rl_p3_1_blind_plan import (
    build_independent_blind_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTRIES = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "entries.jsonl"
MANIFEST = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "manifest.json"


class CarlaRLBlindPlanTests(unittest.TestCase):
    def test_blind_plan_is_deterministic_and_independent(self):
        with tempfile.TemporaryDirectory() as temp:
            first_path = Path(temp) / "first.json"
            second_path = Path(temp) / "second.json"
            first = build_independent_blind_plan(
                ENTRIES, MANIFEST, first_path, seed=20260906
            )
            second = build_independent_blind_plan(
                ENTRIES, MANIFEST, second_path, seed=20260906
            )
            self.assertEqual(first["plan_sha256"], second["plan_sha256"])
            self.assertEqual(first["counts"]["blind"], 24)
            self.assertEqual(first["leakage_check"]["blind_scenario_hash_overlap"], 0)
            self.assertEqual(first["leakage_check"]["blind_canonical_sample_id_overlap"], 0)
            blind_ids = {
                row["canonical_sample_id"] for row in first["splits"]["blind"]
            }
            frozen_ids = {
                row["canonical_sample_id"]
                for split in ("train", "dev", "test")
                for row in first["splits"][split]
            }
            self.assertTrue(blind_ids.isdisjoint(frozen_ids))
            strata = {}
            for row in first["splits"]["blind"]:
                key = (row["generator"], row["target_risk_level"])
                strata[key] = strata.get(key, 0) + 1
            self.assertEqual(set(strata.values()), {2})
            loaded = load_multiscene_plan(first_path)
            self.assertEqual(loaded["plan_sha256"], first["plan_sha256"])


if __name__ == "__main__":
    unittest.main()
