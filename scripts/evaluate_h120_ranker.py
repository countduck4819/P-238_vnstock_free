"""Produce paired daily ranking evidence for the H120 stock-only ranker."""

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

from src.evaluation.h120_ranker_reporting import summarize_daily_ranking_metrics  # noqa: E402
from src.evaluation.wave_model import (  # noqa: E402
    daily_top_k_metrics,
    moving_block_bootstrap_paired_daily,
    paired_daily_ranking_comparison,
)

DEFAULT_RANKER_OOF = Path(
    "models/wave_ignition/h120_ranker_stock_primitives_v1/runs/20260824T061029Z/"
    "predictions/oof_ranker_predictions.parquet"
)
DEFAULT_BASELINE_OOF = Path(
    "models/wave_ignition_snapshot/xgboost_continuation_h120/runs/20260823T052814Z/"
    "predictions/oof_predictions.parquet"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranker-oof", type=Path, default=DEFAULT_RANKER_OOF)
    parser.add_argument("--baseline-oof", type=Path, default=DEFAULT_BASELINE_OOF)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=238)
    parser.add_argument("--date-block-size", type=int, default=24)
    parser.add_argument(
        "--model-seed",
        type=int,
        help="Frozen XGBRanker seed; required for an R2 seed-confirmation artifact.",
    )
    return parser.parse_args()


def paired_bootstrap(
    paired: pd.DataFrame,
    metric: str,
    *,
    samples: int,
    seed: int,
) -> dict[str, float]:
    values = paired[f"delta_{metric}"].dropna().to_numpy(dtype=float)
    if not len(values):
        return {"estimate": np.nan, "lower": np.nan, "upper": np.nan, "samples": 0}
    random = np.random.default_rng(seed)
    draws = np.array(
        [values[random.integers(0, len(values), size=len(values))].mean() for _ in range(samples)]
    )
    return {
        "estimate": float(values.mean()),
        "lower": float(np.quantile(draws, 0.025)),
        "upper": float(np.quantile(draws, 0.975)),
        "samples": int(samples),
    }


def main() -> int:
    args = parse_args()
    ranker = pd.read_parquet(args.ranker_oof)
    baseline = pd.read_parquet(args.baseline_oof)
    ranker_dates = pd.to_datetime(ranker["date"], errors="raise").drop_duplicates()
    baseline["date"] = pd.to_datetime(baseline["date"], errors="raise")
    missing_dates = ranker_dates[~ranker_dates.isin(baseline["date"])]
    if len(missing_dates):
        raise ValueError("Baseline OOF does not cover every ranker evaluation date.")
    baseline = baseline.loc[baseline["date"].isin(ranker_dates)].copy()
    ranker_daily = daily_top_k_metrics(ranker, "rank_score", k=10)
    baseline_daily = daily_top_k_metrics(baseline, "p_entry_raw", k=10)
    paired, paired_summary = paired_daily_ranking_comparison(baseline_daily, ranker_daily)
    baseline_summary = summarize_daily_ranking_metrics(baseline_daily, baseline)
    ranker_summary = summarize_daily_ranking_metrics(ranker_daily, ranker)
    metrics = {
        "status": "research_only_paired_ranking_evidence",
        "random_seed": args.model_seed,
        "ranking_contract": "baseline=p_entry_raw; challenger=rank_score",
        "baseline": {
            "mean_p_at_10": baseline_summary["precision_at_k"]["mean"],
            "worst_fold_p_at_10": baseline_summary["precision_at_k"]["worst_fold"],
            "fold_p_at_10": baseline_summary["precision_at_k"]["fold_means"],
            "daily_metrics": baseline_summary,
        },
        "ranker": {
            "mean_p_at_10": ranker_summary["precision_at_k"]["mean"],
            "worst_fold_p_at_10": ranker_summary["precision_at_k"]["worst_fold"],
            "fold_p_at_10": ranker_summary["precision_at_k"]["fold_means"],
            "daily_metrics": ranker_summary,
        },
        "paired": {
            **paired_summary,
            "precision_at_k_iid_date_bootstrap": paired_bootstrap(
                paired,
                "precision_at_k",
                samples=args.bootstrap_samples,
                seed=args.seed,
            ),
            "precision_at_k_bootstrap": paired_bootstrap(
                paired,
                "precision_at_k",
                samples=args.bootstrap_samples,
                seed=args.seed,
            ),
            "precision_at_k_moving_block_bootstrap": moving_block_bootstrap_paired_daily(
                paired,
                "precision_at_k",
                samples=args.bootstrap_samples,
                random_seed=args.seed,
                block_size=args.date_block_size,
            ),
        },
        "not_trade_authorized": True,
    }
    output = args.output or args.ranker_oof.resolve().parents[1] / "evaluation"
    output.mkdir(parents=True, exist_ok=True)
    baseline_daily.to_csv(output / "daily_top10_baseline.csv", index=False)
    ranker_daily.to_csv(output / "daily_top10_ranker.csv", index=False)
    paired.to_csv(output / "daily_top10_paired.csv", index=False)
    (output / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
