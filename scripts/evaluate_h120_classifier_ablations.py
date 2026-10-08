"""Compare two classifier ablations by paired daily Top-10 bootstrap."""

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

from src.evaluation.wave_model import daily_top_k_metrics, paired_daily_ranking_comparison  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--champion-oof", required=True, type=Path)
    parser.add_argument("--challenger-oof", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=238)
    return parser.parse_args()


def bootstrap_delta(values: np.ndarray, samples: int, seed: int) -> dict[str, float | int]:
    if not len(values):
        return {"estimate": np.nan, "lower": np.nan, "upper": np.nan, "samples": 0}
    random = np.random.default_rng(seed)
    means = np.array(
        [values[random.integers(0, len(values), size=len(values))].mean() for _ in range(samples)]
    )
    return {
        "estimate": float(values.mean()),
        "lower": float(np.quantile(means, 0.025)),
        "upper": float(np.quantile(means, 0.975)),
        "samples": samples,
    }


def main() -> int:
    args = parse_args()
    champion = pd.read_parquet(args.champion_oof)
    challenger = pd.read_parquet(args.challenger_oof)
    champion_daily = daily_top_k_metrics(champion, "p_entry_raw", k=10)
    challenger_daily = daily_top_k_metrics(challenger, "p_entry_raw", k=10)
    paired, summary = paired_daily_ranking_comparison(champion_daily, challenger_daily)
    result = {
        "status": "research_only_paired_classifier_ablation",
        "champion_p_at_10": float(champion_daily["precision_at_k"].mean()),
        "challenger_p_at_10": float(challenger_daily["precision_at_k"].mean()),
        "paired": summary,
        "precision_at_10_bootstrap": bootstrap_delta(
            paired["delta_precision_at_k"].to_numpy(float), args.bootstrap_samples, args.seed
        ),
        "not_trade_authorized": True,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    champion_daily.to_csv(args.output / "daily_top10_champion.csv", index=False)
    challenger_daily.to_csv(args.output / "daily_top10_challenger.csv", index=False)
    paired.to_csv(args.output / "daily_top10_paired.csv", index=False)
    (args.output / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
