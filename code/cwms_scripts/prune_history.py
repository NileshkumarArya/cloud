#!/usr/bin/env python3
"""Prune old SQLite simulation history while retaining recent runs."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cwms_simulator.storage import ResultsStore  # noqa: E402


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prune CWMS simulation history")
    parser.add_argument(
        "--db",
        default=os.environ.get("CWMS_DB_PATH", str(ROOT / "cwms_data" / "cwms.db")),
        help="SQLite database path",
    )
    parser.add_argument(
        "--keep-latest",
        type=int,
        default=50,
        help="Number of newest runs to retain",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the number of runs without deleting anything",
    )
    return parser


def main(args: argparse.Namespace) -> int:
    if args.keep_latest < 0:
        print("error: keep-latest cannot be negative")
        return 2

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: database not found: {db_path}")
        return 2

    store = ResultsStore(db_path)
    before = store.count_runs()
    if args.dry_run:
        deleted = max(0, before - args.keep_latest)
        print(f"database={db_path}")
        print(f"runs_before={before}")
        print(f"would_delete={deleted}")
        print(f"would_remain={before - deleted}")
        return 0

    deleted = store.prune_runs(keep_latest=args.keep_latest)
    print(f"database={db_path}")
    print(f"runs_before={before}")
    print(f"deleted={deleted}")
    print(f"runs_after={store.count_runs()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(create_parser().parse_args()))
