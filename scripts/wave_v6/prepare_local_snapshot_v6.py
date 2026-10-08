"""Create a V6 training snapshot from the local ``data/vnstock`` layout.

The source files are never changed.  Normalised V6 CSVs, manifest, market
index and industry map are written to a distinct output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd

from v6_data_adapter import normalise_ohlcv


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        frame.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json_atomic(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _ticker_from_filename(path: Path) -> str | None:
    match = re.fullmatch(r"([A-Za-z0-9]+)_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}_1D", path.stem)
    return match.group(1).upper() if match else None


def _industry_map(path: Path, level: int) -> pd.DataFrame:
    raw = pd.read_csv(path)
    required = {"symbol", "icb_level", "icb_code", "icb_name"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{path} lacks industry columns: {sorted(missing)}")
    selected = raw.loc[pd.to_numeric(raw["icb_level"], errors="coerce").eq(level)].copy()
    selected["symbol"] = selected["symbol"].astype(str).str.strip().str.upper()
    selected = selected.drop_duplicates("symbol", keep="last")
    return pd.DataFrame(
        {
            "symbol": selected["symbol"],
            "industry_code": selected["icb_code"],
            "industry_name": selected["icb_name"],
            "industry_level": level,
            "company_name": selected.get("organ_name", pd.Series(pd.NA, index=selected.index)),
        }
    ).sort_values("symbol").reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/vnstock/daily"))
    parser.add_argument("--reference-dir", type=Path, default=Path("data/vnstock/reference"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/vnstock/v6_snapshot"))
    parser.add_argument("--icb-level", type=int, default=2)
    parser.add_argument(
        "--price-policy",
        choices=("raw", "adjusted"),
        required=True,
        help="Price-adjustment convention confirmed for every source OHLCV file.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    reference_dir = args.reference_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not source_dir.is_dir() or not reference_dir.is_dir():
        raise FileNotFoundError("--source-dir and --reference-dir must be existing directories")
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite non-empty snapshot: {output_dir}")

    source_files = sorted(source_dir.glob("*.csv"))
    sources = [(ticker, path) for path in source_files if (ticker := _ticker_from_filename(path))]
    if not sources:
        raise RuntimeError(f"No daily OHLCV files found in {source_dir}")

    market_source = reference_dir / "vnindex_ohlcv_1d.csv"
    industry_source = reference_dir / "industry_map_icb.csv"
    if not market_source.is_file() or not industry_source.is_file():
        raise FileNotFoundError("Expected vnindex_ohlcv_1d.csv and industry_map_icb.csv in --reference-dir")

    market = normalise_ohlcv(pd.read_csv(market_source), endpoint=str(market_source))
    market_path = output_dir / "market" / "VNINDEX.csv"
    _write_csv_atomic(market, market_path)
    industries = _industry_map(industry_source, args.icb_level)
    industry_path = output_dir / "industry_map.csv"
    _write_csv_atomic(industries, industry_path)

    records: dict[str, dict[str, object]] = {}
    for position, (ticker, source) in enumerate(sources, 1):
        target = output_dir / f"{ticker}.csv"
        try:
            frame = normalise_ohlcv(pd.read_csv(source), endpoint=str(source))
            _write_csv_atomic(frame, target)
            records[ticker] = {
                "status": "ok",
                "rows": int(len(frame)),
                "min_time": frame["time"].min().isoformat(),
                "max_time": frame["time"].max().isoformat(),
                "path": str(target),
                "sha256": _sha256(target),
            }
        except Exception as exc:
            records[ticker] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        if position % 100 == 0 or position == len(sources):
            successful = sum(item["status"] == "ok" for item in records.values())
            print(f"Prepared {position}/{len(sources)} symbols; ok={successful}; errors={position-successful}")

    successful_symbols = sorted(ticker for ticker, item in records.items() if item["status"] == "ok")
    symbols_path = output_dir / "symbols.csv"
    _write_csv_atomic(pd.DataFrame({"symbol": successful_symbols}), symbols_path)
    latest_stock_date = max(pd.Timestamp(records[ticker]["max_time"]) for ticker in successful_symbols)
    manifest: dict[str, object] = {
        "schema_version": 4,
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "requested_start": str(min(pd.Timestamp(records[ticker]["min_time"]).date() for ticker in successful_symbols)),
        "requested_as_of_end": str(latest_stock_date.date()),
        "interval": "1D",
        "provider_package": "local_vnstock_export",
        "provider_route": "local data/vnstock/daily conversion; no remote download",
        "price_adjustment_policy": args.price_policy,
        "price_value_multiplier": 1000.0,
        "ohlcv_schema": ["time", "open", "high", "low", "close", "volume"],
        "universe_symbols": len(sources),
        "successful_symbols": len(successful_symbols),
        "failed_symbols": len(sources) - len(successful_symbols),
        "coverage_ratio": len(successful_symbols) / len(sources),
        "calendar_alignment_summary": {"source": "evaluated by trainer"},
        "vnindex": {"path": str(market_path), "sha256": _sha256(market_path)},
        "industry_map": {"path": str(industry_path), "sha256": _sha256(industry_path)},
        "equity_list": {"path": str(symbols_path), "sha256": _sha256(symbols_path)},
        "symbols": records,
    }
    _write_json_atomic(manifest, output_dir / "snapshot_manifest.json")
    print(f"Created local V6 snapshot: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
