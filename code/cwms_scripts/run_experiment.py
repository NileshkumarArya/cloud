#!/usr/bin/env python3
"""
Repeatable scheduling experiment for CWMS.

Runs every scenario under every policy with identical seeds/configuration and
writes raw metrics, an aggregated summary, and a Markdown table. All results
come from the local discrete-event simulation and are synthetic.
"""
from __future__ import annotations

import contextlib
import csv
import io
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cwms_simulator.simulator import CWMSimulator, SimulationConfig  # noqa: E402

POLICIES = ["fcfs", "round-robin", "least-loaded", "adaptive"]
SEEDS = [7, 13, 29, 41, 53]
INTERVALS = 20
FORECAST_STRATEGY = "change_aware"
T_CRITICAL_95 = {
    2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
    7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262,
}

SCENARIOS = {
    "normal": dict(base_rate=40, burst_rate=40, burst_start=0, burst_end=0,
                   surge_threshold=90, fail_node=None),
    "burst": dict(base_rate=40, burst_rate=180, burst_start=8, burst_end=13,
                  surge_threshold=90, fail_node=None),
    "failure": dict(base_rate=50, burst_rate=50, burst_start=0, burst_end=0,
                    surge_threshold=90, fail_node="backend-b"),
    "overload": dict(base_rate=120, burst_rate=120, burst_start=0, burst_end=0,
                     surge_threshold=90, fail_node=None,
                     overload_threshold=80.0, queue_limit=10,
                     request_timeout_ms=100.0),
}

NUMERIC_COLUMNS = [
    "requests_generated", "requests_accepted", "requests_rejected",
    "requests_rejected_overload", "requests_rejected_no_capacity",
    "requests_completed", "requests_failed", "requests_timed_out",
    "requests_queued", "acceptance_rate_pct", "completion_rate_pct",
    "queue_rate_pct", "timeout_rate_pct", "surge_events",
    "forecast_mae", "forecast_rmse", "ma_mae", "ma_rmse", "naive_mae",
    "naive_rmse", "peak_load_pct", "final_load_spread_pct",
    "mean_simulated_latency_ms",
]


def run_once(policy: str, scenario: str, params: dict, seed: int) -> dict:
    config = SimulationConfig(
        policy=policy,
        intervals=INTERVALS,
        seed=seed,
        base_rate=params["base_rate"],
        burst_rate=params["burst_rate"],
        burst_start=params["burst_start"],
        burst_end=params["burst_end"],
        surge_threshold=params["surge_threshold"],
        fail_node=params["fail_node"],
        overload_threshold=params.get("overload_threshold", 100.0),
        queue_limit=params.get("queue_limit", 50),
        request_timeout_ms=params.get("request_timeout_ms", 2000.0),
        forecast_strategy=FORECAST_STRATEGY,
        output_path=str(ROOT / "cwms_data" / f"sim_{scenario}_{policy}_seed{seed}.csv"),
    )
    simulator = CWMSimulator(config)
    with contextlib.redirect_stdout(io.StringIO()):
        result = simulator.run()
    simulator.export_csv(result)

    metrics = result.final_system_metrics
    healthy_loads = [m.current_load for m in result.final_node_metrics if m.healthy]
    completed = sum(m.requests_completed for m in result.final_node_metrics)
    total_latency = sum(m.total_latency for m in result.final_node_metrics)
    mean_latency = total_latency / completed if completed else 0.0

    return {
        "scenario": scenario,
        "policy": policy,
        "seed": seed,
        "intervals": INTERVALS,
        "forecast_strategy": FORECAST_STRATEGY,
        "requests_generated": metrics.total_requests_generated,
        "requests_accepted": metrics.total_requests_assigned,
        "requests_rejected": metrics.total_requests_rejected,
        "requests_rejected_overload": metrics.total_requests_rejected_overload,
        "requests_rejected_no_capacity": metrics.total_requests_rejected_no_capacity,
        "requests_completed": metrics.total_requests_completed,
        "requests_failed": metrics.total_requests_failed,
        "requests_timed_out": metrics.total_requests_timed_out,
        "requests_queued": metrics.total_requests_queued,
        "acceptance_rate_pct": round(metrics.assignment_rate, 2),
        "completion_rate_pct": round(metrics.completion_rate, 2),
        "queue_rate_pct": round(metrics.queue_rate, 2),
        "timeout_rate_pct": round(metrics.timeout_rate, 2),
        "surge_events": len(result.surge_events),
        "forecast_mae": round(result.forecast_mae, 2) if result.forecast_mae is not None else "",
        "forecast_rmse": round(result.forecast_rmse, 2) if result.forecast_rmse is not None else "",
        "ma_mae": round(result.forecast_ma_mae, 2) if result.forecast_ma_mae is not None else "",
        "ma_rmse": round(result.forecast_ma_rmse, 2) if result.forecast_ma_rmse is not None else "",
        "naive_mae": round(result.forecast_naive_mae, 2) if result.forecast_naive_mae is not None else "",
        "naive_rmse": round(result.forecast_naive_rmse, 2) if result.forecast_naive_rmse is not None else "",
        "peak_load_pct": round(max(i.max_load for i in result.intervals), 2),
        "final_load_spread_pct": round(max(healthy_loads) - min(healthy_loads), 2) if healthy_loads else 0.0,
        "mean_simulated_latency_ms": round(mean_latency, 2),
        "node_assignments": " ".join(
            f"{m.name}={m.requests_assigned}" for m in result.final_node_metrics
        ),
    }


def ci95(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    critical = T_CRITICAL_95.get(len(values), 1.96)
    return critical * statistics.stdev(values) / math.sqrt(len(values))


def aggregate(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["scenario"], row["policy"]), []).append(row)

    summary = []
    for (scenario, policy), group in grouped.items():
        item = {
            "scenario": scenario,
            "policy": policy,
            "seeds": len(group),
            "forecast_strategy": group[0]["forecast_strategy"],
        }
        for column in NUMERIC_COLUMNS:
            values = [float(r[column]) for r in group if r[column] != ""]
            item[column] = round(statistics.mean(values), 2) if values else ""
        latency = [float(r["mean_simulated_latency_ms"]) for r in group]
        forecast_mae = [float(r["forecast_mae"]) for r in group if r["forecast_mae"] != ""]
        item["latency_stdev_ms"] = round(statistics.pstdev(latency), 2)
        item["latency_ci95_ms"] = round(ci95(latency), 2)
        item["forecast_mae_ci95"] = round(ci95(forecast_mae), 2)
        summary.append(item)
    summary.sort(key=lambda r: (list(SCENARIOS).index(r["scenario"]),
                                POLICIES.index(r["policy"])))
    return summary


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def to_markdown(rows: list[dict], title: str, note: str) -> str:
    headers = list(rows[0].keys())
    lines = [f"# {title}", "", note, "",
             "| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    rows = []
    for scenario, params in SCENARIOS.items():
        for policy in POLICIES:
            for seed in SEEDS:
                row = run_once(policy, scenario, params, seed)
                rows.append(row)
                print(
                    f"{scenario:8s} {policy:12s} seed={seed:2d} "
                    f"generated={row['requests_generated']:5d} "
                    f"accepted={row['requests_accepted']:5d} "
                    f"queued={row['requests_queued']:4d} "
                    f"completed={row['requests_completed']:5d} "
                    f"failed={row['requests_failed']:4d} "
                    f"rejected={row['requests_rejected']:4d} "
                    f"peak={row['peak_load_pct']:6.1f}% "
                    f"lat={row['mean_simulated_latency_ms']:6.1f}ms"
                )

    summary = aggregate(rows)
    raw_csv = ROOT / "cwms_data" / "experiment_results.csv"
    summary_csv = ROOT / "cwms_data" / "experiment_summary.csv"
    write_csv(raw_csv, rows)
    write_csv(summary_csv, summary)

    reports = ROOT / "output" / "reports"
    raw_md = reports / "experiment_raw_results.md"
    summary_md = reports / "experiment_summary.md"
    raw_md.write_text(
        to_markdown(rows, "CWMS Raw Experiment Results",
                    "Synthetic local simulation; each row is one seed."),
        encoding="utf-8",
    )
    summary_md.write_text(
        to_markdown(
            summary,
            "CWMS Experiment Summary (mean over seeds)",
            f"Mean over seeds {SEEDS} across {len(SCENARIOS)} scenarios. "
            "The overload scenario uses overload_threshold=80, queue_limit=10, "
            "and request_timeout_ms=100 so overflow and timeouts are exercised.",
        ),
        encoding="utf-8",
    )

    print(f"\nRaw CSV: {raw_csv}")
    print(f"Summary CSV: {summary_csv}")
    print(f"Raw Markdown: {raw_md}")
    print(f"Summary Markdown: {summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())