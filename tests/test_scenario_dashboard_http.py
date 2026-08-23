import json
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

from tools.scenario_dashboard import DashboardHandler, load_dashboard_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1"


class ScenarioDashboardHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dashboard_data = load_dashboard_data(LIBRARY_DIR)
        handler_class = type("TestDashboardHandler", (DashboardHandler,), {})
        handler_class.dashboard_data = dashboard_data
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.first_library_id = dashboard_data["rows"][0]["library_id"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    @classmethod
    def get_bytes(cls, path):
        with urlopen(cls.base_url + path, timeout=5) as response:
            return response.status, response.headers, response.read()

    @classmethod
    def get_json(cls, path):
        _, _, body = cls.get_bytes(path)
        return json.loads(body.decode("utf-8"))

    def test_page_contract(self):
        status, headers, body = self.get_bytes("/")
        page = body.decode("utf-8")

        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get_content_type())
        self.assertIn("CARLA 极端场景库 V1", page)
        self.assertIn('id="scenario-rows"', page)
        self.assertIn('id="detail-panel"', page)
        self.assertIn("/api/scenarios", page)

    def test_summary_api_contract(self):
        summary = self.get_json("/api/summary")

        self.assertEqual(summary["entry_count"], 117)
        self.assertEqual(summary["accepted_run_evidence_count"], 351)
        self.assertIn("quality_summary", summary)

    def test_scenario_list_api_contract(self):
        payload = self.get_json("/api/scenarios")

        self.assertEqual(payload["count"], 117)
        self.assertEqual(len(payload["items"]), 117)
        self.assertIn("library_id", payload["items"][0])
        self.assertIn("sample_id", payload["items"][0])
        self.assertIn("collision_observed", payload["items"][0])

    def test_controlled_search_api_contract(self):
        payload = self.get_json(
            "/api/scenarios/search?target_risk=high&weather_tag=night&"
            "keyword=lhs&sort=risk_desc&limit=3"
        )

        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["library_count"], 117)
        self.assertEqual(payload["limit"], 3)
        self.assertEqual(payload["sort"], "risk_desc")
        self.assertEqual(len(payload["items"]), 3)
        self.assertTrue(all(item["generators"] == "lhs" for item in payload["items"]))
        self.assertTrue(all(item["target_risk_levels"] == "high" for item in payload["items"]))

    def test_controlled_search_rejects_unsupported_values(self):
        with self.assertRaises(HTTPError) as context:
            self.get_bytes("/api/scenarios/search?target_risk=high%20risk")

        self.assertEqual(context.exception.code, 400)

    def test_scenario_detail_api_contract(self):
        record = self.get_json(f"/api/scenarios/{self.first_library_id}")

        self.assertEqual(record["library_id"], self.first_library_id)
        self.assertIn("parameters", record)
        self.assertIn("execution_evidence", record)
        self.assertIn("observed_risk", record)
        self.assertIn("quality", record)

    def test_missing_scenario_returns_not_found(self):
        with self.assertRaises(HTTPError) as context:
            self.get_bytes("/api/scenarios/not-found")

        self.assertEqual(context.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
