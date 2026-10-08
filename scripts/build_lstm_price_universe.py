"""Create a reproducible LSTM universe from a snapshot or a hash-pinned V6 ranking."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--size", type=int, default=50)
    parser.add_argument("--minimum-history", type=int, default=700)
    parser.add_argument("--output", type=Path, required=True, help="Explicit output path for the generated cohort manifest.")
    parser.add_argument("--v6-manifest", type=Path, help="Successful V6 daily manifest used to cover the dynamic Top-50 candidate universe.")
    parser.add_argument("--include-all-v6-ranked", action="store_true", help="Use every ranked V6 candidate, not merely its first --size entries.")
    args = parser.parse_args()
    if args.size < 1 or args.minimum_history < 1:
        raise ValueError("--size and --minimum-history must be positive.")
    snapshot = args.snapshot_dir if args.snapshot_dir.is_absolute() else ROOT / args.snapshot_dir
    manifest_path = snapshot / "snapshot_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    as_of_date = str(manifest.get("vnindex", {}).get("max_time", ""))[:10]
    if not as_of_date:
        market = snapshot / "market" / "VNINDEX.csv"
        if not market.is_file():
            raise RuntimeError("Snapshot manifest has no max_time and no readable VNINDEX market file.")
        dates = pd.to_datetime(pd.read_csv(market, usecols=["time"])["time"], errors="coerce").dropna()
        if dates.empty:
            raise RuntimeError("VNINDEX market file has no valid dates.")
        as_of_date = str(dates.max().date())
    v6_symbols: list[str] | None = None
    v6_record: dict[str, Any] | None = None
    if args.v6_manifest:
        v6_manifest_path = args.v6_manifest if args.v6_manifest.is_absolute() else ROOT / args.v6_manifest
        v6_manifest = json.loads(v6_manifest_path.read_text(encoding="utf-8"))
        record = v6_manifest.get("prediction_output", {})
        v6_output = Path(record.get("path", ""))
        if not v6_output.is_absolute():
            v6_output = ROOT / v6_output
        if (
            v6_manifest.get("pipeline") != "wave_v6_daily_inference"
            or v6_manifest.get("status") != "success"
            or v6_manifest.get("as_of_date") != as_of_date
            or not v6_output.is_file()
            or record.get("sha256") != _sha256(v6_output)
        ):
            raise RuntimeError("V6 manifest/output does not match the immutable snapshot date and hash.")
        ranked = pd.read_csv(v6_output, usecols=["ticker", "rank"])
        ranked["ticker"] = ranked["ticker"].astype(str).str.strip().str.upper()
        ranked["rank"] = pd.to_numeric(ranked["rank"], errors="coerce")
        ranked = ranked.dropna().sort_values(["rank", "ticker"], kind="stable").drop_duplicates("ticker")
        if ranked.empty or ranked["rank"].astype(int).iloc[0] != 1:
            raise RuntimeError("V6 ranking has no valid rank-1 candidate.")
        v6_symbols = ranked["ticker"].tolist()
        v6_record = {"manifest_path": str(v6_manifest_path.relative_to(ROOT)).replace("\\", "/"), "manifest_sha256": _sha256(v6_manifest_path), "prediction_output": {"path": str(v6_output.relative_to(ROOT)).replace("\\", "/"), "sha256": _sha256(v6_output)}}
    candidates: list[dict[str, Any]] = []
    for symbol, record in manifest.get("symbols", {}).items():
        if not isinstance(record, dict) or record.get("status") != "ok":
            continue
        source = snapshot / f"{symbol}.csv"
        if not source.is_file() or record.get("sha256") != _sha256(source):
            continue
        frame = pd.read_csv(source, usecols=["time", "close", "volume"])
        frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
        frame = frame.dropna().sort_values("time")
        if len(frame) < args.minimum_history or str(frame["time"].iloc[-1].date()) != as_of_date:
            continue
        last = frame.iloc[-1]
        candidates.append({"ticker": str(symbol).upper(), "traded_value": float(last.close * last.volume)})
    if v6_symbols is None:
        candidates.sort(key=lambda item: (-item["traded_value"], item["ticker"]))
    else:
        candidate_by_symbol = {item["ticker"]: item for item in candidates}
        candidates = [candidate_by_symbol[symbol] for symbol in v6_symbols if symbol in candidate_by_symbol]
    needed = len(candidates) if args.include_all_v6_ranked and v6_symbols is not None else args.size
    if len(candidates) < needed:
        raise RuntimeError(f"Only {len(candidates)} current symbols meet the history gate; need {needed}.")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    payload = {
        "schema_version": 2,
        "selection": "v6_ranked_candidate_coverage" if v6_symbols is not None else "latest_close_times_volume",
        "snapshot_manifest": {"path": str(manifest_path.relative_to(ROOT)).replace("\\", "/"), "sha256": _sha256(manifest_path)},
        "as_of_date": as_of_date,
        "symbols": [row["ticker"] for row in candidates[:needed]],
    }
    if v6_record is not None:
        payload["source_v6"] = v6_record
    _write_json(output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
