"""Tests for SQLite persistence of simulation runs."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cwms_simulator.simulator import CWMSimulator, SimulationConfig
from cwms_simulator.storage import ResultsStore


class TestResultsStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "nested" / "cwms.db"
        self.store = ResultsStore(self.db_path)

    def _result(self, policy="least-loaded", intervals=5):
        sim = CWMSimulator(SimulationConfig(
            policy=policy, intervals=intervals, burst_start=0, burst_end=0,
            seed=11, output_path="unused.csv",
        ))
        return sim.run()

    def test_creates_database_file(self):
        self.assertTrue(self.db_path.exists())

    def test_save_and_count(self):
        run_id = self.store.save_run(self._result(), label="unit-test")
        self.assertIsInstance(run_id, int)
        self.assertEqual(self.store.count_runs(), 1)

    def test_roundtrip_fields(self):
        result = self._result(intervals=5)
        run_id = self.store.save_run(result, label="burst")
        run = self.store.get_run(run_id)
        self.assertIsNotNone(run)
        self.assertEqual(run["label"], "burst")
        self.assertEqual(run["policy"], "least-loaded")
        self.assertEqual(run["config"]["intervals"], 5)
        self.assertEqual(len(run["intervals"]), 5)
        self.assertEqual(len(run["nodes"]), 3)
        self.assertEqual(
            run["summary"]["system_metrics"]["total_requests_assigned"],
            result.final_system_metrics.total_requests_assigned,
        )

    def test_persists_across_instances(self):
        run_id = self.store.save_run(self._result())
        reopened = ResultsStore(self.db_path)
        self.assertEqual(reopened.count_runs(), 1)
        self.assertEqual(reopened.get_run(run_id)["id"], run_id)

    def test_list_newest_first(self):
        first = self.store.save_run(self._result())
        second = self.store.save_run(self._result(policy="round-robin"))
        runs = self.store.list_runs()
        self.assertEqual([r["id"] for r in runs], [second, first])

    def test_list_limit(self):
        for _ in range(3):
            self.store.save_run(self._result())
        self.assertEqual(len(self.store.list_runs(limit=2)), 2)

    def test_missing_run(self):
        self.assertIsNone(self.store.get_run(999))

    def test_interval_values(self):
        result = self._result()
        run = self.store.get_run(self.store.save_run(result))
        first = run["intervals"][0]
        self.assertEqual(first["requests_generated"], result.intervals[0].requests_generated)
        self.assertIsInstance(first["surge_detected"], bool)
        self.assertIn("forecast_predicted", first)
        self.assertIn("requests_queued", first)
        self.assertIn("requests_timed_out", first)

    def test_node_admission_fields_roundtrip(self):
        result = self._result()
        run = self.store.get_run(self.store.save_run(result))
        self.assertIn("requests_queued", run["nodes"][0])
        self.assertIn("requests_timed_out", run["nodes"][0])

    def test_prune_keeps_newest_runs(self):
        for policy in ("least-loaded", "round-robin", "fcfs", "adaptive"):
            self.store.save_run(self._result(policy=policy))
        deleted = self.store.prune_runs(keep_latest=2)
        self.assertEqual(deleted, 2)
        self.assertEqual(self.store.count_runs(), 2)
        self.assertEqual(len(self.store.list_runs()), 2)
        with self.assertRaises(ValueError):
            self.store.prune_runs(keep_latest=-1)

    def test_v1_database_is_migrated(self):
        db_path = Path(self.tmp.name) / "old.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                label TEXT NOT NULL,
                policy TEXT NOT NULL,
                config_json TEXT NOT NULL,
                summary_json TEXT NOT NULL
            );
            CREATE TABLE interval_metrics (
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                interval INTEGER NOT NULL,
                requests_generated INTEGER NOT NULL,
                requests_assigned INTEGER NOT NULL,
                requests_rejected INTEGER NOT NULL,
                surge_detected INTEGER NOT NULL,
                surge_type TEXT,
                forecast_predicted REAL,
                forecast_actual REAL,
                recommendation TEXT,
                max_load REAL,
                PRIMARY KEY (run_id, interval)
            );
            CREATE TABLE node_metrics (
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                node_name TEXT NOT NULL,
                requests_assigned INTEGER NOT NULL,
                requests_completed INTEGER NOT NULL,
                requests_failed INTEGER NOT NULL,
                avg_latency REAL NOT NULL,
                max_load REAL NOT NULL,
                healthy INTEGER NOT NULL,
                PRIMARY KEY (run_id, node_name)
            );
            PRAGMA user_version = 1;
            """
        )
        conn.commit()
        conn.close()

        migrated = ResultsStore(db_path)
        with sqlite3.connect(db_path) as check:
            interval_columns = {
                row[1] for row in check.execute("PRAGMA table_info(interval_metrics)")
            }
            node_columns = {
                row[1] for row in check.execute("PRAGMA table_info(node_metrics)")
            }
            version = check.execute("PRAGMA user_version").fetchone()[0]
        for column in ("requests_completed", "requests_queued", "requests_timed_out"):
            self.assertIn(column, interval_columns)
        for column in ("requests_queued", "requests_timed_out"):
            self.assertIn(column, node_columns)
        self.assertEqual(version, 2)

        run_id = migrated.save_run(self._result(intervals=2))
        self.assertIsNotNone(migrated.get_run(run_id))


if __name__ == "__main__":
    unittest.main()