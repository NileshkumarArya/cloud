"""
SQLite persistence for CWMS simulation runs.

Stores run configuration, summary, per-interval metrics, and per-node metrics
so results survive application restarts. Uses only the Python standard library.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .simulator import SimulationResult

SCHEMA_VERSION = 2

INTERVAL_COLUMNS = {
    "requests_completed": "INTEGER NOT NULL DEFAULT 0",
    "requests_failed": "INTEGER NOT NULL DEFAULT 0",
    "requests_timed_out": "INTEGER NOT NULL DEFAULT 0",
    "requests_queued": "INTEGER NOT NULL DEFAULT 0",
    "requests_rejected_overload": "INTEGER NOT NULL DEFAULT 0",
    "requests_rejected_no_capacity": "INTEGER NOT NULL DEFAULT 0",
}

NODE_COLUMNS = {
    "requests_queued": "INTEGER NOT NULL DEFAULT 0",
    "requests_timed_out": "INTEGER NOT NULL DEFAULT 0",
}


class ResultsStore:
    """Small SQLite-backed store for completed simulation runs."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @staticmethod
    def _ensure_columns(
        conn: sqlite3.Connection, table: str, columns: Dict[str, str]
    ) -> None:
        existing = {
            row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
        }
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Add columns introduced after the original v1 schema."""
        self._ensure_columns(conn, "interval_metrics", INTERVAL_COLUMNS)
        self._ensure_columns(conn, "node_metrics", NODE_COLUMNS)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    label TEXT NOT NULL,
                    policy TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS interval_metrics (
                    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    interval INTEGER NOT NULL,
                    requests_generated INTEGER NOT NULL,
                    requests_assigned INTEGER NOT NULL,
                    requests_completed INTEGER NOT NULL DEFAULT 0,
                    requests_failed INTEGER NOT NULL DEFAULT 0,
                    requests_timed_out INTEGER NOT NULL DEFAULT 0,
                    requests_queued INTEGER NOT NULL DEFAULT 0,
                    requests_rejected INTEGER NOT NULL,
                    requests_rejected_overload INTEGER NOT NULL DEFAULT 0,
                    requests_rejected_no_capacity INTEGER NOT NULL DEFAULT 0,
                    surge_detected INTEGER NOT NULL,
                    surge_type TEXT,
                    forecast_predicted REAL,
                    forecast_actual REAL,
                    recommendation TEXT,
                    max_load REAL,
                    PRIMARY KEY (run_id, interval)
                );

                CREATE TABLE IF NOT EXISTS node_metrics (
                    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    node_name TEXT NOT NULL,
                    requests_assigned INTEGER NOT NULL,
                    requests_completed INTEGER NOT NULL,
                    requests_failed INTEGER NOT NULL,
                    requests_queued INTEGER NOT NULL DEFAULT 0,
                    requests_timed_out INTEGER NOT NULL DEFAULT 0,
                    avg_latency REAL NOT NULL,
                    max_load REAL NOT NULL,
                    healthy INTEGER NOT NULL,
                    PRIMARY KEY (run_id, node_name)
                );
                """
            )
            self._migrate(conn)

    def save_run(self, result: SimulationResult, label: str = "custom") -> int:
        """Persist a completed run inside a single transaction."""
        summary = result.to_summary_dict()
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO runs (created_at, label, policy, config_json, summary_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    created_at,
                    label,
                    result.config.policy,
                    json.dumps(summary["config"]),
                    json.dumps(summary),
                ),
            )
            run_id = int(cursor.lastrowid)
            conn.executemany(
                """
                INSERT INTO interval_metrics (
                    run_id, interval, requests_generated, requests_assigned,
                    requests_completed, requests_failed, requests_timed_out,
                    requests_queued, requests_rejected,
                    requests_rejected_overload, requests_rejected_no_capacity,
                    surge_detected, surge_type, forecast_predicted,
                    forecast_actual, recommendation, max_load
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        item.interval,
                        item.requests_generated,
                        item.requests_assigned,
                        item.requests_completed,
                        item.requests_failed,
                        item.requests_timed_out,
                        item.requests_queued,
                        item.requests_rejected,
                        item.requests_rejected_overload,
                        item.requests_rejected_no_capacity,
                        1 if item.surge_detected else 0,
                        item.surge_event["surge_type"] if item.surge_event else None,
                        item.forecast.get("predicted"),
                        item.forecast.get("actual"),
                        item.recommendation.get("message"),
                        item.max_load,
                    )
                    for item in result.intervals
                ],
            )
            conn.executemany(
                """
                INSERT INTO node_metrics (
                    run_id, node_name, requests_assigned, requests_completed,
                    requests_failed, requests_queued, requests_timed_out,
                    avg_latency, max_load, healthy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        node.name,
                        node.requests_assigned,
                        node.requests_completed,
                        node.requests_failed,
                        node.requests_queued,
                        node.requests_timed_out,
                        node.avg_latency,
                        node.max_load,
                        1 if node.healthy else 0,
                    )
                    for node in result.final_node_metrics
                ],
            )
        return run_id

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent runs, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, label, policy, config_json, summary_json "
                "FROM runs ORDER BY id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "label": row["label"],
                "policy": row["policy"],
                "config": json.loads(row["config_json"]),
                "summary": json.loads(row["summary_json"]),
            }
            for row in rows
        ]

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Return a single run with interval and node metrics."""
        with self._connect() as conn:
            run = conn.execute(
                "SELECT id, created_at, label, policy, config_json, summary_json "
                "FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                return None
            intervals = conn.execute(
                "SELECT interval, requests_generated, requests_assigned, "
                "requests_completed, requests_failed, requests_timed_out, "
                "requests_queued, requests_rejected, "
                "requests_rejected_overload, requests_rejected_no_capacity, "
                "surge_detected, surge_type, forecast_predicted, "
                "forecast_actual, recommendation, max_load "
                "FROM interval_metrics WHERE run_id = ? ORDER BY interval",
                (run_id,),
            ).fetchall()
            nodes = conn.execute(
                "SELECT node_name, requests_assigned, requests_completed, "
                "requests_failed, requests_queued, requests_timed_out, "
                "avg_latency, max_load, healthy "
                "FROM node_metrics WHERE run_id = ? ORDER BY node_name",
                (run_id,),
            ).fetchall()

        return {
            "id": run["id"],
            "created_at": run["created_at"],
            "label": run["label"],
            "policy": run["policy"],
            "config": json.loads(run["config_json"]),
            "summary": json.loads(run["summary_json"]),
            "intervals": [
                {
                    "interval": row["interval"],
                    "requests_generated": row["requests_generated"],
                    "requests_assigned": row["requests_assigned"],
                    "requests_completed": row["requests_completed"],
                    "requests_failed": row["requests_failed"],
                    "requests_timed_out": row["requests_timed_out"],
                    "requests_queued": row["requests_queued"],
                    "requests_rejected": row["requests_rejected"],
                    "requests_rejected_overload": row["requests_rejected_overload"],
                    "requests_rejected_no_capacity": row["requests_rejected_no_capacity"],
                    "surge_detected": bool(row["surge_detected"]),
                    "surge_type": row["surge_type"],
                    "forecast_predicted": row["forecast_predicted"],
                    "forecast_actual": row["forecast_actual"],
                    "recommendation": row["recommendation"],
                    "max_load": row["max_load"],
                }
                for row in intervals
            ],
            "nodes": [
                {
                    "name": row["node_name"],
                    "requests_assigned": row["requests_assigned"],
                    "requests_completed": row["requests_completed"],
                    "requests_failed": row["requests_failed"],
                    "requests_queued": row["requests_queued"],
                    "requests_timed_out": row["requests_timed_out"],
                    "avg_latency": round(row["avg_latency"], 2),
                    "max_load": round(row["max_load"], 2),
                    "healthy": bool(row["healthy"]),
                }
                for row in nodes
            ],
        }

    def count_runs(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def prune_runs(self, keep_latest: int = 50) -> int:
        """
        Delete older runs, retaining the newest ``keep_latest`` rows.

        Returns:
            Number of runs deleted. Child metric rows cascade automatically.
        """
        if keep_latest < 0:
            raise ValueError("keep_latest cannot be negative")
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM runs WHERE id NOT IN ("
                "SELECT id FROM runs ORDER BY id DESC LIMIT ?"
                ")",
                (keep_latest,),
            )
            return int(cursor.rowcount)