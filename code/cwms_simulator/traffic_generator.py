"""
Traffic generator for CWMS simulator.
Creates synthetic request events for repeatable scenarios.
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import random


class TrafficScenario(Enum):
    """Predefined traffic scenarios."""
    NORMAL = "normal"
    BURST = "burst"
    FAILURE = "failure"
    CUSTOM = "custom"


@dataclass
class TrafficConfig:
    """Configuration for traffic generation."""
    base_rate: int = 40           # Requests per interval (normal)
    burst_rate: int = 140         # Requests per interval (burst)
    burst_start: int = 8          # Interval when burst starts
    burst_end: int = 13           # Interval when burst ends (exclusive)
    intervals: int = 20           # Total simulation intervals
    variation: float = 0.1        # Random variation factor (+/-10%)
    seed: int = 7                 # Random seed for reproducibility
    scenario: TrafficScenario = TrafficScenario.CUSTOM


class TrafficGenerator:
    """
    Generates synthetic request traffic for simulation.
    
    Supports normal traffic, burst scenarios, and configurable patterns.
    All values are simulated and not real cloud measurements.
    """
    
    def __init__(self, config: TrafficConfig):
        self.config = config
        self._rng = random.Random(config.seed)
        self._interval = 0
    
    def generate_requests(self, interval: int) -> int:
        """
        Generate number of requests for a given interval.
        
        Args:
            interval: Current simulation interval (0-indexed)
            
        Returns:
            Number of requests for this interval
        """
        self._interval = interval
        
        # Determine base rate for this interval
        if self.config.burst_start <= interval < self.config.burst_end:
            rate = self.config.burst_rate
        else:
            rate = self.config.base_rate
        
        # Apply deterministic variation
        variation_factor = self._rng.uniform(1 - self.config.variation, 1 + self.config.variation)
        requests = max(0, int(rate * variation_factor))
        
        return requests
    
    def generate_sequence(self) -> List[int]:
        """
        Generate complete request sequence for all intervals.
        
        Returns:
            List of request counts per interval
        """
        return [self.generate_requests(i) for i in range(self.config.intervals)]
    
    def reset(self, seed: Optional[int] = None) -> None:
        """Reset generator with optional new seed."""
        if seed is not None:
            self.config.seed = seed
        self._rng = random.Random(self.config.seed)
        self._interval = 0
    
    @classmethod
    def from_scenario(cls, scenario: TrafficScenario, **kwargs) -> "TrafficGenerator":
        """
        Create generator from predefined scenario.
        
        Args:
            scenario: Predefined traffic scenario
            **kwargs: Override default parameters
            
        Returns:
            Configured TrafficGenerator instance
        """
        defaults = {
            TrafficScenario.NORMAL: {
                "base_rate": 40,
                "burst_rate": 40,
                "burst_start": 0,
                "burst_end": 0,
                "intervals": 20,
            },
            TrafficScenario.BURST: {
                "base_rate": 40,
                "burst_rate": 180,
                "burst_start": 8,
                "burst_end": 13,
                "intervals": 20,
            },
            TrafficScenario.FAILURE: {
                "base_rate": 50,
                "burst_rate": 50,
                "burst_start": 0,
                "burst_end": 0,
                "intervals": 20,
            },
            TrafficScenario.CUSTOM: {
                "base_rate": 40,
                "burst_rate": 140,
                "burst_start": 8,
                "burst_end": 13,
                "intervals": 20,
            },
        }
        
        params = defaults[scenario].copy()
        params.update(kwargs)
        config = TrafficConfig(scenario=scenario, **params)
        return cls(config)