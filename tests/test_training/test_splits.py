from __future__ import annotations

import numpy as np
import pandas as pd

from src.training.splits import SplitConfig, build_purged_walk_forward_splits


def make_dataset() -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    calendar = pd.bdate_range("2018-01-01", "2026-01-30")
    rows = []
    for symbol in ("AAA", "BBB"):
        for position, date in enumerate(calendar[:-20]):
            rows.append(
                {
                    "symbol": symbol,
                    "date": date,
                    "label_end_date": calendar[position + 20],
                    "y_entry": position % 11 == 0,
                }
            )
    return pd.DataFrame(rows), calendar


def test_walk_forward_splits_are_chronological_and_purged() -> None:
    dataset, calendar = make_dataset()
    config = SplitConfig(validation_years=(2020, 2021), test_start="2022-01-01")
    splits, summary = build_purged_walk_forward_splits(dataset, calendar, config)

    for fold_id in ("fold_2020", "fold_2021"):
        train = dataset.merge(splits[fold_id]["train"], on=["symbol", "date"])
        validation = dataset.merge(
            splits[fold_id]["validation"], on=["symbol", "date"]
        )
        validation_start = validation["date"].min()
        boundary_position = calendar.get_loc(validation_start) - config.embargo_sessions
        assert train["label_end_date"].max() < calendar[boundary_position]
        assert train["date"].max() < validation_start
        next_year_start = calendar[calendar >= pd.Timestamp(f"{validation_start.year + 1}-01-01")][0]
        assert validation["label_end_date"].max() < next_year_start

    assert summary["purged_rows"].sum() > 0


def test_final_test_is_disjoint_and_starts_at_requested_year() -> None:
    dataset, calendar = make_dataset()
    config = SplitConfig(validation_years=(2020,), test_start="2022-01-01")
    splits, _ = build_purged_walk_forward_splits(dataset, calendar, config)
    train_keys = splits["final"]["train"]
    test_keys = splits["final"]["test"]

    overlap = train_keys.merge(test_keys, on=["symbol", "date"])
    assert overlap.empty
    assert test_keys["date"].min().year == 2022
    assert np.all(train_keys["date"] < test_keys["date"].min())


def test_h120_labels_are_purged_before_the_embargo_boundary() -> None:
    """A H120 outcome must finish before a validation boundary is observed."""
    calendar = pd.bdate_range("2018-01-01", "2022-12-30")
    horizon_sessions = 120
    rows = [
        {
            "symbol": "AAA",
            "date": date,
            "label_end_date": calendar[position + horizon_sessions],
            "y_entry": int(position % 7 == 0),
        }
        for position, date in enumerate(calendar[:-horizon_sessions])
    ]
    dataset = pd.DataFrame(rows)
    config = SplitConfig(validation_years=(2021,), test_start="2022-01-03")

    splits, _ = build_purged_walk_forward_splits(dataset, calendar, config)
    train = dataset.merge(splits["fold_2021"]["train"], on=["symbol", "date"])
    validation = dataset.merge(
        splits["fold_2021"]["validation"], on=["symbol", "date"]
    )
    validation_start = validation["date"].min()
    boundary_position = calendar.get_loc(validation_start) - config.embargo_sessions

    assert train["label_end_date"].max() < calendar[boundary_position]
    last_train_position = calendar.get_loc(train["date"].max())
    validation_position = calendar.get_loc(validation_start)
    assert validation_position - last_train_position >= horizon_sessions + config.embargo_sessions + 1
