"""Merge a full historical daily export with an incremental V6 snapshot.

The base export is kept intact; only rows after ``base-end`` and up to
``as-of`` are copied from the incremental snapshot.  The output is a strict
CSV-per-symbol V6 snapshot with a manifest suitable for the trainer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


REQUIRED = ["time", "open", "high", "low", "close", "volume"]
DAILY_RE = re.compile(r"(?P<symbol>[A-Za-z0-9]+)_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}_1D\.csv$")
SIMPLE_DAILY_RE = re.compile(r"(?P<symbol>[A-Za-z0-9]+)\.csv$")
NON_OHLCV_STEMS = {"INDUSTRY_MAP", "SYMBOLS"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_ohlcv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")
    frame = frame[REQUIRED].copy()
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    for column in REQUIRED[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=REQUIRED).sort_values("time", kind="stable")
    return frame.drop_duplicates("time", keep="last").reset_index(drop=True)


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--increment-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-end", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--market-base", type=Path, required=True)
    parser.add_argument("--market-increment", type=Path, required=True)
    parser.add_argument("--industry", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = args.base_dir.resolve()
    increment_dir = args.increment_dir.resolve()
    output_dir = args.output_dir.resolve()
    base_end = pd.Timestamp(args.base_end).normalize()
    as_of = pd.Timestamp(args.as_of).normalize()
    if base_end >= as_of:
        raise ValueError("--base-end must precede --as-of")
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite non-empty directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_files: dict[str, Path] = {}
    for path in sorted(base_dir.glob("*.csv")):
        match = DAILY_RE.fullmatch(path.name) or SIMPLE_DAILY_RE.fullmatch(path.name)
        if match and match.group("symbol").upper() not in NON_OHLCV_STEMS:
            daily_files[match.group("symbol").upper()] = path
    if not daily_files:
        raise RuntimeError(f"No daily OHLCV files found in {base_dir}")

    increment_files: dict[str, Path] = {}
    for path in sorted(increment_dir.glob("*.csv")):
        match = DAILY_RE.fullmatch(path.name) or SIMPLE_DAILY_RE.fullmatch(path.name)
        if match and match.group("symbol").upper() not in NON_OHLCV_STEMS:
            increment_files[match.group("symbol").upper()] = path

    records: dict[str, dict[str, object]] = {}
    for position, (symbol, base_path) in enumerate(sorted(daily_files.items()), 1):
        base = load_ohlcv(base_path)
        # Provider timestamps are commonly 07:00 local time; use an exclusive
        # next-day boundary so the requested calendar dates are inclusive.
        base_end_exclusive = base_end + pd.Timedelta(days=1)
        as_of_exclusive = as_of + pd.Timedelta(days=1)
        base = base.loc[base["time"] < base_end_exclusive]
        increment_path = increment_files.get(symbol)
        if increment_path is not None:
            increment = load_ohlcv(increment_path)
            increment = increment.loc[
                (increment["time"] >= base_end_exclusive)
                & (increment["time"] < as_of_exclusive)
            ]
            frame = pd.concat([base, increment], ignore_index=True)
        else:
            frame = base
        frame = frame.sort_values("time", kind="stable").drop_duplicates("time", keep="last").reset_index(drop=True)
        if frame.empty:
            continue
        target = output_dir / f"{symbol}.csv"
        write_csv(frame, target)
        records[symbol] = {
            "status": "ok",
            "rows": int(len(frame)),
            "min_time": frame["time"].min().isoformat(),
            "max_time": frame["time"].max().isoformat(),
            "path": str(target),
            "sha256": sha256(target),
        }
        if position % 100 == 0 or position == len(daily_files):
            print(f"Merged {position}/{len(daily_files)} symbols; ok={len(records)}", flush=True)

    market = load_ohlcv(args.market_base.resolve())
    market_increment = load_ohlcv(args.market_increment.resolve())
    market = pd.concat(
        [
            market.loc[market["time"] < base_end_exclusive],
            market_increment.loc[
                (market_increment["time"] >= base_end_exclusive)
                & (market_increment["time"] < as_of_exclusive)
            ],
        ],
        ignore_index=True,
    ).sort_values("time", kind="stable").drop_duplicates("time", keep="last").reset_index(drop=True)
    market_path = output_dir / "market" / "VNINDEX.csv"
    write_csv(market, market_path)

    industry_path = output_dir / "industry_map.csv"
    industry_path.write_bytes(args.industry.resolve().read_bytes())
    symbols_path = output_dir / "symbols.csv"
    pd.DataFrame({"symbol": sorted(records)}).to_csv(symbols_path, index=False)

    manifest = {
        "schema_version": 4,
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "requested_start": "2015-09-28",
        "requested_as_of_end": str(as_of.date()),
        "interval": "1D",
        "provider_package": "local_merged_daily_and_incremental_v6",
        "provider_route": "local CSV merge; no future rows beyond cutoff",
        "price_adjustment_policy": "adjusted",
        "price_value_multiplier": 1000.0,
        "ohlcv_schema": REQUIRED,
        "universe_symbols": len(daily_files),
        "successful_symbols": len(records),
        "failed_symbols": len(daily_files) - len(records),
        "coverage_ratio": len(records) / len(daily_files),
        "calendar_alignment_summary": {"source": "local merged snapshot; evaluated by trainer"},
        "vnindex": {"path": str(market_path), "sha256": sha256(market_path)},
        "industry_map": {"path": str(industry_path), "sha256": sha256(industry_path)},
        "equity_list": {"path": str(symbols_path), "sha256": sha256(symbols_path)},
        "symbols": records,
    }
    (output_dir / "snapshot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Created merged snapshot: {output_dir}")
    print(f"Symbols={len(records)}/{len(daily_files)}, market={market['time'].min().date()} -> {market['time'].max().date()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
