"""
Scheduling policies for request distribution in CWMS.

Documented policies: round-robin and least-loaded.
Extension policies (requested by the build brief, not in the source docs):
first-come-first-served (FCFS) and a forecast-aware adaptive policy.
"""
from abc import ABC, abstractmethod
from typing import Callable, Optional, List
from .nodes import Node


class SchedulingPolicy(ABC):
    """Abstract base class for scheduling policies."""
    
    @abstractmethod
    def select_node(self, nodes: List[Node]) -> Optional[Node]:
        """
        Select a node for request assignment.
        
        Args:
            nodes: List of available nodes
            
        Returns:
            Selected node or None if no healthy node available
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return policy name."""
        pass
    
    def _get_healthy_nodes(self, nodes: List[Node]) -> List[Node]:
        """Filter healthy nodes from the list."""
        return [n for n in nodes if n.healthy]


class RoundRobinPolicy(SchedulingPolicy):
    """
    Round Robin scheduling policy.
    Distributes requests sequentially across healthy nodes.
    """
    
    def __init__(self):
        self._index = 0
    
    @property
    def name(self) -> str:
        return "round-robin"
    
    def select_node(self, nodes: List[Node]) -> Optional[Node]:
        healthy = self._get_healthy_nodes(nodes)
        if not healthy:
            return None
        
        # Find next healthy node in round-robin order
        for _ in range(len(nodes)):
            candidate = nodes[self._index % len(nodes)]
            self._index += 1
            if candidate.healthy:
                return candidate
        return None
    
    def reset(self) -> None:
        """Reset the round-robin index."""
        self._index = 0


class LeastLoadedPolicy(SchedulingPolicy):
    """
    Least Loaded scheduling policy.
    Selects the healthy node with the lowest current load.
    """
    
    @property
    def name(self) -> str:
        return "least-loaded"
    
    def select_node(self, nodes: List[Node]) -> Optional[Node]:
        healthy = self._get_healthy_nodes(nodes)
        if not healthy:
            return None
        # Break equal-load ties by total assignments so a saturated cluster
        # does not send every extra request to the first node forever.
        return min(healthy, key=lambda n: (n.load, n.assigned))


class FCFSPolicy(SchedulingPolicy):
    """
    First-Come-First-Served baseline (extension policy).

    Requests are served by the first healthy backend in configuration order,
    so later backends only receive work when earlier ones become unhealthy.
    """
    
    @property
    def name(self) -> str:
        return "fcfs"
    
    def select_node(self, nodes: List[Node]) -> Optional[Node]:
        healthy = self._get_healthy_nodes(nodes)
        return healthy[0] if healthy else None


class AdaptivePolicy(SchedulingPolicy):
    """
    Forecast-aware adaptive policy (extension policy).

    Uses the least-loaded choice while projected demand fits within the
    cluster's remaining headroom. When the forecast indicates an overload
    risk, it switches to the healthy node with the most available capacity.
    The rule is intentionally simple and explainable.
    """
    
    def __init__(self, forecast_provider: Optional[Callable[[], float]] = None):
        self.forecast_provider = forecast_provider
        self.last_mode = "least-loaded"
    
    @property
    def name(self) -> str:
        return "adaptive"
    
    def select_node(self, nodes: List[Node]) -> Optional[Node]:
        healthy = self._get_healthy_nodes(nodes)
        if not healthy:
            return None
        
        predicted = 0.0
        if self.forecast_provider is not None:
            try:
                predicted = max(0.0, float(self.forecast_provider()))
            except Exception:  # noqa: BLE001 - never let a forecast failure break routing
                predicted = 0.0
        
        # Approximate number of requests the cluster can still absorb.
        headroom = 0.0
        for node in healthy:
            per_request = node.load_per_request * (100.0 / max(1.0, node.capacity))
            remaining = max(0.0, node.max_load_cap - node.load)
            headroom += remaining / per_request if per_request > 0 else 0.0
        
        if predicted > headroom:
            self.last_mode = "capacity-first"
            return max(healthy, key=lambda n: (n.available_capacity, -n.assigned))
        
        self.last_mode = "least-loaded"
        return min(healthy, key=lambda n: (n.load, n.assigned))


class PolicyFactory:
    """Factory for creating scheduling policies by name."""
    
    _policies = {
        "round-robin": RoundRobinPolicy,
        "least-loaded": LeastLoadedPolicy,
        "fcfs": FCFSPolicy,
        "adaptive": AdaptivePolicy,
    }
    
    @classmethod
    def create(cls, policy_name: str) -> SchedulingPolicy:
        """
        Create a policy instance by name.
        
        Args:
            policy_name: Name of the policy (round-robin, least-loaded, fcfs, adaptive)
            
        Returns:
            Policy instance
            
        Raises:
            ValueError: If policy name is unknown
        """
        if policy_name not in cls._policies:
            raise ValueError(f"Unknown policy: {policy_name}. Available: {list(cls._policies.keys())}")
        return cls._policies[policy_name]()
    
    @classmethod
    def available_policies(cls) -> List[str]:
        """Return list of available policy names."""
        return list(cls._policies.keys())
    
    @classmethod
    def register(cls, name: str, policy_class: type) -> None:
        """Register a custom policy."""
        if not issubclass(policy_class, SchedulingPolicy):
            raise TypeError("Policy class must inherit from SchedulingPolicy")
        cls._policies[name] = policy_class