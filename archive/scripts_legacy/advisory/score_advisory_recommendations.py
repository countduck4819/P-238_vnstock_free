"""Score live candidate dates with a frozen model and advisory policy.

The input must contain the model feature columns plus ``symbol``, ``date`` and
the configured market-regime feature.  It must not include future labels. PASS
is a watchlist state, not an order instruction.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.evaluation import AdvisoryPolicyConfig, apply_advisory_profile  # noqa: E402
from src.models import WaveXGBoostPredictor  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Live feature parquet.")
    parser.add_argument("--model-run", type=Path, required=True)
    parser.add_argument("--advisory-run", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/wave_ignition_advisory_v1.yaml")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-evidence-features", type=int, default=3)
    return parser.parse_args()


def frozen_policy(config: AdvisoryPolicyConfig, advisory_run: Path) -> AdvisoryPolicyConfig:
    payload = json.loads((advisory_run / "advisory_summary.json").read_text(encoding="utf-8"))
    selected = payload["deployment_policy_selected_from_all_oof_history"]
    ranking = selected["ranking"]
    confidence = selected["confidence"]
    return replace(
        config,
        score_column=str(ranking["score_column"]),
        top_k_max=int(ranking["top_k_max"]),
        minimum_distinct_scores=int(ranking["minimum_distinct_scores"]),
        minimum_history_effective_samples=float(
            confidence["minimum_history_effective_samples"]
        ),
    )


def main() -> None:
    args = parse_args()
    if args.top_evidence_features <= 0:
        raise ValueError("--top-evidence-features must be positive.")
    config = frozen_policy(AdvisoryPolicyConfig.from_yaml(args.config), args.advisory_run)
    profile = pd.read_parquet(args.advisory_run / "confidence_profile.parquet")
    live = pd.read_parquet(args.input)
    if "date" not in live or "symbol" not in live:
        raise ValueError("Live input requires symbol and date columns.")
    live["date"] = pd.to_datetime(live["date"], errors="raise")
    if live.duplicated(["symbol", "date"]).any():
        raise ValueError("Live input has duplicate symbol/date keys.")

    predictor = WaveXGBoostPredictor.from_run(args.model_run)
    prediction = predictor.predict(live)
    evidence = predictor.explain(live, top_features=args.top_evidence_features)
    evidence = evidence.reset_index(drop=True)
    for column in evidence:
        evidence[column] = evidence[column].map(json.dumps)
    scored = live[["symbol", "date", config.market_regime_feature]].merge(
        prediction, on=["symbol", "date"], validate="one_to_one"
    )
    scored = pd.concat([scored.reset_index(drop=True), evidence], axis=1)
    scored = apply_advisory_profile(scored, profile, config)
    scored["prediction_target"] = "Wave H150 entry event, not generic price appreciation"
    scored["ground_truth_available"] = False
    scored["ground_truth"] = pd.NA
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(args.output, index=False)
    passed = int(scored["advisory_status"].eq("PASS").sum())
    print(f"Wrote {len(scored):,} scored rows; PASS={passed:,}: {args.output.resolve()}")


if __name__ == "__main__":
    main()
