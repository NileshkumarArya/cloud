#!/usr/bin/env python3
"""
CWMS Simulator Command Line Interface.
Entry point for running simulations from command line.
"""
import argparse
import sys
from pathlib import Path

from .simulator import CWMSimulator, SimulationConfig


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="CWMS Local Workload Simulator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    parser.add_argument(
        "--policy",
        choices=["round-robin", "least-loaded", "fcfs", "adaptive"],
        default="least-loaded",
        help="Scheduling policy to use",
    )
    parser.add_argument(
        "--intervals",
        type=int,
        default=20,
        help="Number of simulation intervals",
    )
    parser.add_argument(
        "--base-rate",
        type=int,
        default=40,
        help="Normal request rate per interval",
    )
    parser.add_argument(
        "--burst-rate",
        type=int,
        default=140,
        help="Burst request rate per interval",
    )
    parser.add_argument(
        "--burst-start",
        type=int,
        default=8,
        help="Interval when burst starts (inclusive)",
    )
    parser.add_argument(
        "--burst-end",
        type=int,
        default=13,
        help="Interval when burst ends (exclusive)",
    )
    parser.add_argument(
        "--surge-threshold",
        type=int,
        default=90,
        help="Request rate threshold for surge detection",
    )
    parser.add_argument(
        "--load-threshold",
        type=float,
        default=80.0,
        help="Average node load percentage threshold for surge detection",
    )
    parser.add_argument(
        "--max-load-threshold",
        type=float,
        default=100.0,
        help="Single-node load percentage threshold for surge detection",
    )
    parser.add_argument(
        "--fail-node",
        choices=["backend-a", "backend-b", "backend-c"],
        default=None,
        help="Node to mark as unhealthy",
    )
    parser.add_argument(
        "--forecast-window",
        type=int,
        default=5,
        help="Moving average window for forecasting",
    )
    parser.add_argument(
        "--forecast-strategy",
        choices=["moving_average", "change_aware"],
        default="change_aware",
        help="Forecast strategy",
    )
    parser.add_argument(
        "--disable-admission-control",
        action="store_true",
        help="Allow unlimited immediate assignment instead of bounded queues",
    )
    parser.add_argument(
        "--overload-threshold",
        type=float,
        default=100.0,
        help="Node load percentage at which requests start queueing",
    )
    parser.add_argument(
        "--queue-limit",
        type=int,
        default=50,
        help="Maximum queued requests per node per interval",
    )
    parser.add_argument(
        "--request-timeout-ms",
        type=float,
        default=2000.0,
        help="Simulated request latency timeout in milliseconds",
    )
    parser.add_argument(
        "--output",
        default="results/cwms_events.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Optional JSON output path for summary",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress interval output",
    )
    
    return parser


def main(args: argparse.Namespace) -> int:
    """Main entry point."""
    try:
        config = SimulationConfig(
            policy=args.policy,
            intervals=args.intervals,
            base_rate=args.base_rate,
            burst_rate=args.burst_rate,
            burst_start=args.burst_start,
            burst_end=args.burst_end,
            surge_threshold=args.surge_threshold,
            load_threshold=args.load_threshold,
            max_load_threshold=args.max_load_threshold,
            fail_node=args.fail_node,
            forecast_window=args.forecast_window,
            forecast_strategy=args.forecast_strategy,
            admission_control=not args.disable_admission_control,
            overload_threshold=args.overload_threshold,
            queue_limit=args.queue_limit,
            request_timeout_ms=args.request_timeout_ms,
            output_path=args.output,
            seed=args.seed,
        )
    except ValueError as exc:
        print(f"error: {exc}")
        return 2
    
    simulator = CWMSimulator(config)
    result = simulator.run(verbose=not args.quiet)
    simulator.export_csv(result)
    
    if args.json_output:
        simulator.export_json(result, args.json_output)
        print(f"JSON summary written to: {Path(args.json_output).resolve()}")
    
    return 0


if __name__ == "__main__":
    parser = create_parser()
    args = parser.parse_args()
    sys.exit(main(args))