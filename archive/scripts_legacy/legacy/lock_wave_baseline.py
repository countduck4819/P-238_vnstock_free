"""Create an immutable manifest for the current wave-model baseline.

The lock records hashes rather than copying large parquet/model artifacts.  It
is intentionally additive: an existing lock is never overwritten unless the
caller explicitly passes ``--overwrite``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BASELINE_ARTIFACTS = (
    # Source and data-quality contracts.
    "data/vnstock/v6_snapshot/snapshot_manifest.json",
    "data/processed/wave_ignition/audit/quality_summary.json",
    "data/training/wave_ignition/wave_dataset_continuation_h60/runs/20260820T165402Z/dataset_manifest.json",
    "data/training/wave_ignition/wave_dataset_continuation_h120/runs/20260820T165421Z/dataset_manifest.json",
    "data/labels/wave_ignition/wave_continuation_h60_v1/runs/20260820T165207Z/label_manifest.json",
    "data/labels/wave_ignition/wave_continuation_h120_v1/runs/20260820T165322Z/label_manifest.json",
    # Continuation model baselines.
    "models/wave_ignition/xgboost_continuation_h60/runs/20260820T165529Z/model_manifest.json",
    "models/wave_ignition/xgboost_continuation_h60/runs/20260820T165529Z/audit/oof_metrics.json",
    "models/wave_ignition/xgboost_continuation_h60/runs/20260820T165529Z/audit/fold_metrics.csv",
    "models/wave_ignition/xgboost_continuation_h120/runs/20260820T170202Z/model_manifest.json",
    "models/wave_ignition/xgboost_continuation_h120/runs/20260820T170202Z/audit/oof_metrics.json",
    "models/wave_ignition/xgboost_continuation_h120/runs/20260820T170202Z/audit/fold_metrics.csv",
    # V6 causal OOF and cascade baselines.
    "eval/runs/wave_v6_oof_p0_causal_weights/oof_export_report.json",
    "eval/runs/wave_v6_oof_p0_causal_weights/model_metrics_walk_forward_summary.csv",
    "models/wave_ignition/wave_cascade_p0_continuation/runs/20260822T164306Z/audit/metrics.json",
    "models/wave_ignition/wave_cascade_p0/runs/20260822T164231Z/audit/metrics.json",
    "models/wave_ignition/wave_cascade_p0_causal_weights/runs/20260822T165617Z/audit/metrics.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_info(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    status = run("status", "--short", "--untracked-files=all")
    return {
        "commit": run("rev-parse", "HEAD"),
        "status_clean": status == "",
        "status_short": status.splitlines() if status else [],
    }


def _json_summary(path: Path) -> dict[str, Any] | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def build_lock(root: Path) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative in BASELINE_ARTIFACTS:
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        record: dict[str, Any] = {
            "path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        summary = _json_summary(path)
        if summary is not None:
            record["json"] = summary
        artifacts.append(record)
    if missing:
        raise FileNotFoundError(
            "Baseline artifacts are missing:\n" + "\n".join(f"- {path}" for path in missing)
        )
    return {
        "schema_version": 1,
        "baseline_id": "wave_p0_current",
        "locked_at_utc": datetime.now(UTC).isoformat(),
        "purpose": "Immutable comparison point before phase-1 OHLCV remediation.",
        "root": str(root),
        "git": _git_info(root),
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/baselines/wave_p0_current_lock.json"),
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite existing baseline lock: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = build_lock(root)
    output.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "baseline_locked", "path": str(output), "artifacts": len(lock["artifacts"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
