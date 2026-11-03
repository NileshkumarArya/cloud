"""API integration tests using FastAPI TestClient."""
import atexit
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

_IMPORT_DB = tempfile.TemporaryDirectory(prefix="cwms_api_import_")
atexit.register(_IMPORT_DB.cleanup)
os.environ["CWMS_DB_PATH"] = str(Path(_IMPORT_DB.name) / "import.db")

from cwms_api import main as api_main
from cwms_simulator.simulator import SimulationConfig
from cwms_simulator.storage import ResultsStore


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        api_main.simulator_state = api_main.SimulatorState()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        api_main.results_store = ResultsStore(Path(self.tmp.name) / "test.db")
        self.client = TestClient(api_main.app)

    def start_default(self, **overrides):
        payload = {
            "policy": "least-loaded",
            "intervals": 8,
            "base_rate": 30,
            "burst_rate": 120,
            "burst_start": 2,
            "burst_end": 4,
            "surge_threshold": 80,
            "load_threshold": 80.0,
            "fail_node": None,
            "forecast_window": 5,
            "seed": 3,
        }
        payload.update(overrides)
        return self.client.post("/api/simulation/start", json=payload)


class TestBasicEndpoints(ApiTestCase):
    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_root_lists_endpoints(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("endpoints", response.json())

    def test_config(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("least-loaded", body["available_policies"])
        self.assertIn("burst", body["available_scenarios"])
        self.assertNotIn("custom", body["available_scenarios"])
        self.assertEqual(body["max_load_threshold"], 100.0)
        self.assertEqual(body["forecast_strategy"], "change_aware")
        self.assertIn("moving_average", body["available_forecast_strategies"])

    def test_status_before_any_run(self):
        response = self.client.get("/api/simulation/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["running"])
        self.assertEqual(body["requests_generated"], 0)

    def test_scenarios_list(self):
        response = self.client.get("/api/scenarios")
        self.assertEqual(response.status_code, 200)
        ids = [s["id"] for s in response.json()["scenarios"]]
        self.assertEqual(ids, ["normal", "burst", "failure", "overload"])

    def test_nodes_default(self):
        response = self.client.get("/api/nodes")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["nodes"]), 3)

    def test_dashboard_and_static_assets(self):
        page = self.client.get("/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn("CWMS Dashboard", page.text)
        self.assertEqual(self.client.get("/static/styles.css").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)


class TestSimulationFlow(ApiTestCase):
    def test_run_and_read_results(self):
        response = self.start_default()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["policy"], "least-loaded")

        status = self.client.get("/api/simulation/status").json()
        self.assertFalse(status["running"])
        self.assertGreater(status["requests_generated"], 0)
        self.assertEqual(status["total_intervals"], 8)
        self.assertEqual(status["policy"], "least-loaded")

        results = self.client.get("/api/simulation/results").json()
        self.assertEqual(len(results["intervals"]), 8)

        summary = self.client.get("/api/simulation/summary").json()
        self.assertIn("system_metrics", summary)
        self.assertIn("forecast_accuracy", summary)
        self.assertEqual(summary["config"]["intervals"], 8)

    def test_forecast_accuracy_present(self):
        self.start_default(intervals=10)
        summary = self.client.get("/api/simulation/summary").json()
        self.assertIsNotNone(summary["forecast_accuracy"]["mae"])

    def test_failure_node_skipped(self):
        self.start_default(fail_node="backend-b")
        summary = self.client.get("/api/simulation/summary").json()
        by_name = {n["name"]: n for n in summary["node_metrics"]}
        self.assertEqual(by_name["backend-b"]["requests_assigned"], 0)

    def test_csv_export(self):
        self.start_default()
        response = self.client.get("/api/export/csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        text = response.text
        self.assertIn("interval", text.splitlines()[0])
        self.assertEqual(len(text.strip().splitlines()), 8 * 3 + 1)

    def test_json_export(self):
        self.start_default()
        response = self.client.get("/api/export/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("config", response.json())

    def test_run_is_persisted_and_listed(self):
        self.start_default()
        status = self.client.get("/api/simulation/status").json()
        self.assertIsNotNone(status["run_id"])

        history = self.client.get("/api/history").json()["runs"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], status["run_id"])
        self.assertEqual(history[0]["label"], "custom")

        detail = self.client.get(f"/api/history/{status['run_id']}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(len(body["intervals"]), 8)
        self.assertEqual(len(body["nodes"]), 3)

    def test_history_limit_validation(self):
        self.assertEqual(self.client.get("/api/history?limit=0").status_code, 400)
        self.assertEqual(self.client.get("/api/history?limit=500").status_code, 400)

    def test_history_unknown_run(self):
        self.assertEqual(self.client.get("/api/history/9999").status_code, 404)

    def test_history_prune_keeps_newest(self):
        for _ in range(3):
            self.start_default()
        response = self.client.post("/api/history/prune", json={"keep_latest": 1})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["deleted"], 2)
        self.assertEqual(body["remaining"], 1)
        self.assertEqual(len(self.client.get("/api/history").json()["runs"]), 1)

    def test_scenario_burst(self):
        response = self.client.post(
            "/api/scenarios/run", json={"scenario": "burst", "policy": "round-robin"}
        )
        self.assertEqual(response.status_code, 200)
        status = self.client.get("/api/simulation/status").json()
        self.assertEqual(status["policy"], "round-robin")
        self.assertGreater(status["requests_generated"], 0)

    def test_overload_scenario_records_rejections_and_timeouts(self):
        response = self.client.post(
            "/api/scenarios/run",
            json={"scenario": "overload", "policy": "least-loaded"},
        )
        self.assertEqual(response.status_code, 200)
        summary = self.client.get("/api/simulation/summary").json()
        metrics = summary["system_metrics"]
        self.assertGreater(metrics["total_requests_queued"], 0)
        self.assertGreater(metrics["total_requests_rejected_overload"], 0)
        self.assertGreater(metrics["total_requests_timed_out"], 0)
        self.assertEqual(metrics["total_requests_failed"], metrics["total_requests_timed_out"])
        self.assertEqual(
            metrics["total_requests_generated"],
            metrics["total_requests_assigned"] + metrics["total_requests_rejected"],
        )

    def test_node_health_toggle(self):
        self.start_default(intervals=8, burst_start=0, burst_end=0)
        response = self.client.post(
            "/api/nodes/backend-b/health", params={"healthy": "false"}
        )
        self.assertEqual(response.status_code, 200)
        nodes = self.client.get("/api/nodes").json()["nodes"]
        node_b = next(n for n in nodes if n["name"] == "backend-b")
        self.assertFalse(node_b["healthy"])

    def test_node_health_toggle_before_first_run(self):
        response = self.client.post(
            "/api/nodes/backend-c/health", params={"healthy": "false"}
        )
        self.assertEqual(response.status_code, 200)
        nodes = self.client.get("/api/nodes").json()["nodes"]
        node_c = next(n for n in nodes if n["name"] == "backend-c")
        self.assertFalse(node_c["healthy"])

    def test_node_health_override_applies_to_next_run(self):
        self.start_default(intervals=6, burst_start=0, burst_end=0)
        response = self.client.post(
            "/api/nodes/backend-b/health", params={"healthy": "false"}
        )
        self.assertEqual(response.status_code, 200)

        self.start_default(intervals=6, burst_start=0, burst_end=0)
        summary = self.client.get("/api/simulation/summary").json()
        by_name = {n["name"]: n for n in summary["node_metrics"]}
        self.assertEqual(by_name["backend-b"]["requests_assigned"], 0)
        self.assertFalse(by_name["backend-b"]["healthy"])

    def test_failed_scenario_cannot_be_revived_by_override(self):
        response = self.client.post(
            "/api/nodes/backend-b/health", params={"healthy": "true"}
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/api/scenarios/run", json={"scenario": "failure", "policy": "least-loaded"}
        )
        self.assertEqual(response.status_code, 200)
        summary = self.client.get("/api/simulation/summary").json()
        by_name = {n["name"]: n for n in summary["node_metrics"]}
        self.assertEqual(by_name["backend-b"]["requests_assigned"], 0)
        self.assertFalse(by_name["backend-b"]["healthy"])

    def test_running_status_reports_label_and_error(self):
        api_main._prepare_simulator(
            SimulationConfig(intervals=2, burst_start=0, burst_end=0), "burst"
        )
        api_main.simulator_state.running = True
        api_main.simulator_state.error = "test-error"
        status = self.client.get("/api/simulation/status").json()
        self.assertTrue(status["running"])
        self.assertEqual(status["label"], "burst")
        self.assertEqual(status["error"], "test-error")

        api_main.simulator_state.running = False
        status = self.client.get("/api/simulation/status").json()
        self.assertEqual(status["recommendation"], "Simulation failed")

    def test_unknown_node_health(self):
        self.start_default(intervals=8, burst_start=0, burst_end=0)
        response = self.client.post(
            "/api/nodes/backend-z/health", params={"healthy": "false"}
        )
        self.assertEqual(response.status_code, 404)


    def test_adaptive_policy_accepted(self):
        response = self.start_default(policy="adaptive", intervals=6, burst_start=0, burst_end=0)
        self.assertEqual(response.status_code, 200)
        status = self.client.get("/api/simulation/status").json()
        self.assertEqual(status["policy"], "adaptive")
        self.assertFalse(status["running"])

    def test_fcfs_policy_accepted(self):
        response = self.start_default(policy="fcfs", intervals=6, burst_start=0, burst_end=0)
        self.assertEqual(response.status_code, 200)
        summary = self.client.get("/api/simulation/summary").json()
        self.assertEqual(summary["config"]["policy"], "fcfs")


class TestValidationAndErrors(ApiTestCase):
    def test_invalid_policy(self):
        response = self.start_default(policy="magic")
        self.assertEqual(response.status_code, 422)

    def test_zero_intervals(self):
        response = self.start_default(intervals=0)
        self.assertEqual(response.status_code, 422)

    def test_burst_start_after_end(self):
        response = self.start_default(burst_start=6, burst_end=5)
        self.assertEqual(response.status_code, 400)

    def test_equal_burst_bounds_disable_burst(self):
        response = self.start_default(burst_start=0, burst_end=0)
        self.assertEqual(response.status_code, 200)

    def test_burst_end_beyond_intervals(self):
        response = self.start_default(intervals=5, burst_end=99, burst_start=1)
        self.assertEqual(response.status_code, 400)

    def test_negative_base_rate(self):
        response = self.start_default(base_rate=-1)
        self.assertEqual(response.status_code, 422)

    def test_results_before_run(self):
        self.assertEqual(self.client.get("/api/simulation/results").status_code, 404)

    def test_summary_before_run(self):
        self.assertEqual(self.client.get("/api/simulation/summary").status_code, 404)

    def test_export_before_run(self):
        self.assertEqual(self.client.get("/api/export/csv").status_code, 404)

    def test_unknown_scenario(self):
        response = self.client.post(
            "/api/scenarios/run", json={"scenario": "apocalypse", "policy": "round-robin"}
        )
        self.assertEqual(response.status_code, 422)

    def test_invalid_admission_values(self):
        self.assertEqual(self.start_default(overload_threshold=200).status_code, 422)
        self.assertEqual(self.start_default(queue_limit=-1).status_code, 422)
        self.assertEqual(self.start_default(request_timeout_ms=0).status_code, 422)

    def test_total_volume_limit(self):
        response = self.start_default(
            intervals=200, base_rate=1000, burst_rate=1000,
            burst_start=0, burst_end=0,
        )
        self.assertEqual(response.status_code, 422)


class TestSecurity(ApiTestCase):
    def _set_env(self, name, value):
        previous = os.environ.get(name)
        os.environ[name] = value
        self.addCleanup(self._restore_env, name, previous)

    def _restore_env(self, name, value):
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def test_state_changing_endpoints_require_bearer_token(self):
        self._set_env("CWMS_API_TOKEN", "unit-test-token")
        payload = {
            "policy": "least-loaded", "intervals": 2, "base_rate": 20,
            "burst_rate": 20, "burst_start": 0, "burst_end": 0,
        }
        self.assertEqual(
            self.client.post("/api/simulation/start", json=payload).status_code, 401
        )
        self.assertEqual(
            self.client.post(
                "/api/simulation/start", json=payload,
                headers={"Authorization": "Bearer wrong"},
            ).status_code, 401
        )
        self.assertEqual(
            self.client.post(
                "/api/simulation/start", json=payload,
                headers={"Authorization": "Bearer unit-test-token"},
            ).status_code, 200
        )

    def test_node_health_requires_token(self):
        self._set_env("CWMS_API_TOKEN", "unit-test-token")
        response = self.client.post(
            "/api/nodes/backend-b/health", params={"healthy": "false"}
        )
        self.assertEqual(response.status_code, 401)
        response = self.client.post(
            "/api/nodes/backend-b/health", params={"healthy": "false"},
            headers={"Authorization": "Bearer unit-test-token"},
        )
        self.assertEqual(response.status_code, 200)

    def test_history_prune_requires_token(self):
        self._set_env("CWMS_API_TOKEN", "unit-test-token")
        self.assertEqual(
            self.client.post(
                "/api/history/prune", json={"keep_latest": 10}
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/history/prune", json={"keep_latest": 10},
                headers={"Authorization": "Bearer unit-test-token"},
            ).status_code,
            200,
        )

    def test_oversized_body_rejected(self):
        response = self.client.post(
            "/api/simulation/start",
            content=b"{" + b"x" * 40000 + b"}",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)

    def test_security_headers_present(self):
        response = self.client.get("/health")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")

    def test_cors_origins_are_opt_in(self):
        self._set_env("CWMS_CORS_ORIGINS", "http://localhost:3000, https://example.test")
        self.assertEqual(
            api_main._cors_origins(),
            ["http://localhost:3000", "https://example.test"],
        )

    def test_non_loopback_bind_requires_token_or_override(self):
        os.environ.pop("CWMS_API_TOKEN", None)
        os.environ.pop("CWMS_ALLOW_UNAUTHENTICATED_REMOTE", None)
        with self.assertRaises(RuntimeError):
            api_main._validate_bind_host("0.0.0.0")

        self._set_env("CWMS_API_TOKEN", "unit-test-token")
        api_main._validate_bind_host("0.0.0.0")

        os.environ.pop("CWMS_API_TOKEN", None)
        self._set_env("CWMS_ALLOW_UNAUTHENTICATED_REMOTE", "1")
        api_main._validate_bind_host("0.0.0.0")

    def test_status_exposes_admission_metrics(self):
        self.start_default()
        status = self.client.get("/api/simulation/status").json()
        for key in (
            "requests_completed", "requests_failed", "requests_queued",
            "requests_timed_out", "requests_rejected_overload",
            "requests_rejected_no_capacity",
        ):
            self.assertIn(key, status)


if __name__ == "__main__":
    unittest.main()
