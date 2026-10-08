"""Create a checksummed pre-holdout lock for the production cascade candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_RUN_FILES = (
    "model_manifest.json",
    "model/meta_model.joblib",
    "model/calibration.json",
    "predictions/oof_predictions.parquet",
    "audit/metrics.json",
    "audit/fold_metrics.csv",
)
EXPECTED_PROBABILITY_COLUMNS = ("p_h120",)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def git_info() -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=PROJECT_ROOT,
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


def file_record(path: Path) -> dict[str, Any]:
    return {
        "path": relative_path(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def resolve_run(model_root: Path, model_run: Path | None) -> Path:
    if model_run is not None:
        return model_run.resolve()
    latest = json.loads((model_root / "latest.json").read_text(encoding="utf-8"))
    return Path(latest["run_directory"]).resolve()


def validate_manifest(
    manifest: dict[str, Any],
    frame: Path,
    expected_probability_columns: tuple[str, ...] = EXPECTED_PROBABILITY_COLUMNS,
) -> None:
    if manifest.get("target_column") != "y_cont_h120":
        raise RuntimeError("Production cascade lock requires target_column=y_cont_h120.")
    if tuple(manifest.get("probability_columns", ())) != expected_probability_columns:
        raise RuntimeError(
            "Cascade probability schema does not match the requested contract: "
            f"actual={manifest.get('probability_columns')}, "
            f"expected={list(expected_probability_columns)}"
        )
    if manifest.get("continuous_columns", []) != []:
        raise RuntimeError("Production cascade lock requires no continuous strength features.")
    if manifest.get("meta_model") != "logistic":
        raise RuntimeError("Production cascade lock requires the logistic meta-model.")
    if float(manifest.get("positive_class_weight", 1.0)) != 1.0:
        raise RuntimeError("Production cascade lock requires positive_class_weight=1.0.")
    policy = manifest.get("candidate_policy", {})
    if policy.get("mode") != "universe" or policy.get("hard_gate_enabled"):
        raise RuntimeError("Production cascade lock requires full-universe ranking without a hard gate.")
    if float(policy.get("strength_weight", 0.0)) != 0.0:
        raise RuntimeError("Production cascade lock requires strength_weight=0.0.")
    source_frame = Path(str(manifest.get("source_frame", ""))).resolve()
    if source_frame != frame.resolve():
        raise RuntimeError(
            f"Cascade source frame mismatch: manifest={source_frame}, expected={frame.resolve()}"
        )


def build_lock(
    model_root: Path,
    model_run: Path | None,
    config: Path,
    frame: Path,
    frame_manifest: Path,
    expected_probability_columns: tuple[str, ...] = EXPECTED_PROBABILITY_COLUMNS,
    lock_id_prefix: str = "wave_cascade_prod_v3_continuation",
    status: str = "candidate_pre_final_holdout",
    final_holdout_opened: bool = False,
) -> dict[str, Any]:
    run = resolve_run(model_root, model_run)
    missing = [relative for relative in REQUIRED_RUN_FILES if not (run / relative).is_file()]
    if missing:
        raise FileNotFoundError(f"Cascade run is incomplete; missing: {missing}")
    if not config.is_file() or not frame.is_file() or not frame_manifest.is_file():
        raise FileNotFoundError("Config, source frame, and frame manifest must all exist.")
    manifest = json.loads((run / "model_manifest.json").read_text(encoding="utf-8"))
    validate_manifest(manifest, frame, expected_probability_columns)
    files = [
        *(run / relative for relative in REQUIRED_RUN_FILES),
        config,
        frame,
        frame_manifest,
    ]
    return {
        "schema_version": 1,
        "lock_id": f"{lock_id_prefix}:{manifest['run_id']}",
        "status": status,
        "locked_at_utc": datetime.now(UTC).isoformat(),
        "final_holdout_opened": final_holdout_opened,
        "selection_scope": "causal_oof_only",
        "model_run": relative_path(run),
        "source_frame": relative_path(frame),
        "frame_manifest": relative_path(frame_manifest),
        "config": relative_path(config),
        "model_manifest": manifest,
        "git": git_info(),
        "files": [file_record(path) for path in files],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-root",
        type=Path,
        default=Path("models/wave_ignition_snapshot/wave_cascade_research_v4_h120_only"),
    )
    parser.add_argument("--model-run", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/wave_cascade_v4_h120_only.yaml"),
    )
    parser.add_argument(
        "--frame",
        type=Path,
        default=Path("eval/runs/wave_cascade_prod_v2_continuation/oof_frame.parquet"),
    )
    parser.add_argument("--frame-manifest", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/baselines/wave_cascade_research_v4_h120_only_lock.json"),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing lock at the exact requested output path.",
    )
    parser.add_argument(
        "--expected-probability-columns",
        default=",".join(EXPECTED_PROBABILITY_COLUMNS),
    )
    parser.add_argument(
        "--lock-id-prefix",
        default="wave_cascade_research_v4_h120_only",
    )
    parser.add_argument(
        "--status",
        default="research_candidate_requires_new_holdout",
    )
    parser.add_argument("--final-holdout-opened", action="store_true")
    args = parser.parse_args()
    config = args.config.resolve()
    frame = args.frame.resolve()
    frame_manifest = (
        args.frame_manifest.resolve()
        if args.frame_manifest is not None
        else frame.parent / "manifest.json"
    )
    output = args.output.resolve()
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite existing cascade lock: {output}")
    expected_probability_columns = tuple(
        column.strip()
        for column in args.expected_probability_columns.split(",")
        if column.strip()
    )
    if not expected_probability_columns:
        raise ValueError("At least one expected probability column is required.")
    lock = build_lock(
        args.model_root.resolve(),
        args.model_run,
        config,
        frame,
        frame_manifest,
        expected_probability_columns,
        args.lock_id_prefix,
        args.status,
        args.final_holdout_opened,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "cascade_locked", "path": str(output), "files": len(lock["files"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
