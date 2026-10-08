"""Create a checksummed shadow deployment bundle for the locked H120 cascade."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.wave_production import (  # noqa: E402
    CASCADE_RUNTIME_FILES,
    H120_RUNTIME_FILES,
    file_record,
    sha256_file,
)


def _git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _verify_source_lock(lock_path: Path) -> dict[str, Any]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("status") != "research_candidate_requires_new_holdout":
        raise RuntimeError("Expected the locked v4 research candidate.")
    model_manifest = lock.get("model_manifest", {})
    if model_manifest.get("probability_columns") != ["p_h120"]:
        raise RuntimeError("Source lock is not H120-only.")
    if model_manifest.get("continuous_columns") != []:
        raise RuntimeError("Source lock unexpectedly uses strength features.")
    if model_manifest.get("candidate_policy", {}).get("shortlist_k") != 10:
        raise RuntimeError("Source lock does not freeze shortlist_k=10.")
    for record in lock.get("files", []):
        path = (ROOT / record["path"]).resolve()
        if not path.is_file():
            raise RuntimeError(f"Source lock file is missing: {record['path']}")
        exact_match = (
            path.stat().st_size == int(record["size_bytes"])
            and sha256_file(path) == record["sha256"]
        )
        if exact_match:
            continue
        # Git may materialize tracked text as CRLF on Windows. The lock was
        # created from LF bytes, so compare canonical text without weakening
        # byte-level verification for model, parquet, or joblib payloads.
        if path.suffix.lower() in {".yaml", ".yml", ".json", ".csv", ".md", ".py"}:
            canonical = path.read_bytes().replace(b"\r\n", b"\n")
            canonical_hash = hashlib.sha256(canonical).hexdigest()
            if (
                len(canonical) == int(record["size_bytes"])
                and canonical_hash == record["sha256"]
            ):
                continue
        raise RuntimeError(f"Source lock checksum mismatch: {record['path']}")
    return lock


def build_bundle(
    *,
    lock_path: Path,
    h120_run: Path,
    output: Path,
    deployment_status: str,
) -> dict[str, Any]:
    lock_path = lock_path.resolve()
    h120_run = h120_run.resolve()
    lock = _verify_source_lock(lock_path)
    cascade_run = (ROOT / lock["model_run"]).resolve()
    h120_manifest_path = h120_run / "model_manifest.json"
    features_path = h120_run / "model/features.json"
    if not h120_manifest_path.is_file() or not features_path.is_file():
        raise FileNotFoundError("H120 model run is incomplete.")
    h120_manifest = json.loads(h120_manifest_path.read_text(encoding="utf-8"))
    if h120_manifest.get("model_version") != "xgboost_continuation_h120":
        raise RuntimeError("Selected upstream artifact is not continuation H120.")
    if h120_manifest.get("final_test_evaluated"):
        raise RuntimeError("H120 upstream artifact unexpectedly opened its final test.")
    if deployment_status == "production_approved":
        raise RuntimeError(
            "Production approval is blocked until a new holdout and promotion record exist."
        )
    cascade_manifest = lock["model_manifest"]
    policy = cascade_manifest["candidate_policy"]
    feature_columns = json.loads(features_path.read_text(encoding="utf-8"))[
        "feature_columns"
    ]
    files = [
        *(
            file_record(h120_run / relative, ROOT, role="h120_model")
            for relative in H120_RUNTIME_FILES
        ),
        *(
            file_record(cascade_run / relative, ROOT, role="cascade_model")
            for relative in CASCADE_RUNTIME_FILES
        ),
        file_record(lock_path, ROOT, role="source_lock"),
    ]
    status_short = _git_value("status", "--short", "--untracked-files=all")
    return {
        "schema_version": 1,
        "bundle_id": (
            f"wave_h120_shadow:{h120_manifest['run_id']}:"
            f"{cascade_manifest['run_id']}"
        ),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "deployment_status": deployment_status,
        "promotion_blocker": "requires_new_untouched_holdout_and_cost_aware_backtest",
        "artifacts": {
            "h120_model_run": h120_run.relative_to(ROOT).as_posix(),
            "cascade_model_run": cascade_run.relative_to(ROOT).as_posix(),
            "source_lock": lock_path.relative_to(ROOT).as_posix(),
        },
        "contract": {
            "decision_time": "after_market_close",
            "execution_time": "next_session_open",
            "feature_version": "wave_ignition_v2",
            "feature_columns": feature_columns,
            "probability_columns": ["p_h120"],
            "continuous_columns": [],
            "candidate_mode": "universe",
            "hard_gate_enabled": False,
            "shortlist_k": int(policy["shortlist_k"]),
            "strength_weight": float(policy["strength_weight"]),
            "decision_threshold": float(cascade_manifest["threshold_calibrated"]),
            "ranking_column": "p_cascade_calibrated",
            "trade_authorized": False,
        },
        "lineage": {
            "h120_model_version": h120_manifest["model_version"],
            "h120_run_id": h120_manifest["run_id"],
            "cascade_version": cascade_manifest["experiment_version"],
            "cascade_run_id": cascade_manifest["run_id"],
            "selection_scope": cascade_manifest["selection_scope"],
            "final_test_used_for_selection": cascade_manifest[
                "final_test_used_for_selection"
            ],
        },
        "code": {
            "commit": _git_value("rev-parse", "HEAD"),
            "status_clean": status_short == "",
            "status_short": status_short.splitlines() if status_short else [],
        },
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(
            "experiments/baselines/wave_cascade_research_v4_h120_only_lock.json"
        ),
    )
    parser.add_argument(
        "--h120-model-run",
        type=Path,
        default=Path(
            "models/wave_ignition_snapshot/xgboost_continuation_h120/"
            "runs/20260823T052814Z"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("deploy/wave_h120_shadow/bundle_manifest.json"),
    )
    parser.add_argument(
        "--deployment-status",
        choices=("shadow_candidate_requires_new_holdout", "production_approved"),
        default="shadow_candidate_requires_new_holdout",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite frozen bundle: {output}")
    bundle = build_bundle(
        lock_path=args.lock,
        h120_run=args.h120_model_run,
        output=output,
        deployment_status=args.deployment_status,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.json")
    temporary.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(output)
    print(
        json.dumps(
            {
                "status": bundle["deployment_status"],
                "bundle": str(output),
                "files": len(bundle["files"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
