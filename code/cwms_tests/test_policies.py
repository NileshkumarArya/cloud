"""Unit tests for scheduling policies."""
import unittest

from cwms_simulator.nodes import Node, NodeState
from cwms_simulator.policies import (
    PolicyFactory,
    RoundRobinPolicy,
    LeastLoadedPolicy,
    FCFSPolicy,
    AdaptivePolicy,
    SchedulingPolicy,
)


class TestRoundRobin(unittest.TestCase):
    def setUp(self):
        self.nodes = [Node("a", 100), Node("b", 100), Node("c", 100)]
        self.policy = RoundRobinPolicy()

    def test_cycles_in_order(self):
        picked = [self.policy.select_node(self.nodes).name for _ in range(6)]
        self.assertEqual(picked, ["a", "b", "c", "a", "b", "c"])

    def test_skips_unhealthy(self):
        self.nodes[1].set_health(NodeState.UNHEALTHY)
        picked = [self.policy.select_node(self.nodes).name for _ in range(4)]
        self.assertNotIn("b", picked)
        self.assertEqual(picked, ["a", "c", "a", "c"])

    def test_no_healthy_returns_none(self):
        for node in self.nodes:
            node.set_health(NodeState.UNHEALTHY)
        self.assertIsNone(self.policy.select_node(self.nodes))

    def test_reset(self):
        self.policy.select_node(self.nodes)
        self.policy.reset()
        self.assertEqual(self.policy.select_node(self.nodes).name, "a")

    def test_empty_list(self):
        self.assertIsNone(self.policy.select_node([]))


class TestLeastLoaded(unittest.TestCase):
    def test_picks_lowest_load(self):
        nodes = [Node("a", 100, load=70), Node("b", 100, load=20), Node("c", 100, load=50)]
        self.assertEqual(LeastLoadedPolicy().select_node(nodes).name, "b")

    def test_ignores_unhealthy_even_if_idle(self):
        nodes = [Node("a", 100, load=90), Node("b", 100, load=0)]
        nodes[1].set_health(NodeState.UNHEALTHY)
        self.assertEqual(LeastLoadedPolicy().select_node(nodes).name, "a")

    def test_no_healthy_returns_none(self):
        nodes = [Node("a", 100)]
        nodes[0].set_health(NodeState.UNHEALTHY)
        self.assertIsNone(LeastLoadedPolicy().select_node(nodes))

    def test_tie_is_deterministic(self):
        nodes = [Node("a", 100, load=10), Node("b", 100, load=10)]
        policy = LeastLoadedPolicy()
        self.assertEqual(policy.select_node(nodes).name, "a")
        self.assertEqual(policy.select_node(nodes).name, "a")

    def test_tie_breaks_toward_fewer_assignments(self):
        nodes = [Node("a", 100, load=150), Node("b", 100, load=150)]
        nodes[0].assigned = 1000
        nodes[1].assigned = 10
        self.assertEqual(LeastLoadedPolicy().select_node(nodes).name, "b")


class TestFCFS(unittest.TestCase):
    def test_always_first_healthy(self):
        nodes = [Node("a", 100, load=90), Node("b", 100, load=5)]
        policy = FCFSPolicy()
        self.assertEqual(policy.select_node(nodes).name, "a")
        self.assertEqual(policy.select_node(nodes).name, "a")

    def test_skips_unhealthy_first(self):
        nodes = [Node("a", 100), Node("b", 100)]
        nodes[0].set_health(NodeState.UNHEALTHY)
        self.assertEqual(FCFSPolicy().select_node(nodes).name, "b")

    def test_none_when_empty(self):
        self.assertIsNone(FCFSPolicy().select_node([]))


class TestAdaptive(unittest.TestCase):
    def test_without_forecast_uses_least_loaded(self):
        nodes = [Node("a", 100, load=80), Node("b", 100, load=10)]
        policy = AdaptivePolicy()
        self.assertEqual(policy.select_node(nodes).name, "b")
        self.assertEqual(policy.last_mode, "least-loaded")

    def test_overload_forecast_prefers_capacity(self):
        nodes = [Node("a", 100, load=20), Node("b", 50, load=30)]
        policy = AdaptivePolicy(forecast_provider=lambda: 10000)
        self.assertEqual(policy.select_node(nodes).name, "a")
        self.assertEqual(policy.last_mode, "capacity-first")

    def test_forecast_error_falls_back(self):
        def broken():
            raise RuntimeError("boom")

        nodes = [Node("a", 100, load=50), Node("b", 100, load=5)]
        policy = AdaptivePolicy(forecast_provider=broken)
        self.assertEqual(policy.select_node(nodes).name, "b")

    def test_capacity_tie_breaks_toward_fewer_assignments(self):
        nodes = [Node("a", 100, load=150), Node("b", 100, load=150)]
        nodes[0].assigned = 1000
        nodes[1].assigned = 10
        policy = AdaptivePolicy(forecast_provider=lambda: 10000)
        self.assertEqual(policy.select_node(nodes).name, "b")
        self.assertEqual(policy.last_mode, "capacity-first")

    def test_no_healthy(self):
        nodes = [Node("a", 100)]
        nodes[0].set_health(NodeState.UNHEALTHY)
        self.assertIsNone(AdaptivePolicy().select_node(nodes))


class TestPolicyFactory(unittest.TestCase):
    def test_available(self):
        self.assertEqual(
            PolicyFactory.available_policies(),
            ["round-robin", "least-loaded", "fcfs", "adaptive"],
        )

    def test_create_each(self):
        self.assertIsInstance(PolicyFactory.create("round-robin"), RoundRobinPolicy)
        self.assertIsInstance(PolicyFactory.create("least-loaded"), LeastLoadedPolicy)
        self.assertIsInstance(PolicyFactory.create("fcfs"), FCFSPolicy)
        self.assertIsInstance(PolicyFactory.create("adaptive"), AdaptivePolicy)

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            PolicyFactory.create("shortest-job-first")

    def test_policies_are_scheduling_policy(self):
        for name in PolicyFactory.available_policies():
            self.assertIsInstance(PolicyFactory.create(name), SchedulingPolicy)


if __name__ == "__main__":
    unittest.main()
