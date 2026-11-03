"""Unit tests for workload forecasting and error metrics."""
import unittest

from cwms_simulator.forecaster import WorkloadForecaster


class TestWorkloadForecaster(unittest.TestCase):
    def test_empty_forecast_is_zero(self):
        forecaster = WorkloadForecaster()
        self.assertEqual(forecaster.forecast(0).predicted, 0.0)

    def test_moving_average_value(self):
        forecaster = WorkloadForecaster(window_size=5)
        for value in (10, 20, 30):
            forecaster.observe(value)
        self.assertAlmostEqual(forecaster.forecast(3).predicted, 20.0)

    def test_window_limits_history(self):
        forecaster = WorkloadForecaster(window_size=3)
        for value in (100, 100, 100, 10, 10):
            forecaster.observe(value)
        # Only last three values (100, 10, 10) are in the window
        self.assertAlmostEqual(forecaster.forecast(5).predicted, 40.0)

    def test_peek_does_not_record(self):
        forecaster = WorkloadForecaster()
        forecaster.observe(10)
        self.assertEqual(forecaster.peek(), 10.0)
        self.assertEqual(len(forecaster.get_forecasts()), 0)

    def test_forecast_uses_only_past_observations(self):
        forecaster = WorkloadForecaster(window_size=5)
        forecaster.observe(10)
        forecaster.observe(20)
        first = forecaster.forecast(2)
        self.assertAlmostEqual(first.predicted, 15.0)
        # A future observation must not change an already produced forecast
        forecaster.observe(1000)
        self.assertAlmostEqual(first.predicted, 15.0)

    def test_evaluation_mae_rmse(self):
        forecaster = WorkloadForecaster(window_size=5)
        forecaster.observe(10)
        f1 = forecaster.forecast(1)
        f1.actual = 12          # abs error 2
        forecaster.observe(20)
        f2 = forecaster.forecast(2)
        f2.actual = 16          # predicted 15, abs error 1
        mae, rmse = forecaster.evaluate()
        self.assertAlmostEqual(mae, 1.5)
        self.assertAlmostEqual(rmse, (5 / 2) ** 0.5)

    def test_evaluation_without_actuals_is_none(self):
        forecaster = WorkloadForecaster()
        forecaster.observe(10)
        forecaster.forecast(1)
        self.assertEqual(forecaster.evaluate(), (None, None))
        self.assertEqual(forecaster.evaluate_naive(), (None, None))

    def test_naive_baseline_uses_only_prior_observation(self):
        forecaster = WorkloadForecaster()
        first = forecaster.forecast(0)
        self.assertIsNone(first.naive_predicted)

        forecaster.observe(10)
        second = forecaster.forecast(1)
        self.assertEqual(second.naive_predicted, 10)
        second.actual = 14
        forecaster.observe(14)

        third = forecaster.forecast(2)
        self.assertEqual(third.naive_predicted, 14)
        third.actual = 11

        mae, rmse = forecaster.evaluate_naive()
        self.assertAlmostEqual(mae, 3.5)
        self.assertAlmostEqual(rmse, (25 / 2) ** 0.5)

    def test_naive_forecast(self):
        self.assertEqual(WorkloadForecaster.naive_forecast([1, 5, 9]), 9)
        self.assertEqual(WorkloadForecaster.naive_forecast([]), 0.0)

    def test_static_evaluation(self):
        mae, rmse = WorkloadForecaster.evaluate_forecasts([10, 20], [12, 16])
        self.assertAlmostEqual(mae, 3.0)
        self.assertAlmostEqual(rmse, (20 / 2) ** 0.5)

    def test_static_evaluation_rejects_mismatch(self):
        with self.assertRaises(ValueError):
            WorkloadForecaster.evaluate_forecasts([1, 2], [1])
        with self.assertRaises(ValueError):
            WorkloadForecaster.evaluate_forecasts([], [])

    def test_invalid_window(self):
        with self.assertRaises(ValueError):
            WorkloadForecaster(window_size=0)

    def test_invalid_strategy(self):
        with self.assertRaises(ValueError):
            WorkloadForecaster(strategy="magic")

    def test_change_aware_uses_average_on_stable_traffic(self):
        forecaster = WorkloadForecaster(strategy="change_aware")
        for value in (38, 37, 41, 36, 40):
            forecaster.observe(value)
        result = forecaster.forecast(5)
        self.assertAlmostEqual(result.predicted, 38.4)
        self.assertEqual(result.method, "change_aware_average")
        self.assertAlmostEqual(result.ma_predicted, 38.4)

    def test_change_aware_switches_to_latest_after_regime_change(self):
        forecaster = WorkloadForecaster(strategy="change_aware")
        for value in (40, 38, 41, 39):
            forecaster.observe(value)
        forecaster.observe(160)
        result = forecaster.forecast(5)
        self.assertEqual(result.predicted, 160)
        self.assertEqual(result.method, "change_aware_last")
        self.assertAlmostEqual(result.ma_predicted, 63.6)

    def test_moving_average_comparison_is_separate(self):
        forecaster = WorkloadForecaster(strategy="change_aware")
        for value in (40, 38, 41, 39):
            forecaster.observe(value)
        result = forecaster.forecast(4)
        result.actual = 44
        self.assertAlmostEqual(forecaster.evaluate()[0], 4.5)
        self.assertAlmostEqual(forecaster.evaluate_moving_average()[0], 4.5)

        forecaster.observe(160)
        changed = forecaster.forecast(5)
        changed.actual = 165
        self.assertEqual(changed.method, "change_aware_last")
        self.assertAlmostEqual(forecaster.evaluate()[0], 4.75)
        self.assertGreater(forecaster.evaluate_moving_average()[0], 4.75)

    def test_reset(self):
        forecaster = WorkloadForecaster()
        forecaster.observe(10)
        forecaster.forecast(1)
        forecaster.reset()
        self.assertEqual(forecaster.get_history(), [])
        self.assertEqual(forecaster.get_forecasts(), [])


if __name__ == "__main__":
    unittest.main()
