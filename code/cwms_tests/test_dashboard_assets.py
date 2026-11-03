"""Static checks for the dashboard frontend assets."""
import re
import unittest
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent / "cwms_dashboard"


class TestDashboardAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
        cls.js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
        cls.css = (DASHBOARD / "styles.css").read_text(encoding="utf-8")

    def test_required_files_exist(self):
        for name in ("index.html", "app.js", "styles.css"):
            self.assertTrue((DASHBOARD / name).exists(), name)

    def test_simulation_label_present(self):
        self.assertIn("SIMULATED", self.html)

    def test_key_panels_present(self):
        for panel in ("overview", "nodes", "metrics", "forecast", "scenarios"):
            self.assertIn(f'id="{panel}"', self.html)

    def test_referenced_ids_exist_in_markup(self):
        # IDs that app.js looks up directly via getElementById.
        ids = set(re.findall(r"getElementById\('([^']+)'\)", self.js))
        missing = [i for i in ids if f'id="{i}"' not in self.html]
        self.assertEqual(missing, [])

    def test_backend_endpoints_used(self):
        for endpoint in (
            "/config", "/nodes", "/simulation/start",
            "/simulation/status", "/simulation/results", "/simulation/summary",
            "/export/csv", "/export/json",
        ):
            self.assertIn(endpoint, self.js)

    def test_all_policies_selectable(self):
        for policy in ("least-loaded", "round-robin", "adaptive", "fcfs"):
            self.assertIn(f'value="{policy}"', self.html)

    def test_no_todo_placeholders(self):
        self.assertNotIn("TODO", self.html)
        self.assertNotIn("TODO", self.js)

    def test_node_health_request_uses_query_parameter(self):
        # The API accepts ?healthy=..., not a JSON body.
        self.assertIn("/health?healthy=", self.js)

    def test_blue_white_theme_tokens(self):
        self.assertIn("--primary: #0066cc", self.css)
        self.assertIn("--white: #ffffff", self.css)

    def test_assets_are_served_from_static_mount(self):
        self.assertIn('href="/static/styles.css"', self.html)
        self.assertIn('src="/static/app.js"', self.html)

    def test_api_token_control_and_admission_fields(self):
        self.assertIn('id="api-token"', self.html)
        self.assertIn("sessionStorage.getItem('cwms_api_token')", self.js)
        for field in (
            "custom-admission-control", "custom-overload-threshold",
            "custom-queue-limit", "custom-timeout-ms",
        ):
            self.assertIn(f'id="{field}"', self.html)

    def test_overload_scenario_card_present(self):
        self.assertIn('data-scenario="overload"', self.html)
        self.assertEqual(self.html.count('class="scenario-card"'), 4)


if __name__ == "__main__":
    unittest.main()