import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALITY_GATE_PATH = PROJECT_ROOT / "configs" / "scenario_library_quality_gate_v1.json"
LIBRARY_SUMMARY_PATH = (
    PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1" / "summary.json"
)
QUALITY_ANALYSIS_SUMMARY_PATH = (
    PROJECT_ROOT
    / "data"
    / "scenarios"
    / "scenario_library_v1"
    / "quality_analysis_v1"
    / "analysis_summary.json"
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def test_temp_root():
    configured_root = os.environ.get("SCENARIO_LIBRARY_TEST_TMP")
    if configured_root:
        root = Path(configured_root)
    elif os.name == "nt" and Path("F:/").exists():
        root = Path("F:/Carla/project-transfer/test-tmp")
    else:
        root = Path(tempfile.gettempdir()) / "scenario-library-test-tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root


class ScenarioLibraryInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quality_gate = load_json(QUALITY_GATE_PATH)
        cls.library_summary = load_json(LIBRARY_SUMMARY_PATH)
        cls.quality_analysis_summary = load_json(QUALITY_ANALYSIS_SUMMARY_PATH)

    def run_script(self, script_path, *arguments):
        command = [sys.executable, str(PROJECT_ROOT / script_path), *arguments]
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=(
                f"命令失败: {' '.join(command)}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            ),
        )
        return result

    def test_library_snapshot_matches_quality_gate(self):
        expected = self.quality_gate["expected_library"]
        for field_name, expected_value in expected.items():
            self.assertEqual(self.library_summary[field_name], expected_value, field_name)

    def test_quality_analysis_snapshot_matches_quality_gate(self):
        expected = self.quality_gate["expected_analysis"]
        for field_name, expected_value in expected.items():
            self.assertEqual(
                self.quality_analysis_summary[field_name],
                expected_value,
                field_name,
            )

    def test_builder_and_analysis_validation(self):
        builder_result = self.run_script(
            "tools/build_scenario_library.py",
            "--validate-only",
        )
        self.assertIn("[VALID]", builder_result.stdout)
        analysis_result = self.run_script(
            "analysis/analyze_scenario_library.py",
            "--validate-only",
        )
        self.assertIn("[VALID]", analysis_result.stdout)

    def test_query_contracts(self):
        expected_fields = self.quality_gate["query_fields"]
        for contract in self.quality_gate["query_contracts"]:
            result = self.run_script(
                "tools/query_scenario_library.py",
                *contract["args"],
            )
            if contract["format"] == "jsonl":
                records = [
                    json.loads(line)
                    for line in result.stdout.splitlines()
                    if line.strip()
                ]
                self.assertEqual(len(records), contract["expected_count"], contract["name"])
            else:
                csv_reader = csv.DictReader(
                    io.StringIO(result.stdout.lstrip("\ufeff"))
                )
                rows = list(csv_reader)
                self.assertEqual(len(rows), contract["expected_count"], contract["name"])
                self.assertEqual(csv_reader.fieldnames, expected_fields, contract["name"])

    def test_query_csv_output_path(self):
        temporary_directory = Path(
            tempfile.mkdtemp(prefix="scenario-library-interface-", dir=test_temp_root())
        )
        try:
            output_path = temporary_directory / "collision.csv"
            self.run_script(
                "tools/query_scenario_library.py",
                "--collision",
                "yes",
                "--limit",
                "5",
                "--format",
                "csv",
                "--output",
                str(output_path),
            )
            with open(output_path, "r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(row["collision_observed"] == "True" for row in rows))
        finally:
            shutil.rmtree(temporary_directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
