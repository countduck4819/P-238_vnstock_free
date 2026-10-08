"""Run Phase-7 diagnostics on the canonical H120 label without changing it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_regression

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL_RUN = Path(
    "data/labels/wave_ignition_snapshot/wave_continuation_h120_v3_eventweights/runs/20260824T054805Z"
)
DEFAULT_FEATURE_RUN = Path(
    "data/features/wave_ignition_snapshot/wave_ignition_v2/runs/20260823T050008Z"
)
DEFAULT_DATASET_RUN = Path(
    "data/training/wave_ignition_snapshot/wave_dataset_continuation_h120/runs/20260823T050830Z"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-run", type=Path, default=DEFAULT_LABEL_RUN)
    parser.add_argument("--feature-run", type=Path, default=DEFAULT_FEATURE_RUN)
    parser.add_argument("--dataset-run", type=Path, default=DEFAULT_DATASET_RUN)
    parser.add_argument(
        "--output", type=Path, default=Path("reports/h120_improvement/label_sensitivity")
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def read_labels(label_run: Path) -> pd.DataFrame:
    columns = [
        "symbol",
        "date",
        "y_entry",
        "target_return",
        "excess_market_return",
        "terminal_return",
        "maximum_drawdown",
        "label_version",
    ]
    paths = sorted(label_run.glob("labels/year=*/labels.parquet"))
    if not paths:
        raise FileNotFoundError(f"No label partitions found in {label_run}")
    labels = pd.concat((pd.read_parquet(path, columns=columns) for path in paths), ignore_index=True)
    labels["date"] = pd.to_datetime(labels["date"], errors="raise")
    return labels.loc[labels["y_entry"].notna()].copy()


def read_regime(feature_run: Path) -> pd.DataFrame:
    paths = sorted(feature_run.glob("stock_features/year=*/features.parquet"))
    regime = pd.concat(
        (
            pd.read_parquet(path, columns=["symbol", "date", "market_regime_score"])
            for path in paths
        ),
        ignore_index=True,
    )
    regime["date"] = pd.to_datetime(regime["date"], errors="raise")
    return regime


def validation_fold_map(dataset_run: Path) -> pd.DataFrame:
    records: list[pd.DataFrame] = []
    for fold in sorted((dataset_run / "splits").glob("fold_*")):
        keys = pd.read_parquet(fold / "validation_keys.parquet")
        keys["date"] = pd.to_datetime(keys["date"], errors="raise")
        keys["fold_id"] = fold.name
        records.append(keys)
    return pd.concat(records, ignore_index=True)


def quintile(values: pd.Series) -> pd.Series:
    ranked = values.rank(method="first")
    return pd.qcut(ranked, q=5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    expected = output / "label_sensitivity_summary.json"
    if expected.exists() and not args.overwrite:
        raise FileExistsError(f"{expected} exists; use --overwrite to replace it.")
    labels = read_labels(args.label_run.resolve())
    labels = labels.merge(
        read_regime(args.feature_run.resolve()), on=["symbol", "date"], how="left", validate="one_to_one"
    )
    labels = labels.merge(
        validation_fold_map(args.dataset_run.resolve()),
        on=["symbol", "date"],
        how="left",
        validate="one_to_one",
    )
    labels["fold_id"] = labels["fold_id"].fillna("outside_oof_validation")
    labels["market_regime_quintile"] = quintile(labels["market_regime_score"])
    labels["hurdle_branch"] = np.where(
        np.isclose(labels["target_return"], 0.08, atol=1e-12),
        "floor_8pct",
        "volatility_scaled",
    )
    labels["passes_excess_hurdle"] = labels["excess_market_return"].ge(labels["target_return"])
    labels["passes_terminal_return"] = labels["terminal_return"].ge(0.0)
    labels["passes_drawdown"] = labels["maximum_drawdown"].ge(-0.20)
    distribution = (
        labels.groupby(["fold_id", "market_regime_quintile", "hurdle_branch"], observed=True)
        .agg(
            rows=("symbol", "size"),
            positive_rate=("y_entry", "mean"),
            hurdle_mean=("target_return", "mean"),
            hurdle_median=("target_return", "median"),
            excess_condition_rate=("passes_excess_hurdle", "mean"),
            terminal_condition_rate=("passes_terminal_return", "mean"),
            drawdown_condition_rate=("passes_drawdown", "mean"),
        )
        .reset_index()
    )
    regime_valid = labels.loc[labels["market_regime_score"].notna()].copy()
    sample = regime_valid.sample(min(len(regime_valid), 50000), random_state=238)
    mutual_information = float(
        mutual_info_regression(
            sample[["market_regime_score"]], sample["target_return"], random_state=238
        )[0]
    )
    summary = {
        "label_version": str(labels["label_version"].iloc[0]),
        "labeled_rows": int(len(labels)),
        "positive_rate": float(labels["y_entry"].mean()),
        "floor_8pct_rate": float(labels["hurdle_branch"].eq("floor_8pct").mean()),
        "volatility_scaled_rate": float(labels["hurdle_branch"].eq("volatility_scaled").mean()),
        "hurdle_market_regime_spearman": float(
            labels["target_return"].corr(labels["market_regime_score"], method="spearman")
        ),
        "hurdle_market_regime_mutual_information": mutual_information,
        "policy": "diagnostic_only_canonical_h120_label_unchanged",
        "not_trade_authorized": True,
    }
    output.mkdir(parents=True, exist_ok=True)
    distribution.to_csv(output / "hurdle_distribution_by_fold_regime.csv", index=False)
    (output / "label_sensitivity_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
