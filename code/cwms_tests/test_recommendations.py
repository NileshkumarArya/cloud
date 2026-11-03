"""Unit tests for the rule-based recommendation engine."""
import unittest

from cwms_simulator.nodes import Node, NodeState
from cwms_simulator.metrics import SystemMetrics
from cwms_simulator.recommendations import (
    RecommendationEngine,
    RecommendationType,
    Severity,
)
from cwms_simulator.surge_detector import SurgeEvent


def surge(interval=0, requests=200):
    return SurgeEvent(interval, requests, 90, "rate", "surge")


class TestRecommendationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = RecommendationEngine()

    def test_no_healthy_nodes_critical(self):
        nodes = [Node("a", 100), Node("b", 100)]
        for n in nodes:
            n.set_health(NodeState.UNHEALTHY)
        recs = self.engine.evaluate(nodes, SystemMetrics())
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].type, RecommendationType.NODE_UNHEALTHY)
        self.assertEqual(recs[0].severity, Severity.CRITICAL)
        self.assertIn("CRITICAL", recs[0].message)

    def test_high_load_with_surge_adds_capacity(self):
        nodes = [Node("a", 100, load=95), Node("b", 100, load=90)]
        recs = self.engine.evaluate(nodes, SystemMetrics(), surge())
        types = [r.type for r in recs]
        self.assertIn(RecommendationType.ADD_CAPACITY, types)
        self.assertEqual(recs[0].severity, Severity.WARNING)

    def test_high_load_without_surge(self):
        nodes = [Node("a", 100, load=95), Node("b", 100, load=90)]
        recs = self.engine.evaluate(nodes, SystemMetrics())
        self.assertEqual(recs[0].type, RecommendationType.ADD_CAPACITY)
        self.assertIn("inspect distribution", recs[0].message)

    def test_load_imbalance(self):
        nodes = [Node("a", 100, load=70), Node("b", 100, load=5)]
        recs = self.engine.evaluate(nodes, SystemMetrics())
        self.assertEqual(recs[0].type, RecommendationType.INVESTIGATE_DISTRIBUTION)
        self.assertEqual(recs[0].severity, Severity.INFO)

    def test_surge_only_monitor(self):
        nodes = [Node("a", 100, load=20), Node("b", 100, load=20)]
        recs = self.engine.evaluate(nodes, SystemMetrics(), surge())
        self.assertEqual(recs[0].type, RecommendationType.MONITOR)

    def test_no_action(self):
        nodes = [Node("a", 100, load=30), Node("b", 100, load=35)]
        recs = self.engine.evaluate(nodes, SystemMetrics())
        self.assertEqual(recs[0].type, RecommendationType.NO_ACTION)

    def test_sustained_low_load_recommends_review(self):
        engine = RecommendationEngine(
            sustained_low_load_threshold=20,
            sustained_low_load_intervals=3,
        )
        nodes = [Node("a", 100, load=5), Node("b", 100, load=5)]
        for _ in range(3):
            recs = engine.evaluate(nodes, SystemMetrics())
        self.assertEqual(recs[0].type, RecommendationType.REDUCE_CAPACITY)

    def test_unhealthy_node_reported_alongside_state(self):
        nodes = [Node("a", 100, load=20), Node("b", 100, load=20)]
        nodes[1].set_health(NodeState.UNHEALTHY)
        recs = self.engine.evaluate(nodes, SystemMetrics())
        unhealthy = [r for r in recs if r.type == RecommendationType.NODE_UNHEALTHY]
        self.assertEqual(len(unhealthy), 1)
        self.assertIn("b", unhealthy[0].message)

    def test_serialization(self):
        nodes = [Node("a", 100, load=95)]
        recs = self.engine.evaluate(nodes, SystemMetrics())
        data = recs[0].to_dict()
        for key in ("type", "severity", "message", "details"):
            self.assertIn(key, data)

    def test_reset(self):
        engine = RecommendationEngine(sustained_low_load_threshold=20,
                                      sustained_low_load_intervals=1)
        nodes = [Node("a", 100, load=1)]
        engine.evaluate(nodes, SystemMetrics())
        engine.reset()
        self.assertEqual(engine.get_recommendations(), [])


if __name__ == "__main__":
    unittest.main()
