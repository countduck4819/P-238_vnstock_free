"""Audit the active H120 continuation labels before model training."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.labels import (  # noqa: E402
    EVENT_ID_SCHEME,
    attach_continuation_weight_components,
    continuation_event_id,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-run", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.label_run.glob("labels/year=*/labels.parquet"))
    if not paths:
        raise FileNotFoundError(f"No label partitions found in {args.label_run}")
    columns = [
        "symbol",
        "date",
        "entry_date",
        "label_end_date",
        "label_status",
        "y_entry",
        "y_strength",
        "terminal_return",
        "excess_market_return",
        "maximum_drawdown",
        "sample_weight",
        "event_id",
        "event_start_date",
        "label_version",
    ]
    labels = pd.concat((pd.read_parquet(path, columns=columns) for path in paths), ignore_index=True)
    for column in ("date", "entry_date", "label_end_date", "event_start_date"):
        labels[column] = pd.to_datetime(labels[column], errors="raise")
    valid = labels.loc[labels["y_entry"].notna()].copy()
    expected_event_id = pd.Series(
        [
            continuation_event_id(label_version, symbol, entry_date, label_end_date)
            for label_version, symbol, entry_date, label_end_date in zip(
                valid["label_version"],
                valid["symbol"],
                valid["entry_date"],
                valid["label_end_date"],
                strict=True,
            )
        ],
        index=valid.index,
        dtype="string",
    )
    weights = attach_continuation_weight_components(
        labels,
        class_balance_mode="none",
        include_date_balance=True,
    )
    violations = {
        "duplicate_symbol_date": int(labels.duplicated(["symbol", "date"]).sum()),
        "entry_not_after_decision": int(valid["entry_date"].le(valid["date"]).sum()),
        "label_end_before_entry": int(valid["label_end_date"].lt(valid["entry_date"]).sum()),
        "positive_without_strength": int(
            valid[valid["y_entry"].eq(1) & valid["y_strength"].isna()].shape[0]
        ),
        "negative_with_strength": int(
            valid[valid["y_entry"].eq(0) & valid["y_strength"].notna()].shape[0]
        ),
        "event_id_null": int(valid["event_id"].isna().sum()),
        "event_id_collision": int(valid["event_id"].duplicated().sum()),
        "event_start_not_entry": int(
            valid["event_start_date"].ne(valid["entry_date"]).sum()
        ),
        "event_id_not_current_hash_scheme": int(valid["event_id"].ne(expected_event_id).sum()),
    }
    yearly = (
        valid.assign(year=valid["date"].dt.year)
        .groupby("year", as_index=False)
        .agg(
            rows=("y_entry", "size"),
            positive_rows=("y_entry", "sum"),
            positive_rate=("y_entry", "mean"),
            terminal_return_median=("terminal_return", "median"),
            excess_market_return_median=("excess_market_return", "median"),
            maximum_drawdown_median=("maximum_drawdown", "median"),
        )
    )
    identity_by_date = (
        valid.assign(
            event_id_null=valid["event_id"].isna(),
            event_start_not_entry=valid["event_start_date"].ne(valid["entry_date"]),
            event_id_not_current_hash_scheme=valid["event_id"].ne(expected_event_id),
        )
        .groupby("date", as_index=False)
        .agg(
            labeled_rows=("symbol", "size"),
            event_id_null=("event_id_null", "sum"),
            event_start_not_entry=("event_start_not_entry", "sum"),
            event_id_not_current_hash_scheme=("event_id_not_current_hash_scheme", "sum"),
        )
    )
    weight_columns = [
        "event_concurrency_mean",
        "event_uniqueness_weight",
        "date_balance_weight",
        "class_balance_weight",
        "sample_weight_final",
        "sample_weight",
    ]
    weighted_valid = weights.loc[weights["y_entry"].notna(), weight_columns]
    weight_summary = weighted_valid.describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99]).T
    weight_summary.insert(
        0,
        "effective_sample_size",
        [
            float(values.sum() ** 2 / np.square(values).sum())
            if np.square(values).sum() > 0
            else np.nan
            for _, values in weighted_valid.items()
        ],
    )
    report = {
        "label_run": str(args.label_run.resolve()),
        "rows": int(len(labels)),
        "labeled_rows": int(len(valid)),
        "positive_rate": float(valid["y_entry"].mean()) if len(valid) else None,
        "event_id_scheme": EVENT_ID_SCHEME,
        "weight_policy": {
            "event_uniqueness_weight": "per-symbol interval concurrency",
            "date_balance_weight": "decision-date balance",
            "class_balance_weight": "not fit in this global audit; fit per training fold",
            "sample_weight_final": "uniqueness x date balance, normalized",
        },
        "violations": violations,
        "status": "pass" if not any(violations.values()) else "fail",
    }
    audit = args.label_run / "audit"
    yearly.to_csv(audit / "yearly_distribution.csv", index=False, encoding="utf-8-sig")
    identity_by_date.to_csv(audit / "event_identity_by_date.csv", index=False, encoding="utf-8-sig")
    weight_summary.to_csv(audit / "event_weight_distribution.csv", encoding="utf-8-sig")
    (audit / "continuation_label_audit.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if report["status"] != "pass":
        raise RuntimeError("Continuation label audit failed.")


if __name__ == "__main__":
    main()
