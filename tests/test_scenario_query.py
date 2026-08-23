import unittest

from core.scenario_query import query_entries, spec_from_mapping
from tools.query_scenario_library import load_entries


class ScenarioQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = load_entries(
            "data/scenarios/scenario_library_v1/entries.jsonl"
        )

    def test_structured_and_keyword_filters_are_combined(self):
        spec = spec_from_mapping(
            {
                "target_risk": "high",
                "weather_tag": ["night"],
                "keyword": ["lhs"],
            }
        )
        rows = query_entries(self.entries, spec, sort="risk_desc", limit=5)

        self.assertEqual(len(rows), 5)
        self.assertTrue(
            all(
                row["labels"]["target_risk_levels"] == ["high"]
                and "night" in row["labels"]["weather_tags"]
                and "lhs" in row["labels"]["generators"]
                for row in rows
            )
        )
        self.assertGreaterEqual(
            rows[0]["observed_risk"]["score_mean"],
            rows[-1]["observed_risk"]["score_mean"],
        )

    def test_keyword_search_is_whitelisted_and_case_insensitive(self):
        spec = spec_from_mapping({"keyword": "NIGHT"})
        rows = query_entries(self.entries, spec, limit=0)

        self.assertGreater(len(rows), 0)
        self.assertTrue(
            all("night" in row["labels"]["weather_tags"] for row in rows)
        )

    def test_invalid_control_value_is_rejected(self):
        with self.assertRaises(ValueError):
            spec_from_mapping({"target_risk": "high risk"})
        with self.assertRaises(ValueError):
            spec_from_mapping({"collision": "maybe"})


if __name__ == "__main__":
    unittest.main()
