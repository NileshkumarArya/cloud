"""
Workload forecasting for CWMS simulator.
Implements a moving-average baseline, an optional change-aware variant, and
evaluation metrics.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple
from collections import deque
import math


@dataclass
class ForecastResult:
    """Result of a workload forecast."""
    interval: int
    predicted: float
    actual: Optional[float] = None
    method: str = "moving_average"
    window_size: int = 5
    naive_predicted: Optional[float] = None
    ma_predicted: Optional[float] = None
    
    @property
    def error(self) -> Optional[float]:
        """Forecast error (actual - predicted)."""
        if self.actual is None:
            return None
        return self.actual - self.predicted
    
    @property
    def absolute_error(self) -> Optional[float]:
        """Absolute forecast error."""
        err = self.error
        return abs(err) if err is not None else None
    
    @property
    def squared_error(self) -> Optional[float]:
        """Squared forecast error."""
        err = self.error
        return err * err if err is not None else None

    @property
    def naive_error(self) -> Optional[float]:
        """Naive (last-value) forecast error, when available."""
        if self.actual is None or self.naive_predicted is None:
            return None
        return self.actual - self.naive_predicted

    @property
    def naive_absolute_error(self) -> Optional[float]:
        err = self.naive_error
        return abs(err) if err is not None else None

    @property
    def naive_squared_error(self) -> Optional[float]:
        err = self.naive_error
        return err * err if err is not None else None

    @property
    def ma_error(self) -> Optional[float]:
        """Moving-average forecast error, when available."""
        if self.actual is None or self.ma_predicted is None:
            return None
        return self.actual - self.ma_predicted

    @property
    def ma_absolute_error(self) -> Optional[float]:
        err = self.ma_error
        return abs(err) if err is not None else None

    @property
    def ma_squared_error(self) -> Optional[float]:
        err = self.ma_error
        return err * err if err is not None else None
    
    def to_dict(self) -> dict:
        result = {
            "interval": self.interval,
            "predicted": round(self.predicted, 2),
            "method": self.method,
            "window_size": self.window_size,
        }
        if self.naive_predicted is not None:
            result["naive_predicted"] = round(self.naive_predicted, 2)
        if self.ma_predicted is not None:
            result["ma_predicted"] = round(self.ma_predicted, 2)
        if self.actual is not None:
            result["actual"] = self.actual
            result["error"] = round(self.error, 2)
            result["absolute_error"] = round(self.absolute_error, 2)
            result["squared_error"] = round(self.squared_error, 2)
            if self.naive_error is not None:
                result["naive_error"] = round(self.naive_error, 2)
            if self.ma_error is not None:
                result["ma_error"] = round(self.ma_error, 2)
        return result


class WorkloadForecaster:
    """
    Workload forecaster with a moving-average baseline and an optional
    change-aware strategy.

    The moving-average strategy is the documented baseline. The change-aware
    strategy keeps that average on stable traffic and switches to the latest
    observation when recent history indicates a regime change.

    Generates near-term forecasts from recent observations.
    Supports evaluation against actual values using MAE and RMSE.
    """

    STRATEGIES = ("moving_average", "change_aware")
    CHANGE_SPREAD_RATIO = 0.2
    
    def __init__(self, window_size: int = 5, strategy: str = "moving_average"):
        """
        Initialize forecaster.
        
        Args:
            window_size: Number of recent intervals for moving average
            strategy: "moving_average" or "change_aware"
        """
        if window_size < 1:
            raise ValueError("Window size must be at least 1")
        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown forecast strategy: {strategy}")
        self.window_size = window_size
        self.strategy = strategy
        self._history: deque = deque(maxlen=window_size)
        self._forecasts: List[ForecastResult] = []
    
    def observe(self, value: float) -> None:
        """Add an observed value to history."""
        self._history.append(value)

    def _history_snapshot(self) -> Tuple[float, ...]:
        return tuple(self._history)

    def _moving_average(self, history: Tuple[float, ...]) -> float:
        return sum(history) / len(history) if history else 0.0

    def _predict(self) -> Tuple[float, str]:
        history = self._history_snapshot()
        ma_predicted = self._moving_average(history)
        if not history:
            return 0.0, self.strategy
        if self.strategy == "moving_average":
            return ma_predicted, "moving_average"
        if len(history) >= 3:
            spread = max(history) - min(history)
            if spread > self.CHANGE_SPREAD_RATIO * max(1.0, ma_predicted):
                return history[-1], "change_aware_last"
        return ma_predicted, "change_aware_average"
    
    def forecast(self, interval: int) -> ForecastResult:
        """
        Generate forecast for the next interval using only past observations.
        
        Args:
            interval: Interval number for this forecast
            
        Returns:
            ForecastResult with predicted value
        """
        history = self._history_snapshot()
        predicted, method = self._predict()
        naive_predicted = history[-1] if history else None
        result = ForecastResult(
            interval=interval,
            predicted=predicted,
            method=method,
            window_size=len(history),
            naive_predicted=naive_predicted,
            ma_predicted=self._moving_average(history),
        )
        self._forecasts.append(result)
        return result
    
    def peek(self) -> float:
        """
        Return what the next forecast would be without recording it.
        Uses only observations already added via observe().
        """
        return self._predict()[0]
    
    def forecast_with_actual(self, interval: int, actual: float) -> ForecastResult:
        """
        Generate forecast and record actual value for evaluation.
        
        Args:
            interval: Interval number
            actual: Actual observed value
            
        Returns:
            ForecastResult with both predicted and actual values
        """
        result = self.forecast(interval)
        result.actual = actual
        return result
    
    def evaluate(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Evaluate forecast accuracy using MAE and RMSE.

        The first interval has no prior observation, so its arbitrary
        zero-valued prediction is excluded. This matches evaluate_naive()
        and keeps the two baselines comparable.

        Returns:
            Tuple of (MAE, RMSE) or (None, None) if insufficient data
        """
        errors = [
            f.absolute_error
            for f in self._forecasts
            if f.absolute_error is not None and f.window_size > 0
        ]
        squared_errors = [
            f.squared_error
            for f in self._forecasts
            if f.squared_error is not None and f.window_size > 0
        ]
        
        if not errors:
            return None, None
        
        mae = sum(errors) / len(errors)
        rmse = math.sqrt(sum(squared_errors) / len(squared_errors))
        
        return mae, rmse

    def evaluate_moving_average(self) -> Tuple[Optional[float], Optional[float]]:
        """Evaluate the pure moving-average forecast used as a comparison."""
        errors = [
            f.ma_absolute_error
            for f in self._forecasts
            if f.ma_absolute_error is not None and f.window_size > 0
        ]
        squared_errors = [
            f.ma_squared_error
            for f in self._forecasts
            if f.ma_squared_error is not None and f.window_size > 0
        ]
        if not errors:
            return None, None
        mae = sum(errors) / len(errors)
        rmse = math.sqrt(sum(squared_errors) / len(squared_errors))
        return mae, rmse

    def evaluate_naive(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Evaluate the causal last-value baseline with MAE and RMSE.

        Uses the same scored intervals as evaluate(): the first interval has
        no prior observation and is excluded.
        """
        errors = [
            f.naive_absolute_error
            for f in self._forecasts
            if f.naive_absolute_error is not None
        ]
        squared_errors = [
            f.naive_squared_error
            for f in self._forecasts
            if f.naive_squared_error is not None
        ]
        if not errors:
            return None, None
        mae = sum(errors) / len(errors)
        rmse = math.sqrt(sum(squared_errors) / len(squared_errors))
        return mae, rmse
    
    def get_forecasts(self) -> List[ForecastResult]:
        """Get all forecasts made."""
        return self._forecasts.copy()
    
    def get_history(self) -> List[float]:
        """Get current observation history."""
        return list(self._history)
    
    def reset(self) -> None:
        """Reset forecaster state."""
        self._history.clear()
        self._forecasts.clear()
    
    @staticmethod
    def naive_forecast(history: List[float]) -> float:
        """
        Naive forecast (last value).
        
        Args:
            history: Historical values
            
        Returns:
            Last observed value or 0 if empty
        """
        return history[-1] if history else 0.0
    
    @staticmethod
    def evaluate_forecasts(actuals: List[float], predicted: List[float]) -> Tuple[float, float]:
        """
        Evaluate a set of forecasts against actuals.
        
        Args:
            actuals: Actual observed values
            predicted: Predicted values
            
        Returns:
            Tuple of (MAE, RMSE)
        """
        if len(actuals) != len(predicted) or not actuals:
            raise ValueError("Actuals and predicted must have same non-zero length")
        
        n = len(actuals)
        mae = sum(abs(a - p) for a, p in zip(actuals, predicted)) / n
        rmse = math.sqrt(sum((a - p) ** 2 for a, p in zip(actuals, predicted)) / n)
        
        return mae, rmse