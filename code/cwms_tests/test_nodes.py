"""Unit tests for Node model and health behaviour."""
import unittest

from cwms_simulator.nodes import Node, NodeState, create_default_nodes


class TestNode(unittest.TestCase):
    def test_default_nodes(self):
        nodes = create_default_nodes()
        self.assertEqual([n.name for n in nodes], ["backend-a", "backend-b", "backend-c"])
        self.assertEqual(nodes[2].capacity, 75)
        self.assertTrue(all(n.healthy for n in nodes))

    def test_invalid_capacity_rejected(self):
        with self.assertRaises(ValueError):
            Node("bad", 0)

    def test_invalid_initial_load_rejected(self):
        with self.assertRaises(ValueError):
            Node("bad", 100, load=200)

    def test_assign_request_increments(self):
        node = Node("n1", 100)
        self.assertTrue(node.assign_request())
        self.assertEqual(node.assigned, 1)
        self.assertGreater(node.load, 0)
        self.assertLessEqual(node.load, node.max_load_cap)

    def test_unhealthy_node_rejects_assignment(self):
        node = Node("n1", 100)
        node.set_health(NodeState.UNHEALTHY)
        self.assertFalse(node.healthy)
        self.assertFalse(node.assign_request())
        self.assertEqual(node.assigned, 0)

    def test_load_capped(self):
        node = Node("n1", 1, max_load_cap=150)
        for _ in range(500):
            node.assign_request()
        self.assertEqual(node.load, 150)

    def test_decay_reduces_load(self):
        node = Node("n1", 100, load=80)
        node.decay_load()
        self.assertAlmostEqual(node.load, 44.0)

    def test_available_capacity(self):
        node = Node("n1", 100, load=25)
        self.assertAlmostEqual(node.available_capacity, 75.0)

    def test_to_dict_keys(self):
        data = Node("n1", 100, load=10).to_dict()
        for key in ("name", "capacity", "load", "state", "healthy", "assigned", "available_capacity"):
            self.assertIn(key, data)

    def test_reset(self):
        node = Node("n1", 100)
        node.assign_request()
        node.set_health(NodeState.UNHEALTHY)
        node.reset()
        self.assertEqual(node.load, 0)
        self.assertEqual(node.assigned, 0)
        self.assertTrue(node.healthy)

    def test_admission_accepts_below_threshold(self):
        node = Node("n1", 100, overload_threshold=80)
        self.assertEqual(node.admit_request(), "accepted")
        self.assertEqual(node.queued_total, 0)
        self.assertEqual(node.queue_depth, 0)

    def test_admission_queues_then_overflows(self):
        node = Node("n1", 100, load=100, overload_threshold=100, queue_limit=2)
        self.assertEqual(node.admit_request(), "queued")
        self.assertEqual(node.admit_request(), "queued")
        self.assertEqual(node.admit_request(), "overflow")
        self.assertEqual(node.assigned, 2)
        self.assertEqual(node.queued_total, 2)
        self.assertEqual(node.queue_depth, 2)
        self.assertEqual(node.max_queue_depth, 2)
        self.assertEqual(node.overflow_total, 1)
        node.reset_queue()
        self.assertEqual(node.queue_depth, 0)

    def test_unhealthy_node_does_not_admit(self):
        node = Node("n1", 100, load=100)
        node.set_health(NodeState.UNHEALTHY)
        self.assertEqual(node.admit_request(), "unhealthy")
        self.assertEqual(node.assigned, 0)

    def test_zero_queue_limit_rejects_overload(self):
        node = Node("n1", 100, load=100, queue_limit=0)
        self.assertEqual(node.admit_request(), "overflow")

    def test_invalid_admission_config_rejected(self):
        with self.assertRaises(ValueError):
            Node("bad", 100, overload_threshold=200)
        with self.assertRaises(ValueError):
            Node("bad", 100, queue_limit=-1)


if __name__ == "__main__":
    unittest.main()
