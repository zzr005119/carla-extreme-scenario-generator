import unittest
from pathlib import Path

from tools.scenario_dashboard import load_dashboard_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1"


class ScenarioDashboardDataTests(unittest.TestCase):
    def test_dashboard_loads_library_snapshot(self):
        dashboard_data = load_dashboard_data(LIBRARY_DIR)

        self.assertEqual(len(dashboard_data["rows"]), 117)
        self.assertEqual(len(dashboard_data["entries"]), 117)
        self.assertEqual(dashboard_data["summary"]["entry_count"], 117)
        self.assertEqual(dashboard_data["summary"]["accepted_run_evidence_count"], 351)

    def test_dashboard_index_and_entry_ids_match(self):
        dashboard_data = load_dashboard_data(LIBRARY_DIR)
        row_ids = {row["library_id"] for row in dashboard_data["rows"]}
        entry_ids = set(dashboard_data["entries"])

        self.assertEqual(row_ids, entry_ids)
        self.assertTrue(all(row["sample_id"] for row in dashboard_data["rows"]))
        self.assertTrue(all(row["quality_tier"] in {"bronze", "silver", "gold"} for row in dashboard_data["rows"]))


if __name__ == "__main__":
    unittest.main()
