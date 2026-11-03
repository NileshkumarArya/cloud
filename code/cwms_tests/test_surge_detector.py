"""Unit tests for surge detection."""
import unittest

from cwms_simulator.surge_detector import SurgeDetector


class TestSurgeDetector(unittest.TestCase):
    def test_rate_surge_detected_after_window(self):
        detector = SurgeDetector(rate_threshold=90, rate_window=3, load_threshold=999)
        self.assertIsNone(detector.check_surge(0, 100, [10, 10, 10]))
        self.assertIsNone(detector.check_surge(1, 100, [10, 10, 10]))
        event = detector.check_surge(2, 100, [10, 10, 10])
        self.assertIsNotNone(event)
        self.assertEqual(event.surge_type, "rate")
        self.assertEqual(event.threshold, 90)

    def test_no_surge_when_below_threshold(self):
        detector = SurgeDetector(rate_threshold=90, rate_window=3, load_threshold=999)
        for i in range(6):
            self.assertIsNone(detector.check_surge(i, 40, [5, 5, 5]))
        self.assertEqual(detector.get_surge_events(), [])

    def test_cooldown_suppresses_repeat(self):
        detector = SurgeDetector(rate_threshold=90, rate_window=1, load_threshold=999)
        self.assertIsNotNone(detector.check_surge(0, 100, [10]))
        self.assertIsNone(detector.check_surge(1, 100, [10]))
        # After cooldown (2 intervals) detection allowed again
        self.assertIsNotNone(detector.check_surge(2, 100, [10]))

    def test_load_surge(self):
        detector = SurgeDetector(rate_threshold=9999, rate_window=1,
                                 load_threshold=80, load_window=2)
        self.assertIsNone(detector.check_surge(0, 5, [90, 90, 90]))
        event = detector.check_surge(1, 5, [90, 90, 90])
        self.assertIsNotNone(event)
        self.assertEqual(event.surge_type, "load")

    def test_single_hot_node_detected_despite_low_average(self):
        detector = SurgeDetector(
            rate_threshold=9999,
            rate_window=1,
            load_threshold=80,
            max_load_threshold=100,
            load_window=1,
        )
        event = detector.check_surge(0, 5, [150, 10, 10])
        self.assertIsNotNone(event)
        self.assertEqual(event.surge_type, "max_load")

    def test_max_load_below_threshold_not_detected(self):
        detector = SurgeDetector(
            rate_threshold=9999,
            rate_window=1,
            load_threshold=999,
            max_load_threshold=100,
            load_window=1,
        )
        self.assertIsNone(detector.check_surge(0, 5, [99, 10, 10]))

    def test_empty_node_loads_safe(self):
        detector = SurgeDetector(rate_threshold=999, load_threshold=80, load_window=1)
        self.assertIsNone(detector.check_surge(0, 1, []))

    def test_reset(self):
        detector = SurgeDetector(rate_threshold=1, rate_window=1)
        detector.check_surge(0, 100, [10])
        detector.reset()
        self.assertEqual(detector.get_surge_events(), [])
        self.assertFalse(detector.is_surge_active())

    def test_update_thresholds(self):
        detector = SurgeDetector(rate_threshold=1000, rate_window=1)
        detector.update_thresholds(rate_threshold=10)
        self.assertIsNotNone(detector.check_surge(0, 50, [1]))

    def test_update_max_load_threshold(self):
        detector = SurgeDetector(
            rate_threshold=9999,
            rate_window=1,
            load_threshold=999,
            max_load_threshold=200,
            load_window=1,
        )
        self.assertIsNone(detector.check_surge(0, 1, [150]))
        detector.update_thresholds(max_load_threshold=100)
        self.assertIsNotNone(detector.check_surge(1, 1, [150]))

    def test_event_serialization(self):
        detector = SurgeDetector(rate_threshold=1, rate_window=1)
        event = detector.check_surge(0, 50, [1])
        data = event.to_dict()
        for key in ("interval", "requests", "threshold", "surge_type", "message"):
            self.assertIn(key, data)


if __name__ == "__main__":
    unittest.main()
