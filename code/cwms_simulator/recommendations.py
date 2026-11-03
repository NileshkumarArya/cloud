"""
Recommendation engine for CWMS simulator.
Generates capacity and operational recommendations based on rules.
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from .nodes import Node
from .metrics import SystemMetrics
from .surge_detector import SurgeEvent


class RecommendationType(Enum):
    """Types of recommendations."""
    ADD_CAPACITY = "add_capacity"
    INVESTIGATE_DISTRIBUTION = "investigate_distribution"
    NODE_UNHEALTHY = "node_unhealthy"
    REDUCE_CAPACITY = "reduce_capacity"
    MONITOR = "monitor"
    NO_ACTION = "no_action"


class Severity(Enum):
    """Recommendation severity levels."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Recommendation:
    """A capacity or operational recommendation."""
    type: RecommendationType
    severity: Severity
    message: str
    details: dict
    
    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
        }


class RecommendationEngine:
    """
    Rule-based recommendation engine.
    
    Generates interpretable capacity and operational recommendations
    based on current system state, surge events, and node health.
    Does not automatically provision or scale resources.
    """
    
    def __init__(
        self,
        high_load_threshold: float = 80.0,
        imbalance_threshold: float = 30.0,
        sustained_low_load_threshold: float = 20.0,
        sustained_low_load_intervals: int = 10,
    ):
        """
        Initialize recommendation engine.
        
        Args:
            high_load_threshold: Load % considered high
            imbalance_threshold: Load difference % to trigger distribution investigation
            sustained_low_load_threshold: Load % considered low for sustained period
            sustained_low_load_intervals: Intervals of low load before recommending reduction
        """
        self.high_load_threshold = high_load_threshold
        self.imbalance_threshold = imbalance_threshold
        self.sustained_low_load_threshold = sustained_low_load_threshold
        self.sustained_low_load_intervals = sustained_low_load_intervals
        
        self._low_load_counter = 0
        self._recommendations: List[Recommendation] = []
    
    def evaluate(
        self,
        nodes: List[Node],
        system_metrics: SystemMetrics,
        surge_event: Optional[SurgeEvent] = None,
    ) -> List[Recommendation]:
        """
        Evaluate current state and generate recommendations.
        
        Args:
            nodes: List of backend nodes
            system_metrics: Current system metrics
            surge_event: Current surge event if any
            
        Returns:
            List of recommendations
        """
        self._recommendations.clear()
        healthy_nodes = [n for n in nodes if n.healthy]
        
        if not healthy_nodes:
            self._add_recommendation(
                RecommendationType.NODE_UNHEALTHY,
                Severity.CRITICAL,
                "CRITICAL: No healthy backends available; restore capacity immediately",
                {"healthy_nodes": 0, "total_nodes": len(nodes)},
            )
            return self._recommendations
        
        max_load = max(n.load for n in healthy_nodes)
        min_load = min(n.load for n in healthy_nodes)
        avg_load = sum(n.load for n in healthy_nodes) / len(healthy_nodes)
        load_imbalance = max_load - min_load
        
        # Check for sustained low load
        if max_load < self.sustained_low_load_threshold:
            self._low_load_counter += 1
        else:
            self._low_load_counter = 0
        
        # Rule 1: High load + surge -> add capacity
        if max_load >= self.high_load_threshold and surge_event:
            self._add_recommendation(
                RecommendationType.ADD_CAPACITY,
                Severity.WARNING,
                "High load combined with traffic surge; consider adding capacity",
                {
                    "max_load": round(max_load, 1),
                    "surge_type": surge_event.surge_type if surge_event else None,
                    "threshold": self.high_load_threshold,
                },
            )
        
        # Rule 2: High load without surge
        elif max_load >= self.high_load_threshold:
            self._add_recommendation(
                RecommendationType.ADD_CAPACITY,
                Severity.WARNING,
                "High simulated node load; inspect distribution or capacity",
                {
                    "max_load": round(max_load, 1),
                    "threshold": self.high_load_threshold,
                },
            )
        
        # Rule 3: Load imbalance
        elif load_imbalance >= self.imbalance_threshold:
            busiest = max(healthy_nodes, key=lambda n: n.load)
            least_busy = min(healthy_nodes, key=lambda n: n.load)
            self._add_recommendation(
                RecommendationType.INVESTIGATE_DISTRIBUTION,
                Severity.INFO,
                f"Load imbalance detected: {busiest.name} ({busiest.load:.1f}%) vs "
                f"{least_busy.name} ({least_busy.load:.1f}%); investigate distribution policy",
                {
                    "busiest_node": busiest.name,
                    "busiest_load": round(busiest.load, 1),
                    "least_busy_node": least_busy.name,
                    "least_busy_load": round(least_busy.load, 1),
                    "imbalance": round(load_imbalance, 1),
                    "threshold": self.imbalance_threshold,
                },
            )
        
        # Rule 4: Surge without high load
        elif surge_event:
            self._add_recommendation(
                RecommendationType.MONITOR,
                Severity.INFO,
                "Traffic surge detected; monitor latency and capacity",
                {
                    "surge_type": surge_event.surge_type,
                    "requests": surge_event.requests,
                    "threshold": surge_event.threshold,
                },
            )
        
        # Rule 5: Sustained low load
        elif self._low_load_counter >= self.sustained_low_load_intervals:
            self._add_recommendation(
                RecommendationType.REDUCE_CAPACITY,
                Severity.INFO,
                f"Low load sustained for {self._low_load_counter} intervals; "
                "review whether capacity can be reduced (do not auto-remove)",
                {
                    "max_load": round(max_load, 1),
                    "low_load_intervals": self._low_load_counter,
                    "threshold": self.sustained_low_load_threshold,
                },
            )
        
        # Rule 6: Unhealthy nodes
        unhealthy = [n for n in nodes if not n.healthy]
        if unhealthy:
            for node in unhealthy:
                self._add_recommendation(
                    RecommendationType.NODE_UNHEALTHY,
                    Severity.WARNING,
                    f"Node {node.name} is unhealthy; skipping for new assignments",
                    {"node": node.name, "state": "unhealthy"},
                )
        
        # Rule 7: No action needed
        if not self._recommendations:
            self._add_recommendation(
                RecommendationType.NO_ACTION,
                Severity.INFO,
                "No capacity action indicated by current rules",
                {"max_load": round(max_load, 1), "avg_load": round(avg_load, 1)},
            )
        
        return self._recommendations
    
    def _add_recommendation(
        self,
        rec_type: RecommendationType,
        severity: Severity,
        message: str,
        details: dict,
    ) -> None:
        """Add a recommendation to the list."""
        self._recommendations.append(Recommendation(rec_type, severity, message, details))
    
    def get_recommendations(self) -> List[Recommendation]:
        """Get current recommendations."""
        return self._recommendations.copy()
    
    def get_latest(self) -> Optional[Recommendation]:
        """Get the most recent recommendation."""
        return self._recommendations[-1] if self._recommendations else None
    
    def reset(self) -> None:
        """Reset engine state."""
        self._low_load_counter = 0
        self._recommendations.clear()