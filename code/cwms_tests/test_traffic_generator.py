"""Unit tests for synthetic traffic generation."""
import unittest

from cwms_simulator.traffic_generator import (
    TrafficGenerator,
    TrafficConfig,
    TrafficScenario,
)


class TestTrafficGenerator(unittest.TestCase):
    def test_same_seed_is_reproducible(self):
        gen1 = TrafficGenerator(TrafficConfig(seed=42))
        gen2 = TrafficGenerator(TrafficConfig(seed=42))
        self.assertEqual(gen1.generate_sequence(), gen2.generate_sequence())

    def test_different_seed_differs(self):
        gen1 = TrafficGenerator(TrafficConfig(seed=1))
        gen2 = TrafficGenerator(TrafficConfig(seed=2))
        self.assertNotEqual(gen1.generate_sequence(), gen2.generate_sequence())

    def test_sequence_length(self):
        gen = TrafficGenerator(TrafficConfig(intervals=7))
        self.assertEqual(len(gen.generate_sequence()), 7)

    def test_burst_interval_has_higher_rate(self):
        gen = TrafficGenerator(TrafficConfig(
            base_rate=40, burst_rate=200, burst_start=2, burst_end=4,
            intervals=6, variation=0.0,
        ))
        sequence = gen.generate_sequence()
        self.assertEqual(sequence[:2], [40, 40])
        self.assertEqual(sequence[2:4], [200, 200])
        self.assertEqual(sequence[4:], [40, 40])

    def test_variation_bounds(self):
        gen = TrafficGenerator(TrafficConfig(base_rate=100, burst_rate=100,
                                             burst_start=0, burst_end=0,
                                             intervals=50, variation=0.1, seed=3))
        for value in gen.generate_sequence():
            self.assertGreaterEqual(value, 90)
            self.assertLessEqual(value, 110)

    def test_zero_variation_exact(self):
        gen = TrafficGenerator(TrafficConfig(base_rate=55, burst_rate=55,
                                             burst_start=0, burst_end=0,
                                             intervals=3, variation=0.0))
        self.assertEqual(gen.generate_sequence(), [55, 55, 55])

    def test_normal_scenario_has_no_burst(self):
        gen = TrafficGenerator.from_scenario(TrafficScenario.NORMAL, variation=0.0)
        values = gen.generate_sequence()
        self.assertEqual(set(values), {40})

    def test_burst_scenario_triggers_burst(self):
        gen = TrafficGenerator.from_scenario(TrafficScenario.BURST, variation=0.0)
        values = gen.generate_sequence()
        self.assertEqual(max(values), 180)
        self.assertEqual(min(values), 40)

    def test_failure_scenario_defaults(self):
        gen = TrafficGenerator.from_scenario(TrafficScenario.FAILURE, variation=0.0)
        self.assertEqual(gen.config.base_rate, 50)
        self.assertEqual(gen.config.intervals, 20)

    def test_reset_reproducible(self):
        gen = TrafficGenerator(TrafficConfig(seed=5))
        first = gen.generate_sequence()
        gen.reset(seed=5)
        self.assertEqual(first, gen.generate_sequence())


if __name__ == "__main__":
    unittest.main()
