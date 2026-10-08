"""Audit optional fundamental inputs before they can enter a training dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.features.fundamentals import validate_point_in_time_frame  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/processed/fundamentals")
    parser.add_argument("--output", type=Path, default=ROOT / "data/audits/fundamental_input_audit.json")
    args = parser.parse_args()
    files = sorted([*args.input_dir.glob("*.parquet"), *args.input_dir.glob("*.csv")]) if args.input_dir.exists() else []
    if not files:
        report = {"status": "blocked", "reason": "no_point_in_time_fundamental_files", "input_dir": str(args.input_dir), "files": []}
    else:
        reports = []
        for path in files:
            frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
            item = validate_point_in_time_frame(frame)
            item["file"] = str(path)
            reports.append(item)
        report = {"status": "pass" if all(item["status"] == "pass" for item in reports) else "blocked", "files": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["status"] == "blocked":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
