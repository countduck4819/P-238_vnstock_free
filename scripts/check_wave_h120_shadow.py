"""Validate the latest daily H120 shadow run for scheduler health checks."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_manifest(run_root: Path) -> Path:
    candidates = sorted(
        (path for path in run_root.glob("*/orchestration_manifest.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"No orchestration manifests found in {run_root}")
    for path in candidates:
        try:
            if read_json(path).get("status") == "success":
                return path
        except (OSError, json.JSONDecodeError):
            continue
    raise RuntimeError("No successful shadow orchestration manifest found")


def check(manifest_path: Path, *, max_age_hours: float) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    if manifest.get("status") != "success":
        raise RuntimeError(f"Latest shadow run is not successful: {manifest.get('status')}")
    if manifest.get("trade_authorized") is not False:
        raise RuntimeError("Shadow health check refuses a trade-authorized run.")
    finished = datetime.fromisoformat(manifest["finished_at_utc"])
    age_hours = (datetime.now(UTC) - finished).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        raise RuntimeError(f"Latest shadow run is stale: age={age_hours:.2f}h")
    prediction_summary = manifest.get("predictions", {}).get("summary", {})
    if int(prediction_summary.get("shortlist_rows", 0)) != 10:
        raise RuntimeError("Latest shadow run did not produce the frozen Top-10 shortlist.")
    return {
        "status": "healthy",
        "manifest": str(manifest_path.relative_to(ROOT).as_posix()),
        "run_id": manifest.get("run_id"),
        "as_of_date": manifest.get("as_of_date"),
        "age_hours": round(age_hours, 3),
        "eligible_rows": prediction_summary.get("eligible_rows"),
        "shortlist_rows": prediction_summary.get("shortlist_rows"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=Path("runs/wave_h120_shadow"))
    parser.add_argument("--max-age-hours", type=float, default=30.0)
    args = parser.parse_args(argv)
    result = check(latest_manifest(args.run_root.resolve()), max_age_hours=args.max_age_hours)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
