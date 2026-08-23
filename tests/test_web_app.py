import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from tools.scenario_dashboard import load_dashboard_data
from tools.web_app import WebAppHandler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = PROJECT_ROOT / "data" / "scenarios" / "scenario_library_v1"


class WebAppHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dashboard_data = load_dashboard_data(LIBRARY_DIR)
        handler_class = type("TestWebAppHandler", (WebAppHandler,), {})
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

    def test_web_pages_and_navigation(self):
        for path in ("/", "/dashboard", "/scenarios", "/generation", "/validation", "/tasks", "/risk"):
            status, headers, body = self.get_bytes(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(headers.get_content_type(), "text/html", path)
            self.assertIn("/scenarios", body.decode("utf-8"), path)

    def test_workflow_pages_are_operational_forms(self):
        expected = {
            "/generation": ("/api/tasks", "生成数量", "提交任务"),
            "/validation": ("/api/tasks", "记录路径", "编译 CARLA 配置"),
            "/risk": ("/api/tasks", "运行目录", "遥测 CSV"),
        }
        for path, markers in expected.items():
            body = self.get_bytes(path)[2].decode("utf-8")
            for marker in markers:
                self.assertIn(marker, body, f"{path} 缺少 {marker}")

    def test_detail_page_and_health_contract(self):
        status, headers, body = self.get_bytes(f"/scenarios/{self.first_library_id}")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "text/html")
        self.assertIn("场景详情", body.decode("utf-8"))
        health = self.get_json("/healthz")
        self.assertEqual(health["status"], "ok")
        self.assertFalse(health["carla_connected"])
        self.assertEqual(health["entry_count"], 117)
        self.assertEqual(health["accepted_run_evidence_count"], 351)

    def test_existing_api_contract_is_unchanged(self):
        summary = self.get_json("/api/summary")
        scenarios = self.get_json("/api/scenarios")
        self.assertEqual(summary["entry_count"], 117)
        self.assertEqual(summary["accepted_run_evidence_count"], 351)
        self.assertEqual(scenarios["count"], 117)
        record = self.get_json(f"/api/scenarios/{self.first_library_id}")
        self.assertEqual(record["library_id"], self.first_library_id)

    def test_unknown_page_returns_not_found(self):
        with self.assertRaises(HTTPError) as context:
            self.get_bytes("/missing")
        self.assertEqual(context.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
