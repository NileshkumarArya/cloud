"""Integration tests for the end-to-end simulator."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from cwms_simulator.nodes import NodeState
from cwms_simulator.simulator import CWMSimulator, SimulationConfig


class TestSimulator(unittest.TestCase):
    def _config(self, **overrides):
        defaults = dict(
            policy="least-loaded",
            intervals=20,
            base_rate=40,
            burst_rate=180,
            burst_start=8,
            burst_end=13,
            surge_threshold=90,
            fail_node=None,
            seed=7,
            output_path="unused.csv",
        )
        defaults.update(overrides)
        # When a test shortens the run without specifying burst bounds,
        # disable the burst window so the configuration stays valid.
        if (overrides.get("intervals", 20) < defaults["burst_end"]
                and "burst_end" not in overrides):
            defaults["burst_start"] = 0
            defaults["burst_end"] = 0
        return SimulationConfig(**defaults)

    def test_burst_scenario_detects_surge(self):
        sim = CWMSimulator(self._config())
        result = sim.run()
        self.assertGreater(len(result.surge_events), 0)
        self.assertTrue(any(i.surge_detected for i in result.intervals))
        self.assertGreater(max(i.requests_generated for i in result.intervals), 90)

    def test_normal_scenario_no_surge(self):
        sim = CWMSimulator(self._config(
            base_rate=40, burst_rate=40, burst_start=0, burst_end=0,
            surge_threshold=120, load_threshold=999, max_load_threshold=999,
        ))
        result = sim.run()
        self.assertEqual(result.surge_events, [])

    def test_single_saturated_node_triggers_max_load_surge(self):
        sim = CWMSimulator(self._config(
            policy="fcfs", intervals=6, base_rate=40, burst_rate=40,
            burst_start=0, burst_end=0, surge_threshold=999,
            load_threshold=999, max_load_threshold=100,
        ))
        result = sim.run()
        self.assertTrue(any(
            event.surge_type == "max_load" for event in result.surge_events
        ))
        self.assertEqual(result.to_summary_dict()["config"]["max_load_threshold"], 100)

    def test_unhealthy_node_receives_no_assignments(self):
        sim = CWMSimulator(self._config(fail_node="backend-b"))
        result = sim.run()
        by_name = {m.name: m for m in result.final_node_metrics}
        self.assertEqual(by_name["backend-b"].requests_assigned, 0)
        self.assertFalse(by_name["backend-b"].healthy)
        self.assertGreater(by_name["backend-a"].requests_assigned, 0)
        self.assertGreater(by_name["backend-c"].requests_assigned, 0)

    def test_no_healthy_nodes_rejects_everything(self):
        sim = CWMSimulator(self._config(intervals=3, base_rate=10, burst_rate=10,
                                        burst_start=0, burst_end=0))
        sim.initialize()
        for node in sim.nodes:
            node.set_health(NodeState.UNHEALTHY)
        result = sim.run()
        metrics = result.final_system_metrics
        self.assertEqual(metrics.total_requests_assigned, 0)
        self.assertEqual(metrics.total_requests_rejected, metrics.total_requests_generated)
        self.assertGreater(metrics.total_requests_generated, 0)

    def test_policies_process_equivalent_workload(self):
        results = {}
        for policy in ("round-robin", "least-loaded"):
            sim = CWMSimulator(self._config(
                policy=policy, burst_rate=60, burst_start=5, burst_end=10,
            ))
            results[policy] = sim.run()
        rr = results["round-robin"].final_system_metrics
        ll = results["least-loaded"].final_system_metrics
        self.assertEqual(rr.total_requests_generated, ll.total_requests_generated)
        self.assertEqual(rr.total_requests_assigned, ll.total_requests_assigned)

    def test_least_loaded_balances_load_better(self):
        rr = CWMSimulator(self._config(policy="round-robin", burst_rate=60,
                                       burst_start=5, burst_end=10)).run()
        ll = CWMSimulator(self._config(policy="least-loaded", burst_rate=60,
                                       burst_start=5, burst_end=10)).run()

        def final_load_spread(result):
            loads = [m.current_load for m in result.final_node_metrics]
            return max(loads) - min(loads)

        def peak_load(result):
            return max(i.max_load for i in result.intervals)

        # Least-loaded equalises node load and reduces the peak observed load.
        self.assertLess(final_load_spread(ll), final_load_spread(rr))
        self.assertLessEqual(peak_load(ll), peak_load(rr))

    def test_forecast_is_causal(self):
        sim = CWMSimulator(self._config(intervals=8, burst_rate=40,
                                        burst_start=0, burst_end=0))
        result = sim.run()
        requests = [i.requests_generated for i in result.intervals]
        self.assertAlmostEqual(result.intervals[1].forecast["predicted"], requests[0], places=2)
        self.assertAlmostEqual(
            result.intervals[2].forecast["predicted"],
            (requests[0] + requests[1]) / 2,
            places=2,
        )
        # First interval has no history and is not scored
        self.assertNotIn("actual", result.intervals[0].forecast)

    def test_forecast_accuracy_available(self):
        result = CWMSimulator(self._config()).run()
        self.assertIsNotNone(result.forecast_mae)
        self.assertIsNotNone(result.forecast_rmse)
        self.assertGreaterEqual(result.forecast_mae, 0)
        self.assertIsNotNone(result.forecast_naive_mae)
        self.assertIsNotNone(result.forecast_naive_rmse)
        accuracy = result.to_summary_dict()["forecast_accuracy"]
        self.assertIn("naive_mae", accuracy)
        self.assertIn("naive_rmse", accuracy)
        self.assertIn("moving_average_mae", accuracy)
        self.assertIn("moving_average_rmse", accuracy)
        self.assertEqual(accuracy["strategy"], "change_aware")

    def test_csv_export_columns_and_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "nested" / "events.csv"
            sim = CWMSimulator(self._config(intervals=5, output_path=str(output)))
            result = sim.run()
            written = sim.export_csv(result)
            self.assertTrue(written.exists())

            with written.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
                fieldnames = reader.fieldnames

            self.assertEqual(len(rows), 5 * 3)
            for column in (
                "interval", "policy", "requests_generated", "node",
                "simulated_load_percent", "surge_detected",
                "forecast_predicted", "forecast_method",
                "moving_average_forecast", "recommendation",
            ):
                self.assertIn(column, fieldnames)
            self.assertTrue(all(row["policy"] == "least-loaded" for row in rows))

    def test_json_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            sim = CWMSimulator(self._config(intervals=4))
            result = sim.run()
            sim.export_json(result, str(path))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("config", data)
            self.assertIn("system_metrics", data)
            self.assertIn("forecast_accuracy", data)
            self.assertEqual(data["config"]["policy"], "least-loaded")

    def test_config_serialization(self):
        config = self._config()
        traffic = config.to_traffic_config()
        self.assertEqual(traffic.intervals, config.intervals)
        self.assertEqual(traffic.seed, config.seed)

    def test_config_validation(self):
        with self.assertRaises(ValueError):
            SimulationConfig(intervals=0)
        with self.assertRaises(ValueError):
            SimulationConfig(base_rate=-1)
        with self.assertRaises(ValueError):
            SimulationConfig(burst_start=10, burst_end=5)
        with self.assertRaises(ValueError):
            SimulationConfig(intervals=5, burst_end=6)
        with self.assertRaises(ValueError):
            SimulationConfig(max_load_threshold=-1)
        with self.assertRaises(ValueError):
            SimulationConfig(forecast_window=0)
        with self.assertRaises(ValueError):
            SimulationConfig(forecast_strategy="magic")
        with self.assertRaises(ValueError):
            SimulationConfig(seed=-1)
        with self.assertRaises(ValueError):
            SimulationConfig(policy="magic")
        with self.assertRaises(ValueError):
            SimulationConfig(fail_node="backend-typo")

    def test_progress_callback(self):
        seen = []
        sim = CWMSimulator(self._config(intervals=4))
        sim.run(progress_callback=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen, [(1, 4), (2, 4), (3, 4), (4, 4)])

    def test_recommendation_per_interval(self):
        result = CWMSimulator(self._config(intervals=5)).run()
        self.assertEqual(len(result.recommendations), 5)
        for interval in result.intervals:
            self.assertIn("message", interval.recommendation)

    def test_queue_overflow_accounting_is_consistent(self):
        result = CWMSimulator(self._config(
            intervals=1, base_rate=300, burst_rate=300, burst_start=0,
            burst_end=0, overload_threshold=0.0, queue_limit=5,
            request_timeout_ms=2000.0,
        )).run()
        metrics = result.final_system_metrics
        self.assertGreater(metrics.total_requests_queued, 0)
        self.assertGreater(metrics.total_requests_rejected_overload, 0)
        self.assertEqual(metrics.total_requests_rejected_no_capacity, 0)
        self.assertEqual(
            metrics.total_requests_generated,
            metrics.total_requests_assigned + metrics.total_requests_rejected,
        )
        self.assertEqual(
            metrics.total_requests_assigned,
            metrics.total_requests_completed + metrics.total_requests_failed,
        )
        self.assertEqual(metrics.total_requests_queued, metrics.total_requests_assigned)

    def test_request_timeout_failures_are_not_completed(self):
        result = CWMSimulator(self._config(
            intervals=1, base_rate=120, burst_rate=120, burst_start=0,
            burst_end=0, overload_threshold=0.0, queue_limit=500,
            request_timeout_ms=50.0,
        )).run()
        metrics = result.final_system_metrics
        self.assertGreater(metrics.total_requests_timed_out, 0)
        self.assertEqual(metrics.total_requests_timed_out, metrics.total_requests_failed)
        self.assertLess(metrics.total_requests_completed, metrics.total_requests_assigned)

    def test_admission_can_be_disabled_for_baseline(self):
        result = CWMSimulator(self._config(
            intervals=1, base_rate=300, burst_rate=300, burst_start=0,
            burst_end=0, admission_control=False,
        )).run()
        metrics = result.final_system_metrics
        self.assertEqual(metrics.total_requests_queued, 0)
        self.assertEqual(metrics.total_requests_rejected, 0)
        self.assertEqual(metrics.total_requests_completed, metrics.total_requests_generated)

    def test_admission_config_validation(self):
        with self.assertRaises(ValueError):
            SimulationConfig(overload_threshold=-1)
        with self.assertRaises(ValueError):
            SimulationConfig(overload_threshold=200)
        with self.assertRaises(ValueError):
            SimulationConfig(queue_limit=-1)
        with self.assertRaises(ValueError):
            SimulationConfig(request_timeout_ms=0)


if __name__ == "__main__":
    unittest.main()
