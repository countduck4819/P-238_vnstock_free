"""Purged walk-forward and final holdout splitting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class SplitConfig:
    """Versioned chronological split policy."""

    dataset_version: str = "wave_dataset_v1"
    validation_years: tuple[int, ...] = (2020, 2021, 2022, 2023, 2024)
    test_start: str = "2025-01-01"
    embargo_sessions: int = 5

    @classmethod
    def from_yaml(cls, path: Path) -> SplitConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            dataset_version=payload["dataset_version"],
            validation_years=tuple(int(year) for year in payload["validation_years"]),
            test_start=str(payload["test_start"]),
            embargo_sessions=int(payload["embargo_sessions"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "validation_years": list(self.validation_years),
            "test_start": self.test_start,
            "embargo_sessions": self.embargo_sessions,
        }


def _first_market_date_on_or_after(
    calendar: pd.DatetimeIndex,
    requested_date: pd.Timestamp,
) -> pd.Timestamp:
    eligible = calendar[calendar >= requested_date]
    if eligible.empty:
        raise ValueError(f"No market date exists on or after {requested_date.date()}")
    return pd.Timestamp(eligible[0])


def _embargo_boundary(
    calendar: pd.DatetimeIndex,
    split_start: pd.Timestamp,
    embargo_sessions: int,
) -> pd.Timestamp:
    location = int(calendar.get_loc(split_start))
    boundary_location = location - embargo_sessions
    if boundary_location < 0:
        raise ValueError("Not enough market history to apply the requested embargo.")
    return pd.Timestamp(calendar[boundary_location])


def _keys(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[["symbol", "date"]].sort_values(["date", "symbol"], kind="stable")


def _split_statistics(
    fold_id: str,
    subset: str,
    frame: pd.DataFrame,
    purged_rows: int = 0,
) -> dict[str, Any]:
    positives = int(frame["y_entry"].eq(1).sum())
    negatives = int(frame["y_entry"].eq(0).sum())
    return {
        "fold_id": fold_id,
        "subset": subset,
        "rows": len(frame),
        "symbols": int(frame["symbol"].nunique()) if len(frame) else 0,
        "positive_rows": positives,
        "negative_rows": negatives,
        "positive_rate": positives / len(frame) if len(frame) else None,
        "first_date": frame["date"].min() if len(frame) else pd.NaT,
        "last_date": frame["date"].max() if len(frame) else pd.NaT,
        "maximum_label_end_date": frame["label_end_date"].max() if len(frame) else pd.NaT,
        "purged_rows": purged_rows,
    }


def build_purged_walk_forward_splits(
    dataset: pd.DataFrame,
    market_calendar: pd.DatetimeIndex,
    config: SplitConfig,
) -> tuple[dict[str, dict[str, pd.DataFrame]], pd.DataFrame]:
    """Return split keys and an auditable summary without duplicating features."""
    frame = dataset.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["label_end_date"] = pd.to_datetime(frame["label_end_date"], errors="raise")
    calendar = pd.DatetimeIndex(pd.to_datetime(market_calendar).unique()).sort_values()
    splits: dict[str, dict[str, pd.DataFrame]] = {}
    statistics: list[dict[str, Any]] = []

    for validation_year in config.validation_years:
        validation_start = _first_market_date_on_or_after(
            calendar, pd.Timestamp(f"{validation_year}-01-01")
        )
        next_year_start = _first_market_date_on_or_after(
            calendar, pd.Timestamp(f"{validation_year + 1}-01-01")
        )
        embargo_boundary = _embargo_boundary(
            calendar, validation_start, config.embargo_sessions
        )
        chronological_train = frame["date"] < validation_start
        safe_train = chronological_train & (frame["label_end_date"] < embargo_boundary)
        chronological_validation = frame["date"].between(
            validation_start, next_year_start, inclusive="left"
        )
        validation = chronological_validation & (
            frame["label_end_date"] < next_year_start
        )
        train_frame = frame.loc[safe_train]
        validation_frame = frame.loc[validation]
        if train_frame.empty or validation_frame.empty:
            raise ValueError(
                f"Fold {validation_year} has an empty train or validation subset."
            )
        fold_id = f"fold_{validation_year}"
        splits[fold_id] = {
            "train": _keys(train_frame),
            "validation": _keys(validation_frame),
        }
        purged_rows = int((chronological_train & ~safe_train).sum())
        statistics.append(
            _split_statistics(fold_id, "train", train_frame, purged_rows)
        )
        validation_purged = int((chronological_validation & ~validation).sum())
        statistics.append(
            _split_statistics(
                fold_id, "validation", validation_frame, validation_purged
            )
        )

    test_start = _first_market_date_on_or_after(
        calendar, pd.Timestamp(config.test_start)
    )
    final_embargo_boundary = _embargo_boundary(
        calendar, test_start, config.embargo_sessions
    )
    chronological_final_train = frame["date"] < test_start
    safe_final_train = chronological_final_train & (
        frame["label_end_date"] < final_embargo_boundary
    )
    final_train_frame = frame.loc[safe_final_train]
    test_frame = frame.loc[frame["date"] >= test_start]
    if final_train_frame.empty or test_frame.empty:
        raise ValueError("Final train or test subset is empty.")
    splits["final"] = {
        "train": _keys(final_train_frame),
        "test": _keys(test_frame),
    }
    final_purged = int((chronological_final_train & ~safe_final_train).sum())
    statistics.append(
        _split_statistics("final", "train", final_train_frame, final_purged)
    )
    statistics.append(_split_statistics("final", "test", test_frame))

    return splits, pd.DataFrame(statistics)
