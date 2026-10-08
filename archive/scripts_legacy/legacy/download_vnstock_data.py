"""Download historical stock prices from Vnstock and save them as CSV."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
import time

try:
    from vnstock_data import Listing, Quote
except ImportError:
    from vnstock import Listing, Quote


def parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(
        description="Download historical stock-price data from Vnstock."
    )
    parser.add_argument("--symbol", default="FPT", help="Stock symbol (default: FPT)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download every stock listed by Vnstock (HOSE, HNX and UPCOM)",
    )
    parser.add_argument(
        "--start",
        default=(today - timedelta(days=365)).isoformat(),
        help="Start date in YYYY-MM-DD format (default: one year ago)",
    )
    parser.add_argument(
        "--end",
        default=today.isoformat(),
        help="End date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--interval",
        default="1D",
        choices=("1m", "5m", "15m", "30m", "1H", "1D", "1W", "1M"),
        help="Candle interval (default: 1D)",
    )
    parser.add_argument(
        "--source",
        default="KBS",
        help="Vnstock data source (default: KBS)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/vnstock"),
        help="Directory for downloaded CSV files (default: data/vnstock)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip non-empty output files that have already been downloaded",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Delay between API calls in seconds (default: 0.25)",
    )
    return parser.parse_args()


def download_symbol(
    symbol: str,
    start: date,
    end: date,
    interval: str,
    source: str,
    output_dir: Path,
    resume: bool,
) -> tuple[str, int]:
    output = output_dir / f"{symbol}_{start}_{end}_{interval}.csv"
    if resume and output.exists() and output.stat().st_size > 0:
        return "skipped", 0

    dataframe = Quote(source=source.lower(), symbol=symbol).history(
        start=start.isoformat(), end=end.isoformat(), interval=interval
    )
    if dataframe.empty:
        return "empty", 0

    dataframe.to_csv(output, index=False, encoding="utf-8-sig")
    return "downloaded", len(dataframe)


def main() -> None:
    args = parse_args()

    # Validate dates early so input errors produce a clear message.
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        raise ValueError("--start must be earlier than or equal to --end")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.all:
        listing = Listing(source=args.source.lower()).symbols_by_exchange()
        symbols = sorted(
            listing.loc[
                listing["type"].astype(str).str.casefold().eq("stock"), "symbol"
            ]
            .dropna()
            .unique()
        )
    else:
        symbols = [args.symbol.strip().upper()]

    failures: list[tuple[str, str]] = []
    downloaded = skipped = empty = total_rows = 0
    for index, symbol in enumerate(symbols, start=1):
        try:
            status, rows = download_symbol(
                symbol,
                start,
                end,
                args.interval,
                args.source,
                args.output_dir,
                args.resume,
            )
            downloaded += status == "downloaded"
            skipped += status == "skipped"
            empty += status == "empty"
            total_rows += rows
            print(
                f"[{index}/{len(symbols)}] {symbol}: {status} ({rows:,} rows)",
                flush=True,
            )
        except Exception as exc:  # Continue so one bad symbol does not stop the batch.
            failures.append((symbol, str(exc)))
            print(f"[{index}/{len(symbols)}] {symbol}: ERROR - {exc}", flush=True)
        if index < len(symbols) and args.delay > 0:
            time.sleep(args.delay)

    if failures:
        error_file = args.output_dir / "download_errors.csv"
        with error_file.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(("symbol", "error"))
            writer.writerows(failures)

    print(
        f"Finished: {downloaded} downloaded, {skipped} skipped, {empty} empty, "
        f"{len(failures)} failed, {total_rows:,} rows.",
        flush=True,
    )
    print(f"Output directory: {args.output_dir.resolve()}", flush=True)


if __name__ == "__main__":
    main()
