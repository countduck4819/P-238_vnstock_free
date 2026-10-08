"""Build audited, training-ready OHLCV inputs for the Wave Ignition pipeline.

The default input is the cleaned ``data/vnstock/v6_snapshot`` layout. The
legacy ``daily`` layout remains available explicitly. Invalid and removed
observations are written to CSV audit logs so every filtering decision can be
reproduced.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_OHLCV = ("time", "open", "high", "low", "close", "volume")
PRICE_COLUMNS = ("open", "high", "low", "close")
SYMBOL_FILE_PATTERN = re.compile(r"^(?P<symbol>[^_]+)_.*\.csv$", re.IGNORECASE)
AUDIT_COLUMNS = (
    "symbol",
    "date",
    "source_file",
    "row_number",
    "reason",
    "detail",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-layout",
        choices=("daily", "v6_snapshot"),
        default="v6_snapshot",
        help="Input layout to clean; v6_snapshot is the active clean-data lineage.",
    )
    parser.add_argument("--stock-dir", type=Path, default=Path("data/vnstock/daily"))
    parser.add_argument("--snapshot-dir", type=Path, default=Path("data/vnstock/v6_snapshot"))
    parser.add_argument(
        "--vnindex-file",
        type=Path,
        default=Path("data/vnstock/reference/vnindex_ohlcv_1d.csv"),
    )
    parser.add_argument(
        "--industry-file",
        type=Path,
        default=Path("data/vnstock/reference/industry_map_icb.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/wave_ignition"),
    )
    parser.add_argument(
        "--price-policy",
        choices=("raw", "adjusted"),
        required=True,
        help="Price-adjustment convention confirmed for every stock and market OHLCV source.",
    )
    return parser.parse_args()


def audit_record(
    row: pd.Series,
    *,
    symbol: str,
    source_file: str,
    reason: str,
    detail: str = "",
) -> dict[str, Any]:
    parsed_time = row.get("_date")
    date_value = "" if pd.isna(parsed_time) else pd.Timestamp(parsed_time).date().isoformat()
    return {
        "symbol": symbol,
        "date": date_value,
        "source_file": source_file,
        "row_number": int(row.get("_row_number", 0)),
        "reason": reason,
        "detail": detail,
        **{column: row.get(column, "") for column in (*PRICE_COLUMNS, "volume")},
    }


def load_and_validate_ohlcv(
    path: Path,
    symbol: str,
) -> tuple[pd.DataFrame, list[dict[str, Any]], Counter[str], int]:
    raw = pd.read_csv(path)
    missing_columns = [column for column in REQUIRED_OHLCV if column not in raw.columns]
    if missing_columns:
        raise ValueError(f"missing columns: {', '.join(missing_columns)}")

    frame = raw.loc[:, REQUIRED_OHLCV].copy()
    frame["_row_number"] = range(2, len(frame) + 2)
    frame["_date"] = pd.to_datetime(frame["time"], errors="coerce").dt.normalize()
    for column in (*PRICE_COLUMNS, "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    audit: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    invalid = pd.Series(False, index=frame.index)

    def flag(mask: pd.Series, reason: str, detail: str = "") -> None:
        nonlocal invalid
        mask = mask.fillna(False)
        invalid |= mask
        counts[reason] += int(mask.sum())
        for _, row in frame.loc[mask].iterrows():
            audit.append(
                audit_record(
                    row,
                    symbol=symbol,
                    source_file=path.name,
                    reason=reason,
                    detail=detail,
                )
            )

    flag(frame["_date"].isna(), "invalid_or_missing_date")
    numeric = frame.loc[:, (*PRICE_COLUMNS, "volume")]
    flag(numeric.isna().any(axis=1), "missing_or_non_numeric_ohlcv")
    finite = numeric.apply(lambda column: column.map(np.isfinite))
    flag(~finite.all(axis=1) & numeric.notna().all(axis=1), "non_finite_ohlcv")
    flag((frame.loc[:, PRICE_COLUMNS] <= 0).any(axis=1), "non_positive_price")
    flag(frame["volume"] < 0, "negative_volume")

    high_invalid = frame["high"] < frame.loc[:, ("open", "low", "close")].max(axis=1)
    low_invalid = frame["low"] > frame.loc[:, ("open", "high", "close")].min(axis=1)
    flag(high_invalid | low_invalid, "inconsistent_ohlc")

    valid = frame.loc[~invalid].copy()
    duplicate_mask = valid.duplicated("_date", keep="last")
    for _, row in valid.loc[duplicate_mask].iterrows():
        same_date = valid.loc[valid["_date"].eq(row["_date"]), (*PRICE_COLUMNS, "volume")]
        reason = "duplicate_exact" if len(same_date.drop_duplicates()) == 1 else "duplicate_conflict"
        counts[reason] += 1
        audit.append(
            audit_record(
                row,
                symbol=symbol,
                source_file=path.name,
                reason=reason,
                detail="kept the last valid source row for this symbol/date",
            )
        )
    valid = valid.loc[~duplicate_mask].sort_values("_date", kind="stable")
    return valid, audit, counts, len(raw)


def build_industry_map(
    path: Path,
) -> tuple[pd.DataFrame, set[str], list[dict[str, str]]]:
    raw = pd.read_csv(path, dtype=str)
    snapshot_columns = {"symbol", "industry_code", "industry_name", "industry_level"}
    if snapshot_columns.issubset(raw.columns):
        raw = raw.rename(
            columns={
                "industry_code": "icb_code",
                "industry_name": "icb_name",
                "industry_level": "icb_level",
            }
        )
    required = {"symbol", "icb_level", "icb_code", "icb_name"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"Industry map missing columns: {', '.join(missing)}")

    frame = raw.copy()
    frame["symbol"] = frame["symbol"].str.strip().str.upper()
    frame["icb_level"] = pd.to_numeric(frame["icb_level"], errors="coerce").astype("Int64")
    frame = frame.dropna(subset=["symbol", "icb_level", "icb_code", "icb_name"])
    frame = frame.loc[frame["icb_level"].between(1, 4)].drop_duplicates()

    conflicts: set[str] = set()
    conflict_audit: list[dict[str, str]] = []
    for (symbol, level), group in frame.groupby(["symbol", "icb_level"], sort=True):
        assignments = group.loc[:, ["icb_code", "icb_name"]].drop_duplicates()
        if len(assignments) <= 1:
            continue
        conflicts.add(symbol)
        values = assignments.astype(str).agg(": ".join, axis=1).tolist()
        conflict_audit.append(
            {
                "symbol": symbol,
                "reason": "conflicting_industry_mapping",
                "detail": f"ICB level {level}: {' | '.join(values)}",
            }
        )

    unambiguous = (
        frame.loc[
            ~frame["symbol"].isin(conflicts),
            ["symbol", "icb_level", "icb_code", "icb_name"],
        ]
        .drop_duplicates()
        .copy()
    )
    codes = unambiguous.pivot(index="symbol", columns="icb_level", values="icb_code")
    names = unambiguous.pivot(index="symbol", columns="icb_level", values="icb_name")
    codes.columns = [f"icb_level_{level}_code" for level in codes.columns]
    names.columns = [f"icb_level_{level}_name" for level in names.columns]
    mapping = codes.join(names).reset_index()
    ordered = ["symbol"]
    for level in range(1, 5):
        ordered.extend([f"icb_level_{level}_code", f"icb_level_{level}_name"])
    mapping = mapping.reindex(columns=ordered).sort_values("symbol", kind="stable")
    return mapping, conflicts, conflict_audit


def save_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def main() -> None:
    args = parse_args()
    if args.input_layout == "v6_snapshot":
        snapshot_dir = args.snapshot_dir
        stock_dir = snapshot_dir
        vnindex_file = snapshot_dir / "market" / "VNINDEX.csv"
        industry_file = snapshot_dir / "industry_map.csv"
    else:
        stock_dir = args.stock_dir
        vnindex_file = args.vnindex_file
        industry_file = args.industry_file

    stock_output_dir = args.output_dir / "stock_ohlcv"
    audit_dir = args.output_dir / "audit"
    stock_output_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    industry_map, industry_conflicts, excluded_symbols = build_industry_map(
        industry_file
    )
    industry_symbols = set(industry_map["symbol"])

    vnindex, vnindex_audit, vnindex_counts, _ = load_and_validate_ohlcv(
        vnindex_file, "VNINDEX"
    )
    if vnindex.empty:
        raise RuntimeError("No valid VNINDEX observations remain after validation.")
    market_dates = pd.DatetimeIndex(vnindex["_date"])
    market_date_set = set(market_dates)
    vnindex_clean = vnindex.rename(columns={"_date": "date"}).loc[
        :, ("date", *PRICE_COLUMNS, "volume")
    ]
    vnindex_clean["date"] = vnindex_clean["date"].dt.date.astype(str)
    save_csv(vnindex_clean, args.output_dir / "vnindex_ohlcv_1d.csv")

    all_audit = list(vnindex_audit)
    missing_sessions: list[dict[str, str]] = []
    ignored_inputs: list[dict[str, str]] = []
    reason_counts = Counter(vnindex_counts)
    total_input_rows = 0
    total_output_rows = 0
    processed_symbols = 0

    for path in sorted(stock_dir.glob("*.csv")):
        if args.input_layout == "v6_snapshot":
            if path.name.lower() in {"symbols.csv", "industry_map.csv"}:
                ignored_inputs.append(
                    {
                        "source_file": path.name,
                        "reason": "snapshot_metadata_file",
                    }
                )
                continue
            symbol = path.stem.strip().upper()
            match = True
        else:
            match = SYMBOL_FILE_PATTERN.match(path.name)
            symbol = match.group("symbol").strip().upper() if match is not None else ""

        if not match or (args.input_layout == "daily" and not path.name.lower().endswith("_1d.csv")):
            ignored_inputs.append(
                {
                    "source_file": path.name,
                    "reason": "filename_not_stock_ohlcv_pattern",
                }
            )
            continue
        try:
            frame, audit, counts, raw_row_count = load_and_validate_ohlcv(path, symbol)
        except Exception as exc:
            excluded_symbols.append(
                {"symbol": symbol, "reason": "unreadable_stock_file", "detail": str(exc)}
            )
            continue

        total_input_rows += raw_row_count
        all_audit.extend(audit)
        reason_counts.update(counts)

        if symbol in industry_conflicts or symbol not in industry_symbols:
            reason = (
                "conflicting_industry_mapping"
                if symbol in industry_conflicts
                else "missing_industry_mapping"
            )
            if symbol not in industry_conflicts:
                excluded_symbols.append({"symbol": symbol, "reason": reason, "detail": ""})
            reason_counts[reason] += len(frame)
            for _, row in frame.iterrows():
                all_audit.append(
                    audit_record(
                        row,
                        symbol=symbol,
                        source_file=path.name,
                        reason=reason,
                    )
                )
            continue

        outside_calendar = ~frame["_date"].isin(market_date_set)
        reason_counts["date_not_in_vnindex_calendar"] += int(outside_calendar.sum())
        for _, row in frame.loc[outside_calendar].iterrows():
            all_audit.append(
                audit_record(
                    row,
                    symbol=symbol,
                    source_file=path.name,
                    reason="date_not_in_vnindex_calendar",
                )
            )
        frame = frame.loc[~outside_calendar].copy()
        if frame.empty:
            excluded_symbols.append(
                {
                    "symbol": symbol,
                    "reason": "no_valid_synchronized_rows",
                    "detail": "No observations remained after data-quality checks.",
                }
            )
            continue

        observed_dates = set(frame["_date"])
        active_market_dates = market_dates[
            (market_dates >= frame["_date"].min()) & (market_dates <= frame["_date"].max())
        ]
        for missing_date in active_market_dates.difference(pd.DatetimeIndex(observed_dates)):
            missing_sessions.append(
                {
                    "symbol": symbol,
                    "date": missing_date.date().isoformat(),
                    "reason": "missing_stock_session_within_observed_span",
                }
            )

        clean = frame.rename(columns={"_date": "date"}).loc[
            :, ("date", *PRICE_COLUMNS, "volume")
        ]
        clean.insert(0, "symbol", symbol)
        clean["date"] = clean["date"].dt.date.astype(str)
        save_csv(clean, stock_output_dir / f"{symbol}.csv")
        processed_symbols += 1
        total_output_rows += len(clean)

    used_symbols = {path.stem for path in stock_output_dir.glob("*.csv")}
    training_industry_map = industry_map.loc[industry_map["symbol"].isin(used_symbols)]
    save_csv(training_industry_map, args.output_dir / "industry_map_icb.csv")
    save_csv(pd.DataFrame(all_audit, columns=AUDIT_COLUMNS), audit_dir / "excluded_rows.csv")
    save_csv(
        pd.DataFrame(excluded_symbols, columns=("symbol", "reason", "detail")),
        audit_dir / "excluded_symbols.csv",
    )
    save_csv(
        pd.DataFrame(missing_sessions, columns=("symbol", "date", "reason")),
        audit_dir / "missing_sessions.csv",
    )
    save_csv(
        pd.DataFrame(ignored_inputs, columns=("source_file", "reason")),
        audit_dir / "ignored_inputs.csv",
    )

    latest_stock_date = ""
    if total_output_rows:
        latest_stock_date = max(
            pd.read_csv(path, usecols=["date"])["date"].max()
            for path in stock_output_dir.glob("*.csv")
        )
    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "stock_source": str(stock_dir.resolve()),
        "stock_source_policy": (
            "cleaned V6 snapshot layout"
            if args.input_layout == "v6_snapshot"
            else "daily only; daily_full_vci is not read"
        ),
        "price_adjustment_policy": args.price_policy,
        "industry_mapping_policy": "static current ICB snapshot; ambiguous symbols excluded",
        "market_calendar_policy": "stock dates must exist in cleaned VNINDEX calendar",
        "duplicate_policy": "keep last valid source row per symbol/date",
        "missing_session_policy": "audit only; do not impute OHLCV",
        "processed_stock_symbols": processed_symbols,
        "excluded_symbol_records": len(excluded_symbols),
        "input_stock_rows": total_input_rows,
        "output_stock_rows": total_output_rows,
        "excluded_row_audit_records": len(all_audit),
        "missing_session_records": len(missing_sessions),
        "vnindex_rows": len(vnindex_clean),
        "vnindex_first_date": vnindex_clean["date"].min(),
        "vnindex_last_date": vnindex_clean["date"].max(),
        "latest_stock_date": latest_stock_date,
        "reason_counts": dict(sorted(reason_counts.items())),
    }
    (audit_dir / "quality_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
