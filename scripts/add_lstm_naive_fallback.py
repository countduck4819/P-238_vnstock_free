"""Replace an out-of-cohort LSTM forecast with a transparent last-close fallback."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument(
        "--remove-ticker",
        help="Optional symbol to replace when the input contains an extra non-serving forecast.",
    )
    parser.add_argument(
        "--template-ticker",
        help="Optional symbol whose forecast dates and timestamp seed a newly added fallback.",
    )
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()
    remove_ticker = str(args.remove_ticker or "").strip().upper()
    template_ticker = str(args.template_ticker or "").strip().upper()
    payload = json.loads(args.predictions.read_text(encoding="utf-8"))
    source = payload.get(remove_ticker) or payload.get(ticker) or payload.get(template_ticker)
    if not isinstance(source, dict) or not isinstance(source.get("future"), list) or len(source["future"]) != 78:
        raise ValueError("A replacement or template ticker must provide a 78-session forecast.")
    history_path = args.snapshot_dir / f"{ticker}.csv"
    history = pd.read_csv(history_path, usecols=["time", "close"])
    history["time"] = pd.to_datetime(history["time"], errors="coerce")
    history["close"] = pd.to_numeric(history["close"], errors="coerce")
    as_of = pd.Timestamp(args.as_of_date)
    history = history.dropna().loc[lambda frame: frame["time"] <= as_of].sort_values("time")
    if history.empty:
        raise ValueError(f"No valid {ticker} close through {args.as_of_date}.")
    last_close = float(history.iloc[-1]["close"])
    if remove_ticker and remove_ticker != ticker:
        payload.pop(remove_ticker, None)
    payload[ticker] = {
        "predicted_on": source.get("predicted_on"),
        "last_close_price": last_close,
        "chart_path": None,
        "forecast_method": "naive_last_close_fallback",
        "fallback_reason": "Insufficient history for the LSTM minimum sequence requirement.",
        "future": [
            {"date": str(row["date"]), "predicted_close": last_close}
            for row in source["future"]
        ],
    }
    temporary = args.predictions.with_suffix(args.predictions.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")
    temporary.replace(args.predictions)
    digest = hashlib.sha256(args.predictions.read_bytes()).hexdigest()
    for release_path in args.predictions.parent.glob("*release.json"):
        release = json.loads(release_path.read_text(encoding="utf-8"))
        record = release.get("prediction_output")
        if not isinstance(record, dict) or Path(str(record.get("path", ""))).name != args.predictions.name:
            continue
        record["sha256"] = digest
        record["size_bytes"] = args.predictions.stat().st_size
        temporary_release = release_path.with_suffix(release_path.suffix + ".tmp")
        temporary_release.write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary_release.replace(release_path)
    print(json.dumps({"ticker": ticker, "last_close": last_close, "sessions": 78, "removed": remove_ticker}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
