"""Fail-closed preflight for opening the registered H120 future holdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registration = json.loads(args.registration.read_text(encoding="utf-8"))
    if registration.get("status") != "registered_unopened" or registration.get("outcome_access") != "sealed":
        raise ValueError("Future holdout registration is not sealed and unopened.")
    calendar = pd.DatetimeIndex(pd.read_csv(args.calendar, parse_dates=["date"])["date"].drop_duplicates()).sort_values()
    requested = pd.Timestamp(args.as_of_date)
    start = pd.Timestamp("2026-08-25")  # Registration's explicit first eligible session.
    eligible = calendar[(calendar >= start) & (calendar <= requested)]
    if len(eligible) <= int(registration["horizon_sessions"]):
        raise ValueError("Phase F is not mature: fewer than 120 registered trading sessions are available.")
    raise ValueError("Phase F opening requires the sealed outcome artifact and one-time human approval.")


if __name__ == "__main__":
    raise SystemExit(main())
