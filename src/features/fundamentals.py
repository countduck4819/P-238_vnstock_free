"""Point-in-time validation helpers for optional fundamental features."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class FundamentalInputConfig:
    symbol_column: str = "symbol"
    report_period_column: str = "report_period"
    publication_date_column: str = "publication_date"
    asof_date_column: str = "date"


def validate_point_in_time_frame(
    frame: pd.DataFrame,
    config: FundamentalInputConfig = FundamentalInputConfig(),
) -> dict[str, Any]:
    """Audit a fundamental panel for publication-time leakage and key issues."""
    required = {
        config.symbol_column,
        config.report_period_column,
        config.publication_date_column,
        config.asof_date_column,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        return {"status": "blocked", "rows": int(len(frame)), "missing_columns": missing}
    result = frame.copy()
    for column in (config.report_period_column, config.publication_date_column, config.asof_date_column):
        result[column] = pd.to_datetime(result[column], errors="coerce")
    invalid_dates = result[[config.report_period_column, config.publication_date_column, config.asof_date_column]].isna().any(axis=1)
    future_publication = result[config.publication_date_column] > result[config.asof_date_column]
    duplicate_keys = result.duplicated(
        [config.symbol_column, config.report_period_column, config.asof_date_column], keep=False
    )
    return {
        "status": "pass" if not (invalid_dates | future_publication | duplicate_keys).any() else "blocked",
        "rows": int(len(result)),
        "symbols": int(result[config.symbol_column].nunique(dropna=True)),
        "invalid_date_rows": int(invalid_dates.sum()),
        "future_publication_rows": int(future_publication.sum()),
        "duplicate_asof_key_rows": int(duplicate_keys.sum()),
        "max_publication_lag_days": _max_lag_days(result, config),
    }


def _max_lag_days(frame: pd.DataFrame, config: FundamentalInputConfig) -> float | None:
    lag = (frame[config.asof_date_column] - frame[config.publication_date_column]).dt.total_seconds() / 86400
    lag = lag.dropna()
    return float(lag.max()) if not lag.empty else None
