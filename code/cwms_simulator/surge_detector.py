"""
Surge detection for CWMS simulator.
Detects traffic spikes based on configurable thresholds.
"""
from dataclasses import dataclass
from typing import List, Optional
from collections import deque


@dataclass
class SurgeEvent:
    """Represents a detected traffic surge."""
    interval: int
    requests: int
    threshold: int
    surge_type: str  # "rate", "load", or "max_load"
    message: str
    
    def to_dict(self) -> dict:
        return {
            "interval": self.interval,
            "requests": self.requests,
            "threshold": self.threshold,
            "surge_type": self.surge_type,
            "message": self.message,
        }


class SurgeDetector:
    """
    Detects traffic surges based on request rate and node load thresholds.
    
    Supports configurable thresholds for request rate, average node load, and
    maximum node load. All detections are based on simulated metrics.
    """
    
    def __init__(
        self,
        rate_threshold: int = 90,
        load_threshold: float = 80.0,
        rate_window: int = 3,
        load_window: int = 3,
        max_load_threshold: float = 100.0,
    ):
        """
        Initialize surge detector.
        
        Args:
            rate_threshold: Request rate threshold per interval
            load_threshold: Average node load percentage threshold
            rate_window: Number of intervals for rate averaging
            load_window: Number of intervals for load averaging
            max_load_threshold: Maximum single-node load percentage threshold
        """
        self.rate_threshold = rate_threshold
        self.load_threshold = load_threshold
        self.max_load_threshold = max_load_threshold
        self.rate_window = rate_window
        self.load_window = load_window
        
        self._rate_history: deque = deque(maxlen=rate_window)
        self._load_history: deque = deque(maxlen=load_window)
        self._max_load_history: deque = deque(maxlen=load_window)
        self._surge_events: List[SurgeEvent] = []
        self._last_surge_interval = -999
        self._cooldown = 2  # Intervals before detecting another surge
    
    def check_surge(
        self,
        interval: int,
        requests: int,
        node_loads: List[float],
    ) -> Optional[SurgeEvent]:
        """
        Check for surge conditions.
        
        Args:
            interval: Current interval number
            requests: Number of requests in this interval
            node_loads: List of current node loads
            
        Returns:
            SurgeEvent if surge detected, None otherwise
        """
        self._rate_history.append(requests)
        
        avg_load = sum(node_loads) / len(node_loads) if node_loads else 0.0
        max_load = max(node_loads) if node_loads else 0.0
        self._load_history.append(avg_load)
        self._max_load_history.append(max_load)
        
        # Check cooldown
        if interval - self._last_surge_interval < self._cooldown:
            return None
        
        surge_event = None
        
        # Check rate-based surge
        if len(self._rate_history) >= self.rate_window:
            avg_rate = sum(self._rate_history) / len(self._rate_history)
            if avg_rate >= self.rate_threshold:
                surge_event = SurgeEvent(
                    interval=interval,
                    requests=requests,
                    threshold=self.rate_threshold,
                    surge_type="rate",
                    message=f"Request rate surge: {avg_rate:.1f} req/interval (threshold: {self.rate_threshold})",
                )
        
        if surge_event is None and len(self._max_load_history) >= self.load_window:
            avg_max_load = sum(self._max_load_history) / len(self._max_load_history)
            if avg_max_load >= self.max_load_threshold:
                surge_event = SurgeEvent(
                    interval=interval,
                    requests=requests,
                    threshold=int(self.max_load_threshold),
                    surge_type="max_load",
                    message=f"Single-node load surge: {avg_max_load:.1f}% max load (threshold: {self.max_load_threshold}%)",
                )
        
        # Check load-based surge
        if surge_event is None and len(self._load_history) >= self.load_window:
            avg_load = sum(self._load_history) / len(self._load_history)
            if avg_load >= self.load_threshold:
                surge_event = SurgeEvent(
                    interval=interval,
                    requests=requests,
                    threshold=int(self.load_threshold),
                    surge_type="load",
                    message=f"Node load surge: {avg_load:.1f}% avg load (threshold: {self.load_threshold}%)",
                )
        
        if surge_event:
            self._surge_events.append(surge_event)
            self._last_surge_interval = interval
        
        return surge_event
    
    def get_surge_events(self) -> List[SurgeEvent]:
        """Get all detected surge events."""
        return self._surge_events.copy()
    
    def is_surge_active(self) -> bool:
        """Check whether any surge has been detected in this run."""
        return self._last_surge_interval >= 0
    
    def reset(self) -> None:
        """Reset detector state."""
        self._rate_history.clear()
        self._load_history.clear()
        self._max_load_history.clear()
        self._surge_events.clear()
        self._last_surge_interval = -999
    
    def update_thresholds(
        self,
        rate_threshold: Optional[int] = None,
        load_threshold: Optional[float] = None,
        max_load_threshold: Optional[float] = None,
    ) -> None:
        """Update detection thresholds."""
        if rate_threshold is not None:
            self.rate_threshold = rate_threshold
        if load_threshold is not None:
            self.load_threshold = load_threshold
        if max_load_threshold is not None:
            self.max_load_threshold = max_load_threshold