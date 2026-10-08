"""Audit a local V6 OHLCV snapshot without changing source files.

The report distinguishes structural errors from large price jumps.  A jump is
reported for review and is not silently deleted: downstream feature/label
builders must quarantine its historical window according to the selected
corporate-action policy.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REQUIRED = ("time", "open", "high", "low", "close", "volume")
PRICE = ("open", "high", "low", "close")


def _audit_file(path: Path, market_calendar: pd.DatetimeIndex, jump_threshold: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = pd.read_csv(path)
    missing = sorted(set(REQUIRED).difference(raw.columns))
    if missing:
        return {
            "symbol": path.stem,
            "status": "schema_error",
            "rows_raw": int(len(raw)),
            "missing_columns": missing,
        }, []

    frame = raw.loc[:, REQUIRED].copy()
    dates = pd.to_datetime(frame["time"], errors="coerce").dt.normalize()
    numeric = frame.loc[:, REQUIRED[1:]].apply(pd.to_numeric, errors="coerce")
    invalid_date = dates.isna()
    missing_numeric = numeric.isna().any(axis=1)
    non_finite = numeric.apply(np.isfinite).all(axis=1).eq(False) & ~missing_numeric
    non_positive = numeric.loc[:, PRICE].le(0).any(axis=1)
    negative_volume = numeric["volume"].lt(0)
    inconsistent = numeric["high"].lt(numeric.loc[:, ("open", "low", "close")].max(axis=1)) | numeric["low"].gt(
        numeric.loc[:, ("open", "high", "close")].min(axis=1)
    )
    valid = ~(invalid_date | missing_numeric | non_finite | non_positive | negative_volume | inconsistent)
    duplicate = dates[valid].duplicated(keep="last")
    clean = pd.DataFrame({"date": dates[valid], "close": numeric.loc[valid, "close"], "volume": numeric.loc[valid, "volume"]})
    clean = clean.loc[~duplicate.to_numpy()].drop_duplicates("date", keep="last").sort_values("date")
    returns = clean["close"].pct_change(fill_method=None)
    jump_mask = returns.abs().gt(jump_threshold)
    jump_rows: list[dict[str, Any]] = []
    for index in clean.index[jump_mask.fillna(False)]:
        position = clean.index.get_loc(index)
        previous = clean.iloc[position - 1]
        current = clean.loc[index]
        jump_rows.append(
            {
                "symbol": path.stem,
                "date": pd.Timestamp(current["date"]).date().isoformat(),
                "previous_date": pd.Timestamp(previous["date"]).date().isoformat(),
                "return": float(returns.loc[index]),
                "previous_close": float(previous["close"]),
                "close": float(current["close"]),
            }
        )
    active_calendar = market_calendar[(market_calendar >= clean["date"].min()) & (market_calendar <= clean["date"].max())] if len(clean) else pd.DatetimeIndex([])
    coverage = len(clean) / len(active_calendar) if len(active_calendar) else 0.0
    counts = Counter()
    counts["invalid_or_missing_date"] = int(invalid_date.sum())
    counts["missing_or_non_numeric_ohlcv"] = int(missing_numeric.sum())
    counts["non_finite_ohlcv"] = int(non_finite.sum())
    counts["non_positive_price"] = int(non_positive.sum())
    counts["negative_volume"] = int(negative_volume.sum())
    counts["inconsistent_ohlc"] = int(inconsistent.sum())
    counts["duplicate_timestamp"] = int(duplicate.sum())
    return {
        "symbol": path.stem,
        "status": "ok",
        "rows_raw": int(len(raw)),
        "rows_valid_unique": int(len(clean)),
        "first_date": pd.Timestamp(clean["date"].min()).date().isoformat() if len(clean) else None,
        "last_date": pd.Timestamp(clean["date"].max()).date().isoformat() if len(clean) else None,
        "calendar_coverage": float(coverage),
        "zero_volume_rate": float(clean["volume"].eq(0).mean()) if len(clean) else 1.0,
        "jump_count": int(jump_mask.sum()),
        "jump_count_gt_50pct": int(returns.abs().gt(0.50).sum()),
        "invalid_counts": dict(counts),
    }, jump_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jump-threshold", type=float, default=0.30)
    args = parser.parse_args()

    snapshot = args.snapshot_dir.resolve()
    output = args.output_dir.resolve()
    manifest_path = snapshot / "snapshot_manifest.json"
    market_path = snapshot / "market" / "VNINDEX.csv"
    if not manifest_path.is_file() or not market_path.is_file():
        raise FileNotFoundError("Snapshot must contain snapshot_manifest.json and market/VNINDEX.csv")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    market = pd.read_csv(market_path, usecols=["time"])
    calendar = pd.DatetimeIndex(pd.to_datetime(market["time"], errors="coerce").dropna().dt.normalize().unique()).sort_values()
    reports: list[dict[str, Any]] = []
    jumps: list[dict[str, Any]] = []
    ignored_files: list[str] = []
    for path in sorted(snapshot.glob("*.csv")):
        # The snapshot root also contains supporting symbol/industry tables;
        # they are not OHLCV sources and must not be reported as schema errors.
        if path.name in {"symbols.csv", "industry_map.csv"}:
            ignored_files.append(path.name)
            continue
        report, events = _audit_file(path, calendar, args.jump_threshold)
        reports.append(report)
        jumps.extend(events)

    output.mkdir(parents=True, exist_ok=True)
    symbols = pd.DataFrame(reports)
    symbols.to_csv(output / "symbol_quality.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(jumps).to_csv(output / "jump_events.csv", index=False, encoding="utf-8-sig")
    invalid_totals: Counter[str] = Counter()
    for report in reports:
        invalid_totals.update(report.get("invalid_counts", {}))
    policy = manifest.get("price_adjustment_policy")
    status = "pass" if policy in {"raw", "adjusted"} and not any(report.get("status") == "schema_error" for report in reports) else "fail"
    summary = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "snapshot_dir": str(snapshot),
        "manifest_price_adjustment_policy": policy,
        "status": status,
        "gate_failures": (["price_adjustment_policy_unverified"] if policy not in {"raw", "adjusted"} else [])
        + (["schema_error"] if any(report.get("status") == "schema_error" for report in reports) else []),
        "symbols_audited": int(len(reports)),
        "ignored_support_files": ignored_files,
        "symbols_schema_error": int(sum(report.get("status") == "schema_error" for report in reports)),
        "rows_raw": int(sum(report.get("rows_raw", 0) for report in reports)),
        "invalid_counts": dict(invalid_totals),
        "symbols_coverage_lt_80pct": int(symbols.loc[symbols["status"].eq("ok"), "calendar_coverage"].lt(0.80).sum()),
        "symbols_coverage_lt_95pct": int(symbols.loc[symbols["status"].eq("ok"), "calendar_coverage"].lt(0.95).sum()),
        "symbols_with_jump": int(symbols.loc[symbols["status"].eq("ok"), "jump_count"].gt(0).sum()),
        "jump_events_gt_threshold": int(len(jumps)),
        "jump_events_gt_50pct": int(sum(report.get("jump_count_gt_50pct", 0) for report in reports)),
        "source_manifest": str(manifest_path),
    }
    (output / "snapshot_quality_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
