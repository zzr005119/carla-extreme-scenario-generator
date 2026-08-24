import json
import tempfile
import unittest
from pathlib import Path

from tools.benchmark_stage5_generation_baseline import _generate


class Stage5GenerationBaselineTests(unittest.TestCase):
    def test_lhs_and_uniform_rule_share_contract_and_count(self):
        with tempfile.TemporaryDirectory(prefix="stage5-generation-") as root:
            root = Path(root)
            lhs = _generate("lhs", root / "lhs.jsonl", 2, 20260824, repeats=2)
            baseline = _generate(
                "uniform_rule", root / "baseline.jsonl", 2, 20260824, repeats=2
            )

            self.assertEqual(lhs["accepted_count"], 16)
            self.assertEqual(baseline["accepted_count"], 16)
            self.assertEqual(
                lhs["measurement_contract"], baseline["measurement_contract"]
            )
            self.assertEqual(
                len(
                    [
                        line
                        for line in (root / "lhs.jsonl")
                        .read_text(encoding="utf-8")
                        .splitlines()
                        if line
                    ]
                ),
                8,
            )
            record = json.loads(
                (root / "baseline.jsonl").read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(record["provenance"]["generator"], "uniform_rule_parameter_sampling_v1")
            self.assertEqual(record["observed_risk"]["status"], "not_simulated")


if __name__ == "__main__":
    unittest.main()
