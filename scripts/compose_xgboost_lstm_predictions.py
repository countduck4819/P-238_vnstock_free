"""Compose the V6 ensemble and LSTM forecasts into one deployable JSON artifact."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd


def safe(value):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensemble", type=Path, required=True)
    parser.add_argument("--lstm", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    frame = pd.read_csv(args.ensemble).sort_values("rank", kind="stable")
    top50 = frame.head(50)
    if top50["rank"].tolist() != list(range(1, 51)):
        raise ValueError("Ensemble input must contain rank 1..50.")
    forecasts = json.loads(args.lstm.read_text(encoding="utf-8"))
    symbols = top50["ticker"].astype(str).str.upper().tolist()
    if set(forecasts) != set(symbols):
        raise ValueError("LSTM and ensemble cohorts differ.")
    payload = {
        "schema_version": 1,
        "artifact_type": "v6_xgboost_and_lstm_top50",
        "as_of_date": str(top50.iloc[0]["time"])[:10],
        "predictions": [],
    }
    for row in top50.to_dict(orient="records"):
        symbol = str(row["ticker"]).upper()
        forecast = forecasts[symbol]
        payload["predictions"].append(
            {
                "symbol": symbol,
                "ensemble": {key: safe(value) for key, value in row.items()},
                "price_forecast": forecast,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=safe), encoding="utf-8")
    temporary.replace(args.output)
    print(f"Wrote {len(payload['predictions'])} combined predictions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
