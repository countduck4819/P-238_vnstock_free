"""Operational refresh and drift checks for the advisory watchlist."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


@dataclass(frozen=True)
class MonitoringConfig:
    retrain_after_sessions: int
    recalibrate_after_sessions: int
    minimum_resolved_rows_for_calibration: int
    maximum_expected_calibration_error: float

    @classmethod
    def from_yaml(cls, path: Path) -> MonitoringConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))["operations"]
        config = cls(
            retrain_after_sessions=int(payload["retrain_after_sessions"]),
            recalibrate_after_sessions=int(payload["recalibrate_after_sessions"]),
            minimum_resolved_rows_for_calibration=int(
                payload["minimum_resolved_rows_for_calibration"]
            ),
            maximum_expected_calibration_error=float(
                payload["maximum_expected_calibration_error"]
            ),
        )
        if min(
            config.retrain_after_sessions,
            config.recalibrate_after_sessions,
            config.minimum_resolved_rows_for_calibration,
        ) <= 0:
            raise ValueError("Monitoring intervals and resolved-row minimum must be positive.")
        if not 0 <= config.maximum_expected_calibration_error <= 1:
            raise ValueError("maximum_expected_calibration_error must be in [0, 1].")
        return config


def _sessions_since(dates: pd.Series, previous: pd.Timestamp) -> int:
    unique = pd.DatetimeIndex(pd.to_datetime(dates, errors="raise").unique()).sort_values()
    return int(unique[unique > previous].size)


def expected_calibration_error(frame: pd.DataFrame, bins: int = 10) -> float:
    """Unweighted ECE for resolved live rows; NaN means not yet measurable."""
    required = {"p_entry_calibrated", "ground_truth"}
    if not required.issubset(frame.columns):
        return float("nan")
    resolved = frame.dropna(subset=["p_entry_calibrated", "ground_truth"]).copy()
    if resolved.empty:
        return float("nan")
    resolved["bucket"] = pd.cut(
        resolved["p_entry_calibrated"], bins=np.linspace(0.0, 1.0, bins + 1), include_lowest=True
    )
    grouped = resolved.groupby("bucket", observed=True)
    return float(
        sum(abs(group["p_entry_calibrated"].mean() - group["ground_truth"].mean()) * len(group) for _, group in grouped)
        / len(resolved)
    )


def build_refresh_plan(
    ledger: pd.DataFrame,
    *,
    last_retrained_at: pd.Timestamp,
    last_recalibrated_at: pd.Timestamp,
    config: MonitoringConfig,
) -> dict[str, Any]:
    """Decide if a human-approved rolling retrain/recalibration is due.

    This function never trains automatically.  It turns fresh trading-session
    evidence into an auditable request, keeping deployment changes reviewable.
    """
    if "date" not in ledger:
        raise ValueError("Monitoring ledger requires a date column.")
    dates = pd.to_datetime(ledger["date"], errors="raise")
    if "ground_truth_available" in ledger:
        resolved_mask = ledger["ground_truth_available"].fillna(False).astype(bool)
    else:
        resolved_mask = pd.Series(False, index=ledger.index)
    resolved = ledger.loc[resolved_mask].copy()
    resolved_rows = int(len(resolved))
    sessions_since_retrain = _sessions_since(dates, last_retrained_at)
    sessions_since_calibration = _sessions_since(dates, last_recalibrated_at)
    ece = expected_calibration_error(resolved)
    retrain_due = sessions_since_retrain >= config.retrain_after_sessions
    recalibration_due = (
        sessions_since_calibration >= config.recalibrate_after_sessions
        and resolved_rows >= config.minimum_resolved_rows_for_calibration
    )
    drift_due = np.isfinite(ece) and ece > config.maximum_expected_calibration_error
    return {
        "sessions_since_retrain": sessions_since_retrain,
        "sessions_since_calibration": sessions_since_calibration,
        "resolved_rows": resolved_rows,
        "expected_calibration_error": ece,
        "retrain_due": bool(retrain_due or drift_due),
        "recalibration_due": bool(recalibration_due or drift_due),
        "reasons": [
            *(["retrain_interval_reached"] if retrain_due else []),
            *(["recalibration_interval_and_resolved_rows_reached"] if recalibration_due else []),
            *(["live_calibration_drift"] if drift_due else []),
        ],
    }
