"""Unit tests for metrics collection."""
import unittest

from cwms_simulator.nodes import Node
from cwms_simulator.metrics import MetricsCollector


class TestMetricsCollector(unittest.TestCase):
    def setUp(self):
        self.node = Node("a", 100)
        self.collector = MetricsCollector()
        self.collector.register_node(self.node)

    def test_generated_counter(self):
        self.collector.record_request_generated(10)
        self.collector.record_request_generated(5)
        self.assertEqual(self.collector.get_system_metrics().total_requests_generated, 15)

    def test_assignment_updates_node(self):
        self.node.load = 40
        self.collector.record_request_assigned(self.node)
        node_metrics = self.collector.get_node_metrics("a")
        self.assertEqual(node_metrics.requests_assigned, 1)
        self.assertEqual(node_metrics.current_load, 40)
        self.assertEqual(self.collector.get_system_metrics().total_requests_assigned, 1)

    def test_max_load_tracked(self):
        self.node.load = 30
        self.collector.record_request_assigned(self.node)
        self.node.load = 10
        self.collector.record_request_assigned(self.node)
        self.assertEqual(self.collector.get_node_metrics("a").max_load, 30)

    def test_rejection_counter(self):
        self.collector.record_request_generated(5)
        self.collector.record_request_rejected()
        metrics = self.collector.get_system_metrics()
        self.assertEqual(metrics.total_requests_rejected, 1)
        self.assertAlmostEqual(metrics.rejection_rate, 20.0)

    def test_completion_and_latency(self):
        self.collector.record_request_assigned(self.node)
        self.collector.record_request_assigned(self.node)
        self.collector.record_request_completed("a", 10.0)
        self.collector.record_request_completed("a", 20.0)
        node_metrics = self.collector.get_node_metrics("a")
        self.assertEqual(node_metrics.requests_completed, 2)
        self.assertAlmostEqual(node_metrics.avg_latency, 15.0)

    def test_failure_and_error_rate(self):
        self.collector.record_request_completed("a", 10.0)
        self.collector.record_request_failed("a")
        node_metrics = self.collector.get_node_metrics("a")
        self.assertEqual(node_metrics.requests_failed, 1)
        self.assertAlmostEqual(node_metrics.error_rate, 50.0)

    def test_completion_rate(self):
        self.collector.record_request_generated(4)
        for _ in range(4):
            self.collector.record_request_assigned(self.node)
        for _ in range(2):
            self.collector.record_request_completed("a", 5.0)
        metrics = self.collector.get_system_metrics()
        self.assertAlmostEqual(metrics.completion_rate, 50.0)
        self.assertAlmostEqual(metrics.assignment_rate, 100.0)

    def test_end_interval_resets_counters(self):
        self.collector.record_request_generated(10)
        self.collector.record_request_assigned(self.node)
        summary = self.collector.end_interval(0, False)
        self.assertEqual(summary["requests_generated"], 10)
        self.assertEqual(summary["requests_assigned"], 1)
        self.assertEqual(self.collector.get_system_metrics().intervals_elapsed, 1)
        # Next interval starts from zero
        summary2 = self.collector.end_interval(1, False)
        self.assertEqual(summary2["requests_generated"], 0)

    def test_history_window(self):
        collector = MetricsCollector(window_size=3)
        for i in range(5):
            collector.end_interval(i, False)
        history = collector.get_interval_history()
        self.assertEqual(len(history), 3)
        self.assertEqual(history[-1]["interval"], 4)

    def test_reset(self):
        self.collector.record_request_generated(3)
        self.collector.reset()
        self.assertEqual(self.collector.get_system_metrics().total_requests_generated, 0)
        self.assertEqual(self.collector.get_all_node_metrics(), [])

    def test_queue_and_timeout_accounting(self):
        self.collector.record_request_generated(4)
        self.collector.record_request_assigned(self.node)
        self.collector.record_request_assigned(self.node, queued=True)
        self.collector.record_request_completed("a", 10.0)
        self.collector.record_request_failed("a", reason="timeout")
        metrics = self.collector.get_system_metrics()
        self.assertEqual(metrics.total_requests_accepted, 2)
        self.assertEqual(metrics.total_requests_queued, 1)
        self.assertEqual(metrics.total_requests_completed, 1)
        self.assertEqual(metrics.total_requests_failed, 1)
        self.assertEqual(metrics.total_requests_timed_out, 1)
        self.assertAlmostEqual(metrics.completion_rate, 50.0)
        self.assertAlmostEqual(metrics.queue_rate, 50.0)
        self.assertAlmostEqual(metrics.timeout_rate, 50.0)
        node_metrics = self.collector.get_node_metrics("a")
        self.assertEqual(node_metrics.requests_queued, 1)
        self.assertEqual(node_metrics.requests_timed_out, 1)

    def test_rejection_reasons_are_separated(self):
        self.collector.record_request_rejected("overload")
        self.collector.record_request_rejected("no_capacity")
        metrics = self.collector.get_system_metrics()
        self.assertEqual(metrics.total_requests_rejected, 2)
        self.assertEqual(metrics.total_requests_rejected_overload, 1)
        self.assertEqual(metrics.total_requests_rejected_no_capacity, 1)

    def test_invalid_rejection_reason_rejected(self):
        with self.assertRaises(ValueError):
            self.collector.record_request_rejected("magic")
        with self.assertRaises(ValueError):
            self.collector.record_request_failed("a", reason="magic")

    def test_interval_summary_includes_admission_counts(self):
        self.collector.record_request_generated(2)
        self.collector.record_request_rejected("overload")
        self.collector.record_request_assigned(self.node, queued=True)
        summary = self.collector.end_interval(0, False)
        self.assertEqual(summary["requests_queued"], 1)
        self.assertEqual(summary["requests_rejected_overload"], 1)
        self.assertIn("requests_timed_out", summary)


if __name__ == "__main__":
    unittest.main()
