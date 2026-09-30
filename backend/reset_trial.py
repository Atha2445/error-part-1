"""
Reset Vigilinx Trial
--------------------
Resets the subscription row to a fresh 30-day trial immediately.

Usage:
    python reset_trial.py
    python reset_trial.py --db C:\\Vigilinx\\vigilinx.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta

TRIAL_DURATION_DAYS = 30
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _default_db_path() -> str:
    override = os.environ.get("DB_PATH")
    if override:
        return override
    data_dir = os.environ.get("VIGILINX_DATA_DIR")
    if not data_dir:
        data_dir = r"C:\Vigilinx" if os.name == "nt" else os.path.join(BASE_DIR, "data")
    return os.path.join(data_dir, "vigilinx.db")


def reset_trial(db_path: str) -> dict:
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    now = datetime.utcnow()
    trial_end = now + timedelta(days=TRIAL_DURATION_DAYS)
    start_iso = now.isoformat()
    end_iso = trial_end.isoformat()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        before = conn.execute(
            "SELECT plan, trial_start, trial_end FROM subscription WHERE id = 1"
        ).fetchone()

        if before is None:
            conn.execute(
                "INSERT INTO subscription (id, plan, trial_start, trial_end, is_active) "
                "VALUES (1, 'free_trial', ?, ?, 1)",
                (start_iso, end_iso),
            )
        else:
            conn.execute(
                "UPDATE subscription SET plan = 'free_trial', trial_start = ?, "
                "trial_end = ?, is_active = 1, license_key = NULL, activated_at = NULL "
                "WHERE id = 1",
                (start_iso, end_iso),
            )

        conn.commit()
        try:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
        except sqlite3.Error:
            pass

        after = conn.execute(
            "SELECT plan, trial_start, trial_end FROM subscription WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()

    return {
        "before": dict(before) if before else None,
        "after": dict(after) if after else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset Vigilinx free trial.")
    parser.add_argument("--db", default=_default_db_path())
    args = parser.parse_args()

    try:
        result = reset_trial(os.path.abspath(args.db))
    except FileNotFoundError as exc:
        print(exc)
        return 1
    except sqlite3.Error as exc:
        print(f"Reset failed: {exc}")
        return 1

    before = result["before"]
    if before:
        print(f"Previous trial: {before['trial_start']} -> {before['trial_end']} ({before['plan']})")
    after = result["after"]
    print(f"New trial:      {after['trial_start']} -> {after['trial_end']} ({after['plan']})")
    print("Restart Vigilinx to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
