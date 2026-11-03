"""
Backend node simulation for CWMS.
Represents simulated server nodes with capacity, load, and health state.
"""
from dataclasses import dataclass, field
from enum import Enum
import random


class NodeState(Enum):
    """Health state of a backend node."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


@dataclass
class Node:
    """
    Simulated backend node.
    
    Attributes:
        name: Unique identifier for the node
        capacity: Maximum request capacity (requests per interval)
        load: Current simulated load percentage (0-150%)
        state: Health state of the node
        assigned: Total requests accepted by this node
        max_load_cap: Maximum load percentage (default 150%)
        load_decay: Load decay factor per interval (default 0.55)
        load_per_request: Load increase per assigned request (default 3.0)
        overload_threshold: Load percentage at which new requests wait in queue
        queue_limit: Maximum waiting requests per interval
        queue_depth: Current waiting requests in this interval
        queued_total: Total requests that waited in the queue
        overflow_total: Total requests rejected because the queue was full
    """
    name: str
    capacity: float
    load: float = 0.0
    state: NodeState = NodeState.HEALTHY
    assigned: int = 0
    max_load_cap: float = 150.0
    load_decay: float = 0.55
    load_per_request: float = 3.0
    overload_threshold: float = 100.0
    queue_limit: int = 50
    queue_depth: int = 0
    queued_total: int = 0
    overflow_total: int = 0
    max_queue_depth: int = 0
    _rng: random.Random = field(default_factory=random.Random, repr=False)
    
    def __post_init__(self):
        if self.capacity <= 0:
            raise ValueError("Node capacity must be positive")
        if not 0 <= self.load <= self.max_load_cap:
            raise ValueError(f"Initial load must be between 0 and {self.max_load_cap}")
        if not 0 <= self.overload_threshold <= self.max_load_cap:
            raise ValueError(
                f"overload_threshold must be between 0 and {self.max_load_cap}"
            )
        if self.queue_limit < 0:
            raise ValueError("queue_limit cannot be negative")
    
    @property
    def healthy(self) -> bool:
        """Return True if node can accept new requests."""
        return self.state == NodeState.HEALTHY
    
    @property
    def available_capacity(self) -> float:
        """Return available capacity based on current load."""
        return max(0, self.capacity * (1 - self.load / 100))
    
    def _record_assignment(self) -> None:
        """Update assignment and load counters for an accepted request."""
        self.assigned += 1
        self.load = min(
            self.max_load_cap,
            self.load + self.load_per_request * (100.0 / max(1, self.capacity)),
        )

    def assign_request(self) -> bool:
        """
        Assign a request to this node without admission control.
        
        Returns:
            True if request was assigned, False if node is unhealthy
        """
        if not self.healthy:
            return False
        self._record_assignment()
        return True

    def admit_request(self) -> str:
        """
        Apply bounded admission control to a new request.

        Requests are accepted immediately below ``overload_threshold``. At or
        above the threshold they wait in a per-interval queue until
        ``queue_limit`` is reached; further requests overflow and are rejected.

        Returns:
            "accepted", "queued", "overflow", or "unhealthy"
        """
        if not self.healthy:
            return "unhealthy"
        if self.load >= self.overload_threshold:
            if self.queue_depth >= self.queue_limit:
                self.overflow_total += 1
                return "overflow"
            self.queue_depth += 1
            self.queued_total += 1
            self.max_queue_depth = max(self.max_queue_depth, self.queue_depth)
            self._record_assignment()
            return "queued"
        self._record_assignment()
        return "accepted"

    def reset_queue(self) -> None:
        """Clear the current interval's waiting queue after it is drained."""
        self.queue_depth = 0
    
    def decay_load(self) -> None:
        """Apply load decay between intervals."""
        self.load = max(0.0, self.load * self.load_decay)
    
    def set_health(self, state: NodeState) -> None:
        """Set the node health state."""
        self.state = state
    
    def reset(self) -> None:
        """Reset node to initial state."""
        self.load = 0.0
        self.state = NodeState.HEALTHY
        self.assigned = 0
        self.queue_depth = 0
        self.queued_total = 0
        self.overflow_total = 0
        self.max_queue_depth = 0
    
    def to_dict(self) -> dict:
        """Convert node to dictionary for serialization."""
        return {
            "name": self.name,
            "capacity": self.capacity,
            "load": round(self.load, 2),
            "state": self.state.value,
            "healthy": self.healthy,
            "assigned": self.assigned,
            "available_capacity": round(self.available_capacity, 2),
            "overload_threshold": self.overload_threshold,
            "queue_limit": self.queue_limit,
            "queued_current": self.queue_depth,
            "queued_total": self.queued_total,
            "queue_overflow_total": self.overflow_total,
            "max_queue_depth": self.max_queue_depth,
        }


def create_default_nodes(
    overload_threshold: float = 100.0,
    queue_limit: int = 50,
) -> list[Node]:
    """Create the default set of backend nodes for simulation."""
    return [
        Node("backend-a", 100, overload_threshold=overload_threshold,
             queue_limit=queue_limit),
        Node("backend-b", 100, overload_threshold=overload_threshold,
             queue_limit=queue_limit),
        Node("backend-c", 75, overload_threshold=overload_threshold,
             queue_limit=queue_limit),
    ]