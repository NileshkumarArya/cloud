"""
Metrics collection for CWMS simulator.
Tracks request counts, node load, response times, and system-wide metrics.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import deque
from .nodes import Node


@dataclass
class NodeMetrics:
    """Metrics for a single node."""
    name: str
    requests_assigned: int = 0
    requests_completed: int = 0
    requests_failed: int = 0
    requests_queued: int = 0
    requests_timed_out: int = 0
    total_latency: float = 0.0
    max_load: float = 0.0
    current_load: float = 0.0
    healthy: bool = True
    
    @property
    def avg_latency(self) -> float:
        """Average latency for completed requests."""
        if self.requests_completed == 0:
            return 0.0
        return self.total_latency / self.requests_completed
    
    @property
    def error_rate(self) -> float:
        """Error rate as percentage."""
        total = self.requests_completed + self.requests_failed
        if total == 0:
            return 0.0
        return (self.requests_failed / total) * 100
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "requests_assigned": self.requests_assigned,
            "requests_completed": self.requests_completed,
            "requests_failed": self.requests_failed,
            "requests_queued": self.requests_queued,
            "requests_timed_out": self.requests_timed_out,
            "avg_latency": round(self.avg_latency, 2),
            "max_load": round(self.max_load, 2),
            "current_load": round(self.current_load, 2),
            "healthy": self.healthy,
            "error_rate": round(self.error_rate, 2),
        }


@dataclass
class SystemMetrics:
    """System-wide aggregated metrics."""
    total_requests_generated: int = 0
    total_requests_assigned: int = 0
    total_requests_completed: int = 0
    total_requests_rejected: int = 0
    total_requests_failed: int = 0
    total_requests_queued: int = 0
    total_requests_timed_out: int = 0
    total_requests_rejected_overload: int = 0
    total_requests_rejected_no_capacity: int = 0
    intervals_elapsed: int = 0
    surge_events: int = 0

    @property
    def total_requests_accepted(self) -> int:
        """Requests admitted immediately or queued (not rejected)."""
        return self.total_requests_assigned
    
    @property
    def assignment_rate(self) -> float:
        """Percentage of generated requests that were admitted."""
        if self.total_requests_generated == 0:
            return 0.0
        return (self.total_requests_assigned / self.total_requests_generated) * 100
    
    @property
    def completion_rate(self) -> float:
        """Percentage of admitted requests that completed."""
        if self.total_requests_assigned == 0:
            return 0.0
        return (self.total_requests_completed / self.total_requests_assigned) * 100
    
    @property
    def rejection_rate(self) -> float:
        """Percentage of generated requests that were rejected."""
        if self.total_requests_generated == 0:
            return 0.0
        return (self.total_requests_rejected / self.total_requests_generated) * 100

    @property
    def failure_rate(self) -> float:
        """Percentage of admitted requests that failed or timed out."""
        if self.total_requests_assigned == 0:
            return 0.0
        return (self.total_requests_failed / self.total_requests_assigned) * 100

    @property
    def queue_rate(self) -> float:
        """Percentage of admitted requests that waited in a queue."""
        if self.total_requests_assigned == 0:
            return 0.0
        return (self.total_requests_queued / self.total_requests_assigned) * 100

    @property
    def timeout_rate(self) -> float:
        """Percentage of admitted requests that timed out."""
        if self.total_requests_assigned == 0:
            return 0.0
        return (self.total_requests_timed_out / self.total_requests_assigned) * 100
    
    def to_dict(self) -> dict:
        return {
            "total_requests_generated": self.total_requests_generated,
            "total_requests_accepted": self.total_requests_accepted,
            "total_requests_assigned": self.total_requests_assigned,
            "total_requests_completed": self.total_requests_completed,
            "total_requests_rejected": self.total_requests_rejected,
            "total_requests_failed": self.total_requests_failed,
            "total_requests_queued": self.total_requests_queued,
            "total_requests_timed_out": self.total_requests_timed_out,
            "total_requests_rejected_overload": self.total_requests_rejected_overload,
            "total_requests_rejected_no_capacity": self.total_requests_rejected_no_capacity,
            "intervals_elapsed": self.intervals_elapsed,
            "surge_events": self.surge_events,
            "assignment_rate": round(self.assignment_rate, 2),
            "completion_rate": round(self.completion_rate, 2),
            "rejection_rate": round(self.rejection_rate, 2),
            "failure_rate": round(self.failure_rate, 2),
            "queue_rate": round(self.queue_rate, 2),
            "timeout_rate": round(self.timeout_rate, 2),
        }


class MetricsCollector:
    """
    Collects and aggregates metrics during simulation.
    
    Tracks per-node and system-wide metrics for analysis and reporting.
    All metrics are based on simulated values, not real cloud telemetry.
    """
    
    def __init__(self, window_size: int = 100):
        self.node_metrics: Dict[str, NodeMetrics] = {}
        self.system_metrics = SystemMetrics()
        self._interval_history: deque = deque(maxlen=window_size)
        self._current_interval_requests = 0
        self._current_interval_assigned = 0
        self._current_interval_rejected = 0
        self._current_interval_queued = 0
        self._current_interval_completed = 0
        self._current_interval_failed = 0
        self._current_interval_timed_out = 0
        self._current_interval_rejected_overload = 0
        self._current_interval_rejected_no_capacity = 0
    
    def register_node(self, node: Node) -> None:
        """Register a node for metrics tracking."""
        self.node_metrics[node.name] = NodeMetrics(
            name=node.name,
            healthy=node.healthy,
        )
    
    def record_request_generated(self, count: int = 1) -> None:
        """Record generated requests."""
        self.system_metrics.total_requests_generated += count
        self._current_interval_requests += count
    
    def record_request_assigned(self, node: Node, queued: bool = False) -> None:
        """Record a request admitted to a node, optionally after queueing."""
        self.system_metrics.total_requests_assigned += 1
        self._current_interval_assigned += 1
        if queued:
            self.system_metrics.total_requests_queued += 1
            self._current_interval_queued += 1
        if node.name in self.node_metrics:
            self.node_metrics[node.name].requests_assigned += 1
            if queued:
                self.node_metrics[node.name].requests_queued += 1
            self.node_metrics[node.name].current_load = node.load
            self.node_metrics[node.name].max_load = max(
                self.node_metrics[node.name].max_load, node.load
            )
            self.node_metrics[node.name].healthy = node.healthy

    @staticmethod
    def _validate_rejection_reason(reason: str) -> str:
        if reason not in {"overload", "no_capacity"}:
            raise ValueError("rejection reason must be 'overload' or 'no_capacity'")
        return reason
    
    def record_request_rejected(self, reason: str = "no_capacity") -> None:
        """Record a rejected request, separated by overload or no capacity."""
        reason = self._validate_rejection_reason(reason)
        self.system_metrics.total_requests_rejected += 1
        self._current_interval_rejected += 1
        if reason == "overload":
            self.system_metrics.total_requests_rejected_overload += 1
            self._current_interval_rejected_overload += 1
        else:
            self.system_metrics.total_requests_rejected_no_capacity += 1
            self._current_interval_rejected_no_capacity += 1
    
    def record_request_completed(self, node_name: str, latency: float) -> None:
        """Record a completed request with latency."""
        self.system_metrics.total_requests_completed += 1
        self._current_interval_completed += 1
        if node_name in self.node_metrics:
            self.node_metrics[node_name].requests_completed += 1
            self.node_metrics[node_name].total_latency += latency
    
    def record_request_failed(self, node_name: str, reason: str = "failed") -> None:
        """Record a failed request; timeouts are tracked separately."""
        if reason not in {"failed", "timeout"}:
            raise ValueError("failure reason must be 'failed' or 'timeout'")
        self.system_metrics.total_requests_failed += 1
        self._current_interval_failed += 1
        if reason == "timeout":
            self.system_metrics.total_requests_timed_out += 1
            self._current_interval_timed_out += 1
        if node_name in self.node_metrics:
            self.node_metrics[node_name].requests_failed += 1
            if reason == "timeout":
                self.node_metrics[node_name].requests_timed_out += 1
    
    def record_surge(self) -> None:
        """Record a surge detection event."""
        self.system_metrics.surge_events += 1
    
    def sync_nodes(self, nodes: List[Node]) -> None:
        """
        Refresh health and load snapshots for every node.
        
        Called each interval so unhealthy nodes (which receive no requests)
        are still reported accurately.
        """
        for node in nodes:
            metrics = self.node_metrics.get(node.name)
            if metrics is None:
                continue
            metrics.healthy = node.healthy
            metrics.current_load = node.load
            metrics.max_load = max(metrics.max_load, node.load)
    
    def end_interval(self, interval: int, surge_detected: bool) -> dict:
        """
        Finalize metrics for the current interval.
        
        Returns:
            Dictionary with interval summary
        """
        interval_summary = {
            "interval": interval,
            "requests_generated": self._current_interval_requests,
            "requests_assigned": self._current_interval_assigned,
            "requests_completed": self._current_interval_completed,
            "requests_failed": self._current_interval_failed,
            "requests_timed_out": self._current_interval_timed_out,
            "requests_queued": self._current_interval_queued,
            "requests_rejected": self._current_interval_rejected,
            "requests_rejected_overload": self._current_interval_rejected_overload,
            "requests_rejected_no_capacity": self._current_interval_rejected_no_capacity,
            "surge_detected": surge_detected,
        }
        
        self._interval_history.append(interval_summary)
        self.system_metrics.intervals_elapsed += 1
        
        # Reset interval counters
        self._current_interval_requests = 0
        self._current_interval_assigned = 0
        self._current_interval_rejected = 0
        self._current_interval_queued = 0
        self._current_interval_completed = 0
        self._current_interval_failed = 0
        self._current_interval_timed_out = 0
        self._current_interval_rejected_overload = 0
        self._current_interval_rejected_no_capacity = 0
        
        return interval_summary
    
    def get_node_metrics(self, node_name: str) -> Optional[NodeMetrics]:
        """Get metrics for a specific node."""
        return self.node_metrics.get(node_name)
    
    def get_all_node_metrics(self) -> List[NodeMetrics]:
        """Get metrics for all nodes."""
        return list(self.node_metrics.values())
    
    def get_system_metrics(self) -> SystemMetrics:
        """Get system-wide metrics."""
        return self.system_metrics
    
    def get_interval_history(self) -> List[dict]:
        """Get history of interval summaries."""
        return list(self._interval_history)
    
    def reset(self) -> None:
        """Reset all metrics."""
        self.node_metrics.clear()
        self.system_metrics = SystemMetrics()
        self._interval_history.clear()
        self._current_interval_requests = 0
        self._current_interval_assigned = 0
        self._current_interval_rejected = 0
        self._current_interval_queued = 0
        self._current_interval_completed = 0
        self._current_interval_failed = 0
        self._current_interval_timed_out = 0
        self._current_interval_rejected_overload = 0
        self._current_interval_rejected_no_capacity = 0