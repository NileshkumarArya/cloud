"""
Main CWMS Simulator.
Orchestrates traffic generation, scheduling, metrics, surge detection, forecasting, and recommendations.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path
import csv
import json

from .nodes import Node, NodeState, create_default_nodes
from .policies import SchedulingPolicy, PolicyFactory, AdaptivePolicy
from .traffic_generator import TrafficGenerator, TrafficConfig
from .metrics import MetricsCollector, NodeMetrics, SystemMetrics
from .surge_detector import SurgeDetector, SurgeEvent
from .forecaster import WorkloadForecaster, ForecastResult
from .recommendations import RecommendationEngine, Recommendation


@dataclass
class SimulationConfig:
    """Configuration for a simulation run."""
    policy: str = "least-loaded"
    intervals: int = 20
    base_rate: int = 40
    burst_rate: int = 140
    burst_start: int = 8
    burst_end: int = 13
    surge_threshold: int = 90
    load_threshold: float = 80.0
    max_load_threshold: float = 100.0
    fail_node: Optional[str] = None
    forecast_window: int = 5
    forecast_strategy: str = "change_aware"
    admission_control: bool = True
    overload_threshold: float = 100.0
    queue_limit: int = 50
    request_timeout_ms: float = 2000.0
    seed: int = 7
    output_path: str = "results/cwms_events.csv"
    
    def __post_init__(self) -> None:
        """Validate configuration so CLI and API share the same rules."""
        if self.policy not in PolicyFactory.available_policies():
            raise ValueError(
                f"Unknown policy: {self.policy}. "
                f"Available: {PolicyFactory.available_policies()}"
            )
        if self.fail_node is not None and self.fail_node not in {
            "backend-a", "backend-b", "backend-c"
        }:
            raise ValueError(f"Unknown fail_node: {self.fail_node}")
        if self.intervals < 1:
            raise ValueError("intervals must be at least 1")
        if self.base_rate < 0 or self.burst_rate < 0:
            raise ValueError("request rates cannot be negative")
        if self.burst_start < 0 or self.burst_end < 0:
            raise ValueError("burst bounds cannot be negative")
        if self.burst_start > self.burst_end:
            raise ValueError("burst_start cannot be after burst_end")
        if self.burst_end > self.intervals:
            raise ValueError("burst_end cannot exceed intervals")
        if self.surge_threshold < 1:
            raise ValueError("surge_threshold must be at least 1")
        if self.load_threshold < 0:
            raise ValueError("load_threshold cannot be negative")
        if self.max_load_threshold < 0:
            raise ValueError("max_load_threshold cannot be negative")
        if self.forecast_window < 1:
            raise ValueError("forecast_window must be at least 1")
        if self.forecast_strategy not in WorkloadForecaster.STRATEGIES:
            raise ValueError(
                f"Unknown forecast_strategy: {self.forecast_strategy}. "
                f"Available: {WorkloadForecaster.STRATEGIES}"
            )
        if not 0 <= self.overload_threshold <= 150.0:
            raise ValueError("overload_threshold must be between 0 and 150")
        if self.queue_limit < 0:
            raise ValueError("queue_limit cannot be negative")
        if self.request_timeout_ms <= 0:
            raise ValueError("request_timeout_ms must be positive")
        if self.seed < 0:
            raise ValueError("seed cannot be negative")
    
    def to_traffic_config(self) -> TrafficConfig:
        """Convert to TrafficConfig."""
        return TrafficConfig(
            base_rate=self.base_rate,
            burst_rate=self.burst_rate,
            burst_start=self.burst_start,
            burst_end=self.burst_end,
            intervals=self.intervals,
            seed=self.seed,
        )


@dataclass
class IntervalResult:
    """Results for a single simulation interval."""
    interval: int
    requests_generated: int
    requests_assigned: int
    requests_rejected: int
    requests_completed: int
    requests_failed: int
    requests_timed_out: int
    requests_queued: int
    requests_rejected_overload: int
    requests_rejected_no_capacity: int
    node_metrics: List[Dict[str, Any]]
    surge_detected: bool
    surge_event: Optional[Dict[str, Any]]
    forecast: Dict[str, Any]
    recommendation: Dict[str, Any]
    max_load: float


@dataclass
class SimulationResult:
    """Complete simulation results."""
    config: SimulationConfig
    intervals: List[IntervalResult]
    final_system_metrics: SystemMetrics
    final_node_metrics: List[NodeMetrics]
    surge_events: List[SurgeEvent]
    forecasts: List[ForecastResult]
    recommendations: List[Recommendation]
    forecast_mae: Optional[float]
    forecast_rmse: Optional[float]
    forecast_naive_mae: Optional[float] = None
    forecast_naive_rmse: Optional[float] = None
    forecast_ma_mae: Optional[float] = None
    forecast_ma_rmse: Optional[float] = None
    
    def to_csv_rows(self) -> List[dict]:
        """Convert results to CSV rows (one per node per interval)."""
        rows = []
        for interval_result in self.intervals:
            for node_metric in interval_result.node_metrics:
                row = {
                    "interval": interval_result.interval,
                    "policy": self.config.policy,
                    "requests_generated": interval_result.requests_generated,
                    "requests_assigned_this_interval": interval_result.requests_assigned,
                    "requests_rejected_this_interval": interval_result.requests_rejected,
                    "requests_completed_this_interval": interval_result.requests_completed,
                    "requests_failed_this_interval": interval_result.requests_failed,
                    "requests_timed_out_this_interval": interval_result.requests_timed_out,
                    "requests_queued_this_interval": interval_result.requests_queued,
                    "requests_rejected_overload_this_interval": interval_result.requests_rejected_overload,
                    "requests_rejected_no_capacity_this_interval": interval_result.requests_rejected_no_capacity,
                    "node": node_metric["name"],
                    "healthy": node_metric["healthy"],
                    "simulated_load_percent": node_metric["load"],
                    "node_assigned_total": node_metric["assigned_total"],
                    "node_queued_total": node_metric["queued_total"],
                    "node_queue_overflow_total": node_metric["queue_overflow_total"],
                    "surge_detected": interval_result.surge_detected,
                    "forecast_predicted": interval_result.forecast["predicted"],
                    "forecast_method": interval_result.forecast.get("method"),
                    "moving_average_forecast": interval_result.forecast.get("ma_predicted"),
                    "naive_forecast": interval_result.forecast.get("naive_predicted"),
                    "recommendation": interval_result.recommendation["message"],
                    "surge_type": interval_result.surge_event["surge_type"] if interval_result.surge_event else None,
                    "forecast_actual": interval_result.forecast.get("actual"),
                    "forecast_error": interval_result.forecast.get("error"),
                }
                rows.append(row)
        return rows
    
    def to_summary_dict(self) -> dict:
        """Convert to summary dictionary."""
        return {
            "config": {
                "policy": self.config.policy,
                "intervals": self.config.intervals,
                "base_rate": self.config.base_rate,
                "burst_rate": self.config.burst_rate,
                "burst_start": self.config.burst_start,
                "burst_end": self.config.burst_end,
                "surge_threshold": self.config.surge_threshold,
                "load_threshold": self.config.load_threshold,
                "max_load_threshold": self.config.max_load_threshold,
                "fail_node": self.config.fail_node,
                "forecast_window": self.config.forecast_window,
                "forecast_strategy": self.config.forecast_strategy,
                "admission_control": self.config.admission_control,
                "overload_threshold": self.config.overload_threshold,
                "queue_limit": self.config.queue_limit,
                "request_timeout_ms": self.config.request_timeout_ms,
                "seed": self.config.seed,
            },
            "system_metrics": self.final_system_metrics.to_dict(),
            "node_metrics": [m.to_dict() for m in self.final_node_metrics],
            "surge_events": [e.to_dict() for e in self.surge_events],
            "forecast_accuracy": {
                "strategy": self.config.forecast_strategy,
                "mae": self.forecast_mae,
                "rmse": self.forecast_rmse,
                "moving_average_mae": self.forecast_ma_mae,
                "moving_average_rmse": self.forecast_ma_rmse,
                "naive_mae": self.forecast_naive_mae,
                "naive_rmse": self.forecast_naive_rmse,
            },
            "final_recommendation": self.recommendations[-1].to_dict() if self.recommendations else None,
        }


class CWMSimulator:
    """
    Main CWMS Simulator.
    
    Runs complete workload management simulation with:
    - Traffic generation
    - Request scheduling (round-robin or least-loaded)
    - Node health management
    - Metrics collection
    - Surge detection
    - Workload forecasting
    - Recommendation generation
    - CSV export
    """
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.nodes: List[Node] = []
        self.policy: SchedulingPolicy
        self.traffic_generator: TrafficGenerator
        self.metrics: MetricsCollector
        self.surge_detector: SurgeDetector
        self.forecaster: WorkloadForecaster
        self.recommendation_engine: RecommendationEngine
        self._rr_index = 0
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize simulator components."""
        # Create nodes
        self.nodes = create_default_nodes(
            overload_threshold=self.config.overload_threshold,
            queue_limit=self.config.queue_limit,
        )
        
        # Apply node failure if configured
        if self.config.fail_node:
            for node in self.nodes:
                if node.name == self.config.fail_node:
                    node.set_health(NodeState.UNHEALTHY)
        
        # Create policy
        self.policy = PolicyFactory.create(self.config.policy)
        
        # Create traffic generator
        self.traffic_generator = TrafficGenerator(self.config.to_traffic_config())
        
        # Create metrics collector
        self.metrics = MetricsCollector()
        for node in self.nodes:
            self.metrics.register_node(node)
        
        # Create surge detector
        self.surge_detector = SurgeDetector(
            rate_threshold=self.config.surge_threshold,
            load_threshold=self.config.load_threshold,
            max_load_threshold=self.config.max_load_threshold,
        )
        
        # Create forecaster
        self.forecaster = WorkloadForecaster(
            window_size=self.config.forecast_window,
            strategy=self.config.forecast_strategy,
        )
        
        # Adaptive policy consumes the causal forecast from past observations.
        if isinstance(self.policy, AdaptivePolicy):
            self.policy.forecast_provider = self.forecaster.peek
        
        # Create recommendation engine
        self.recommendation_engine = RecommendationEngine(
            high_load_threshold=self.config.load_threshold,
        )
        
        self._rr_index = 0
        self._initialized = True
    
    def run(self, progress_callback=None, verbose: bool = True) -> SimulationResult:
        """
        Run the complete simulation.
        
        Args:
            progress_callback: Optional callable(interval, total_intervals)
            verbose: Print per-interval progress and a final summary
        
        Returns:
            SimulationResult with all metrics and events
        """
        if not self._initialized:
            self.initialize()
        
        intervals_results = []
        all_surge_events = []
        all_forecasts = []
        all_recommendations = []
        
        for interval in range(self.config.intervals):
            # Generate traffic
            requests = self.traffic_generator.generate_requests(interval)
            self.metrics.record_request_generated(requests)
            
            # Decay node loads
            for node in self.nodes:
                node.decay_load()
            
            # Assign requests through bounded admission control.
            interval_assigned = 0
            interval_rejected = 0
            interval_queued = 0
            interval_completed = 0
            interval_failed = 0
            interval_timed_out = 0
            interval_overflow = 0
            interval_no_capacity = 0

            for _ in range(requests):
                node = self.policy.select_node(self.nodes)
                if node is None:
                    interval_rejected += 1
                    interval_no_capacity += 1
                    self.metrics.record_request_rejected("no_capacity")
                    continue

                if self.config.admission_control:
                    outcome = node.admit_request()
                else:
                    outcome = "accepted" if node.assign_request() else "unhealthy"

                if outcome in {"accepted", "queued"}:
                    interval_assigned += 1
                    queued = outcome == "queued"
                    if queued:
                        interval_queued += 1
                    self.metrics.record_request_assigned(node, queued=queued)
                    if not queued:
                        completed, timed_out = self._finish_request(node)
                        if completed:
                            interval_completed += 1
                        else:
                            interval_failed += 1
                            if timed_out:
                                interval_timed_out += 1
                elif outcome == "overflow":
                    interval_rejected += 1
                    interval_overflow += 1
                    self.metrics.record_request_rejected("overload")
                else:
                    interval_rejected += 1
                    interval_no_capacity += 1
                    self.metrics.record_request_rejected("no_capacity")

            # Drain queued requests at the end of each interval. Waiting time is
            # approximated from node capacity; requests over the timeout fail.
            for node in self.nodes:
                service_ms = 1000.0 / max(1.0, node.capacity)
                for position in range(node.queue_depth):
                    latency = service_ms * (position + 1) + self._simulated_latency(node)
                    if latency > self.config.request_timeout_ms:
                        self.metrics.record_request_failed(node.name, reason="timeout")
                        interval_failed += 1
                        interval_timed_out += 1
                    else:
                        self.metrics.record_request_completed(node.name, latency)
                        interval_completed += 1
                node.reset_queue()
            
            # Check surge
            node_loads = [n.load for n in self.nodes]
            surge_event = self.surge_detector.check_surge(interval, requests, node_loads)
            surge_detected = surge_event is not None
            
            if surge_detected:
                self.metrics.record_surge()
                all_surge_events.append(surge_event)
            
            # Forecast next interval using only prior observations, then record actual.
            forecast = self.forecaster.forecast(interval)
            had_history = forecast.window_size > 0
            self.forecaster.observe(requests)
            if had_history:
                forecast.actual = requests
            all_forecasts.append(forecast)
            
            # Generate recommendation
            recommendations = self.recommendation_engine.evaluate(
                self.nodes,
                self.metrics.get_system_metrics(),
                surge_event,
            )
            all_recommendations.extend(recommendations)
            
            # Collect node metrics for this interval
            self.metrics.sync_nodes(self.nodes)
            node_metrics = []
            for node in self.nodes:
                node_metrics.append({
                    "name": node.name,
                    "healthy": node.healthy,
                    "load": round(node.load, 2),
                    "assigned_total": node.assigned,
                    "queued_total": node.queued_total,
                    "queue_overflow_total": node.overflow_total,
                    "max_queue_depth": node.max_queue_depth,
                    "capacity": node.capacity,
                })
            
            # Record interval results
            interval_result = IntervalResult(
                interval=interval,
                requests_generated=requests,
                requests_assigned=interval_assigned,
                requests_rejected=interval_rejected,
                requests_completed=interval_completed,
                requests_failed=interval_failed,
                requests_timed_out=interval_timed_out,
                requests_queued=interval_queued,
                requests_rejected_overload=interval_overflow,
                requests_rejected_no_capacity=interval_no_capacity,
                node_metrics=node_metrics,
                surge_detected=surge_detected,
                surge_event=surge_event.to_dict() if surge_event else None,
                forecast=forecast.to_dict(),
                recommendation=recommendations[-1].to_dict() if recommendations else {},
                max_load=max(n.load for n in self.nodes) if self.nodes else 0.0,
            )
            intervals_results.append(interval_result)
            
            # End interval in metrics
            self.metrics.end_interval(interval, surge_detected)
            
            # Notify progress listeners
            if progress_callback is not None:
                progress_callback(interval + 1, self.config.intervals)
            
            # Print progress
            if verbose:
                print(f"interval={interval:02d} requests={requests:4d} accepted={interval_assigned:4d} "
                      f"queued={interval_queued:3d} completed={interval_completed:4d} "
                      f"failed={interval_failed:3d} rejected={interval_rejected:3d} "
                      f"max_load={interval_result.max_load:5.1f}% surge={surge_detected}")
                print(f"  forecast~{forecast.predicted:.1f} requests/interval | {recommendations[-1].message if recommendations else 'N/A'}")
        
        # Evaluate forecast accuracy
        forecast_mae, forecast_rmse = self.forecaster.evaluate()
        ma_mae, ma_rmse = self.forecaster.evaluate_moving_average()
        naive_mae, naive_rmse = self.forecaster.evaluate_naive()
        
        # Create final result
        result = SimulationResult(
            config=self.config,
            intervals=intervals_results,
            final_system_metrics=self.metrics.get_system_metrics(),
            final_node_metrics=self.metrics.get_all_node_metrics(),
            surge_events=all_surge_events,
            forecasts=all_forecasts,
            recommendations=all_recommendations,
            forecast_mae=forecast_mae,
            forecast_rmse=forecast_rmse,
            forecast_naive_mae=naive_mae,
            forecast_naive_rmse=naive_rmse,
            forecast_ma_mae=ma_mae,
            forecast_ma_rmse=ma_rmse,
        )
        
        # Print summary
        if verbose:
            self._print_summary(result)
        
        return result
    
    def _finish_request(self, node: Node) -> tuple[bool, bool]:
        """
        Complete an immediately admitted request or mark it timed out.

        Returns:
            (completed, timed_out)
        """
        latency = self._simulated_latency(node)
        if latency > self.config.request_timeout_ms:
            self.metrics.record_request_failed(node.name, reason="timeout")
            return False, True
        self.metrics.record_request_completed(node.name, latency)
        return True, False

    @staticmethod
    def _simulated_latency(node: Node) -> float:
        """Simulated response time in ms; grows with load and shrinks with capacity."""
        base = 20.0
        capacity_factor = 100.0 / max(1.0, node.capacity)
        return base * capacity_factor * (1.0 + node.load / 100.0)

    def _print_summary(self, result: SimulationResult) -> None:
        """Print simulation summary."""
        print("\n--- Summary ---")
        print(f"Policy: {self.config.policy}")
        sys_metrics = result.final_system_metrics
        print(f"Generated/accepted/rejected: {sys_metrics.total_requests_generated}/"
              f"{sys_metrics.total_requests_assigned}/{sys_metrics.total_requests_rejected}")
        print(f"Completed/failed/timed-out/queued: {sys_metrics.total_requests_completed}/"
              f"{sys_metrics.total_requests_failed}/{sys_metrics.total_requests_timed_out}/"
              f"{sys_metrics.total_requests_queued}")
        print(f"Rejected overload/no-capacity: {sys_metrics.total_requests_rejected_overload}/"
              f"{sys_metrics.total_requests_rejected_no_capacity}")
        print("Per-node assignment totals: " + ", ".join(
            f"{n.name}={n.requests_assigned}" for n in result.final_node_metrics
        ))
        print(f"Surge events: {len(result.surge_events)}")
        if result.forecast_mae is not None:
            print(f"Forecast MAE: {result.forecast_mae:.2f}, RMSE: {result.forecast_rmse:.2f}")
        print(f"Configured CSV output path: {Path(self.config.output_path).resolve()}")
        print("Note: all node load and request metrics are simulated, not real cloud telemetry.")
    
    def export_csv(self, result: SimulationResult, path: Optional[str] = None) -> Path:
        """
        Export simulation results to CSV.
        
        Args:
            result: Simulation results
            path: Optional output path (uses config default if not provided)
            
        Returns:
            Path to written CSV file
        """
        output_path = Path(path or self.config.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        rows = result.to_csv_rows()
        if not rows:
            return output_path
        
        fieldnames = list(rows[0].keys())
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        return output_path
    
    def export_json(self, result: SimulationResult, path: str) -> Path:
        """Export simulation results to JSON."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(result.to_summary_dict(), f, indent=2)
        
        return output_path


def run_simulation(
    policy: str = "least-loaded",
    intervals: int = 20,
    base_rate: int = 40,
    burst_rate: int = 140,
    burst_start: int = 8,
    burst_end: int = 13,
    surge_threshold: int = 90,
    fail_node: Optional[str] = None,
    output: str = "results/cwms_events.csv",
    seed: int = 7,
    load_threshold: float = 80.0,
    max_load_threshold: float = 100.0,
    forecast_strategy: str = "change_aware",
    admission_control: bool = True,
    overload_threshold: float = 100.0,
    queue_limit: int = 50,
    request_timeout_ms: float = 2000.0,
) -> SimulationResult:
    """
    Convenience function to run a simulation.
    
    Args:
        policy: Scheduling policy ("round-robin", "least-loaded", "fcfs", or "adaptive")
        intervals: Number of simulation intervals
        base_rate: Normal request rate per interval
        burst_rate: Burst request rate per interval
        burst_start: Interval when burst starts
        burst_end: Interval when burst ends
        surge_threshold: Request rate threshold for surge detection
        fail_node: Node to mark as unhealthy
        output: Output CSV path
        seed: Random seed
        load_threshold: Average node load threshold for surge detection
        max_load_threshold: Maximum single-node load threshold for surge detection
        forecast_strategy: "moving_average" or "change_aware"
        admission_control: Enable bounded per-node admission queues
        overload_threshold: Load percentage at which requests start queueing
        queue_limit: Maximum queued requests per node per interval
        request_timeout_ms: Maximum simulated request latency before timeout
        
    Returns:
        SimulationResult
    """
    config = SimulationConfig(
        policy=policy,
        intervals=intervals,
        base_rate=base_rate,
        burst_rate=burst_rate,
        burst_start=burst_start,
        burst_end=burst_end,
        surge_threshold=surge_threshold,
        load_threshold=load_threshold,
        max_load_threshold=max_load_threshold,
        forecast_strategy=forecast_strategy,
        admission_control=admission_control,
        overload_threshold=overload_threshold,
        queue_limit=queue_limit,
        request_timeout_ms=request_timeout_ms,
        fail_node=fail_node,
        output_path=output,
        seed=seed,
    )
    
    simulator = CWMSimulator(config)
    result = simulator.run()
    simulator.export_csv(result)
    
    return result