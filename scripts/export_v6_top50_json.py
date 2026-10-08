"""Export the hash-pinned long-term ensemble Top 50 as JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path, *, rows: int | None = None) -> dict[str, Any]:
    path = path.resolve()
    record: dict[str, Any] = {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }
    if rows is not None:
        record["rows"] = rows
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=Path("deploy/wave_v6_advisory/serving_release.json"))
    parser.add_argument("--output", type=Path, default=Path("deploy/wave_v6_advisory/top50.json"))
    args = parser.parse_args()

    release_path = _path(args.release)
    release = json.loads(release_path.read_text(encoding="utf-8"))
    output_record = release.get("prediction_output", {})
    prediction_path = _path(Path(str(output_record.get("path", ""))))
    if not prediction_path.is_file():
        raise FileNotFoundError(f"Prediction output is missing: {prediction_path}")
    expected_hash = str(output_record.get("sha256", "")).lower()
    if expected_hash and _sha256(prediction_path).lower() != expected_hash:
        raise ValueError("Prediction output hash does not match the serving release.")

    frame = pd.read_csv(prediction_path)
    required = {"time", "ticker", "rank", "p_ensemble"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Prediction output is missing columns: {missing}")
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce")
    frame["p_ensemble"] = pd.to_numeric(frame["p_ensemble"], errors="coerce")
    frame = frame.dropna(subset=["ticker", "rank", "p_ensemble"])
    frame = frame.sort_values(["rank", "ticker"], kind="stable").drop_duplicates("ticker")
    top50 = frame.head(50).copy()
    ranks = top50["rank"].astype(int).tolist()
    if len(top50) != 50 or len(set(top50["ticker"])) != 50 or ranks != list(range(1, 51)):
        raise ValueError("Serving output does not contain a complete rank-ordered Top 50.")

    symbols: list[dict[str, Any]] = []
    for row in top50.to_dict(orient="records"):
        item: dict[str, Any] = {
            "rank": int(row["rank"]),
            "ticker": row["ticker"],
            "date": str(row["time"])[:10],
            "p_ensemble": float(row["p_ensemble"]),
        }
        if pd.notna(row.get("model_agreement")):
            item["model_agreement"] = float(row["model_agreement"])
        symbols.append(item)

    payload = {
        "schema_version": 1,
        "release_id": release.get("release_id"),
        "release_kind": "long_term_ensemble_top50",
        "as_of_date": release.get("as_of_date"),
        "snapshot_date": release.get("snapshot_date"),
        "source_prediction_output": _record(prediction_path, rows=len(frame)),
        "symbols": symbols,
    }
    output = _path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
