"""Run the short-term daily scoring job.

Long-term ranking and LSTM price forecasts are served from their reviewed
cohort release and are intentionally not retrained or rescored by this job.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _run(name: str, command: list[str], manifest: dict[str, Any]) -> int:
    started = datetime.now(UTC)
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=14_400)
    manifest["steps"].append({
        "name": name,
        "return_code": completed.returncode,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "stdout_tail": completed.stdout[-4_000:],
        "stderr_tail": completed.stderr[-4_000:],
    })
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-date", default=datetime.now(VIETNAM_TZ).date().isoformat())
    parser.add_argument("--orchestration-root", type=Path, default=Path("runs/daily_model_scoring"))
    parser.add_argument("--skip-sync", action="store_true", help="Replay an existing short-term snapshot only.")
    parser.add_argument("--allow-stale-cache", action="store_true", help="Only for historical replay/testing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot_date = args.snapshot_date
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ROOT / args.orchestration_root / f"{snapshot_date}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "pipeline": "daily_independent_advisory_scoring",
        "run_id": run_id,
        "snapshot_date": snapshot_date,
        "status": "running",
        "trade_authorized": False,
        "models": {
            "short_term": {"implementation": "wave_h120", "daily_inference": True},
            "long_term": {"implementation": "wave_v6", "daily_inference": False},
        },
        "steps": [],
        "started_at_utc": datetime.now(UTC).isoformat(),
    }
    manifest_path = run_dir / "orchestration_manifest.json"
    _write_json(manifest_path, manifest)
    h120_command = [sys.executable, "scripts/run_wave_h120_shadow.py", "--snapshot-date", snapshot_date]
    if args.skip_sync:
        h120_command.append("--skip-sync")
    if args.allow_stale_cache:
        # The normal daily path keeps H120's strict freshness gate.  A
        # historical replay intentionally relaxes only that gate; it still
        # validates snapshot hashes and feature/output contracts.
        h120_command.extend(["--max-staleness-days", "36500"])
    try:
        h120_code = _run("h120_snapshot_and_inference", h120_command, manifest)
        manifest["models"]["short_term"].update({"status": "success" if h120_code == 0 else "failed"})
        manifest["models"]["long_term"].update({
            "status": "frozen_not_run",
            "reason": "Long-term ranking and LSTM price forecasts are refreshed by the cohort release process, not daily scoring.",
        })
        manifest["status"] = "success" if h120_code == 0 else "failed"
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        manifest["finished_at_utc"] = datetime.now(UTC).isoformat()
        _write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
