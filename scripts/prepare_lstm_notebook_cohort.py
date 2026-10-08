"""Materialize the frozen ensemble Top 50 in the notebook's input schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("deploy/wave_v6_advisory/top50.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()

    source = _path(args.input)
    if source.suffix.lower() == ".csv":
        ranked = pd.read_csv(source, usecols=["ticker", "rank"])
        ranked["ticker"] = ranked["ticker"].astype(str).str.strip().str.upper()
        ranked["rank"] = pd.to_numeric(ranked["rank"], errors="raise").astype(int)
        ranked = ranked.sort_values("rank", kind="stable")
        symbols = ranked["ticker"].tolist()
        ranks = ranked["rank"].tolist()
    else:
        payload = json.loads(source.read_text(encoding="utf-8"))
        entries = payload.get("symbols") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise ValueError("Top-50 JSON must contain a symbols list.")
        symbols = [str(item.get("ticker", "")).strip().upper() for item in entries if isinstance(item, dict)]
        ranks = [int(item.get("rank")) for item in entries if isinstance(item, dict) and item.get("rank") is not None]
    if len(symbols) != 50 or len(set(symbols)) != 50 or ranks != list(range(1, 51)):
        raise ValueError("Top-50 JSON must contain 50 unique rank-ordered symbols.")
    excluded = {value.strip().upper() for value in args.exclude if value.strip()}
    symbols = [symbol for symbol in symbols if symbol not in excluded]
    if not symbols:
        raise ValueError("The exclusion list removed every LSTM cohort symbol.")

    output = _path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps([{"ticker": symbol} for symbol in symbols], indent=2), encoding="utf-8")
    temporary.replace(output)
    print(f"Prepared {len(symbols)} LSTM cohort symbols at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
