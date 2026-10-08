"""Freeze a trained model run into an immutable, checksummed artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "model_manifest.json",
    "model/entry_classifier.json",
    "model/strength_regressor.json",
    "model/calibration.json",
    "model/decision_policy.json",
    "model/features.json",
    "predictions/oof_predictions.parquet",
    "audit/fold_metrics.csv",
    "audit/oof_metrics.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-root",
        type=Path,
        default=Path("models/wave_ignition/xgboost_wave_v1"),
    )
    parser.add_argument("--model-run", type=Path)
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("models/artifacts")
    )
    parser.add_argument(
        "--registry-root", type=Path, default=Path("eval/registry")
    )
    parser.add_argument("--status", default="experimental", choices=("experimental", "candidate"))
    return parser.parse_args()


def resolve_model_run(explicit: Path | None, root: Path) -> Path:
    if explicit is not None:
        return explicit.resolve()
    latest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    return Path(latest["run_directory"]).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def relative_to_project(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def inventory(directory: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        if path.name == "artifact_manifest.json":
            continue
        records.append(
            {
                "path": path.relative_to(directory).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def aggregate_sha256(records: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def validate_source(run: Path) -> dict[str, Any]:
    missing = [relative for relative in REQUIRED_FILES if not (run / relative).is_file()]
    if missing:
        raise RuntimeError(f"Model run is incomplete; missing files: {missing}")
    manifest = json.loads((run / "model_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("final_test_evaluated"):
        raise RuntimeError("V1 experimental artifact must preserve the sealed final test.")
    unexpected_test_files = [path for path in run.rglob("*final_test*") if path.is_file()]
    if unexpected_test_files:
        raise RuntimeError(f"Unexpected final-test artifacts found: {unexpected_test_files}")
    return manifest


def main() -> None:
    args = parse_args()
    source_run = resolve_model_run(args.model_run, args.model_root)
    source_manifest = validate_source(source_run)
    model_version = str(source_manifest["model_version"])
    run_id = str(source_manifest["run_id"])
    version_root = args.artifact_root / model_version
    destination = version_root / run_id
    if destination.exists():
        raise FileExistsError(
            f"Frozen artifact already exists and will not be overwritten: {destination}"
        )
    version_root.mkdir(parents=True, exist_ok=True)
    temporary = version_root / f".incomplete-{run_id}"
    if temporary.exists():
        raise FileExistsError(f"Incomplete artifact path already exists: {temporary}")
    completed = False
    try:
        shutil.copytree(source_run, temporary)
        files = inventory(temporary)
        frozen_at = datetime.now(UTC).isoformat()
        artifact_manifest = {
            "artifact_format_version": 1,
            "artifact_id": f"{model_version}:{run_id}",
            "model_version": model_version,
            "run_id": run_id,
            "frozen_at_utc": frozen_at,
            "source_run": relative_to_project(source_run),
            "artifact_directory": relative_to_project(destination),
            "immutable": True,
            "model_status": args.status,
            "deployment_eligible": False,
            "final_test_evaluated": False,
            "benchmark_version": "v1",
            "rejection_reasons": [
                "Artifact is registered as experimental pending standalone evaluation.",
                "Final holdout has not been evaluated.",
            ],
            "dataset_dependency": source_manifest["dataset_dependency"],
            "payload_sha256": aggregate_sha256(files),
            "payload_size_bytes": sum(int(record["size_bytes"]) for record in files),
            "files": files,
        }
        write_json(artifact_manifest, temporary / "artifact_manifest.json")
        temporary.rename(destination)
        latest_payload = {
            "artifact_id": artifact_manifest["artifact_id"],
            "artifact_directory": str(destination.resolve()),
            "payload_sha256": artifact_manifest["payload_sha256"],
            "model_status": args.status,
            "deployment_eligible": False,
            "frozen_at_utc": frozen_at,
        }
        write_json(latest_payload, version_root / "latest.json")
        registry_payload = {
            **latest_payload,
            "artifact_directory": relative_to_project(destination),
            "dataset_version": source_manifest["dataset_dependency"]["dataset_version"],
            "final_test_evaluated": False,
            "registry_note": "Canonical V1 experimental benchmark; not approved for deployment.",
        }
        write_json(
            registry_payload,
            args.registry_root / f"{model_version}_{run_id}.json",
        )
        completed = True
        print(json.dumps(registry_payload, ensure_ascii=False, indent=2), flush=True)
    finally:
        if not completed and temporary.exists():
            shutil.rmtree(temporary)


if __name__ == "__main__":
    main()
