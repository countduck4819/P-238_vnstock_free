"""Run the daily H120 shadow pipeline from data sync through predictions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RunLock:
    """Small cross-process lock using an exclusive file create."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: int | None = None

    def __enter__(self) -> RunLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._handle = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as exc:
            raise RuntimeError(f"Another shadow pipeline is already running: {self.path}") from exc
        os.write(self._handle, f"pid={os.getpid()}\n".encode("ascii"))
        return self

    def __exit__(self, *_: object) -> None:
        if self._handle is not None:
            os.close(self._handle)
        self.path.unlink(missing_ok=True)


def local_path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_serving_release(
    *,
    payload: dict[str, Any],
    manifest_path: Path,
    release_path: Path,
    bundle_path: Path,
) -> dict[str, Any]:
    """Atomically publish a verified successful H120 run.

    Validation happens before the temporary release is written.  Therefore an
    inference or publish failure leaves the previous release pointer untouched.
    """

    if payload.get("trade_authorized") is not False:
        raise RuntimeError("Refusing to publish a trade-authorized H120 run.")
    predictions = payload.get("predictions")
    if not isinstance(predictions, dict):
        raise RuntimeError("Cannot publish H120 run without predictions.")
    output = predictions.get("output")
    if not isinstance(output, dict) or not isinstance(output.get("path"), str):
        raise RuntimeError("Cannot publish H120 run without a prediction output path.")
    output_path = local_path(Path(output["path"]))
    if not output_path.is_file():
        raise RuntimeError(f"Prediction output is missing: {output_path}")
    actual_size = output_path.stat().st_size
    actual_sha = sha256_file(output_path)
    if actual_size != int(output.get("size_bytes", -1)):
        raise RuntimeError("Prediction output size changed before publish.")
    if actual_sha != output.get("sha256"):
        raise RuntimeError("Prediction output checksum changed before publish.")

    release = {
        "schema_version": 1,
        "release_id": f"wave_h120_advisory_{payload['run_id']}",
        "release_kind": "production_serving_advisory",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_orchestration_manifest": manifest_path.relative_to(ROOT).as_posix(),
        "snapshot_date": payload.get("snapshot_date"),
        "as_of_date": payload.get("as_of_date"),
        "prediction_output": {
            "path": output_path.relative_to(ROOT).as_posix(),
            "sha256": actual_sha,
            "size_bytes": actual_size,
        },
        "model_bundle": bundle_path.relative_to(ROOT).as_posix(),
        "runtime": {"inference_replay": "deterministic_verified"},
        "contract": {
            "horizon_sessions": 120,
            "probability_field": "continuation_probability_h120",
            "advisory_only": True,
            "trade_authorized": False,
            "serving_access": "premium_and_admin",
        },
        "promotion_blocker": "requires_new_untouched_holdout_and_cost_aware_backtest",
    }
    write_json(release_path, release)
    return release


def validate_snapshot_manifest(
    manifest: dict[str, Any],
    *,
    requested_end: str,
    minimum_coverage: float,
    expected_price_policy: str,
    minimum_history_sessions: int = 0,
) -> dict[str, Any]:
    if manifest.get("requested_as_of_end") != requested_end:
        raise RuntimeError(
            "Snapshot as-of mismatch: "
            f"actual={manifest.get('requested_as_of_end')}, expected={requested_end}"
        )
    coverage = float(manifest.get("coverage_ratio", 0.0))
    if coverage < minimum_coverage:
        raise RuntimeError(
            f"Snapshot coverage {coverage:.2%} is below {minimum_coverage:.2%}."
        )
    if manifest.get("price_adjustment_policy") != expected_price_policy:
        raise RuntimeError("Snapshot price adjustment policy does not match production config.")
    if int(manifest.get("failed_symbols", 1)):
        raise RuntimeError(
            f"Snapshot contains failed symbols: {manifest.get('failed_symbols')}"
        )
    market_rows = int(manifest.get("vnindex", {}).get("rows", 0))
    if market_rows < minimum_history_sessions:
        raise RuntimeError(
            f"Snapshot has only {market_rows} VNINDEX rows; "
            f"at least {minimum_history_sessions} are required for feature warm-up."
        )
    alignment = manifest.get("calendar_alignment_summary", {})
    alignment_ratio = alignment.get("current_to_vnindex_ratio")
    # A listed universe contains suspended/delisted symbols by design. Their
    # point-in-time tradability is evaluated by the downstream feature quality
    # gate; requiring every raw ticker to print on today's VNINDEX session would
    # reject an otherwise complete provider snapshot.
    if alignment.get("strict_current_required") and float(alignment_ratio or 0.0) < minimum_coverage:
        raise RuntimeError("Snapshot market-calendar alignment is below the quality gate.")
    return {
        "coverage_ratio": coverage,
        "successful_symbols": int(manifest.get("successful_symbols", 0)),
        "latest_market_date": manifest.get("vnindex", {}).get("max_time"),
        "history_sessions": market_rows,
    }


def _market_csv_path(snapshot_manifest: dict[str, Any], snapshot_dir: Path) -> Path:
    """Resolve the market CSV even for legacy manifests with absolute paths."""

    raw_path = snapshot_manifest.get("vnindex", {}).get("path")
    if isinstance(raw_path, str) and raw_path.strip():
        path = Path(raw_path)
        if path.is_file():
            return path
    fallback = snapshot_dir / "market" / "VNINDEX.csv"
    if fallback.is_file():
        return fallback
    raise RuntimeError("Snapshot manifest has no readable VNINDEX CSV for as-of resolution.")


def resolve_effective_as_of_date(
    snapshot_manifest: dict[str, Any],
    *,
    snapshot_dir: Path,
    requested_end: str,
    max_staleness_days: int,
) -> str:
    """Return the last actual market bar, never the download/snapshot date.

    A snapshot can be downloaded on a weekend or before an upstream provider has
    published the last session.  The model must score the latest VNINDEX bar it
    actually received; its manifest preserves both dates for traceability.
    """

    if max_staleness_days < 0:
        raise ValueError("max_staleness_days must be non-negative.")
    raw_max = snapshot_manifest.get("vnindex", {}).get("max_time")
    if isinstance(raw_max, str) and raw_max.strip():
        latest = datetime.fromisoformat(raw_max.replace("Z", "+00:00")).date()
    else:
        market_path = _market_csv_path(snapshot_manifest, snapshot_dir)
        latest_text: str | None = None
        with market_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                value = row.get("time") or row.get("date")
                if value and (latest_text is None or value > latest_text):
                    latest_text = value
        if latest_text is None:
            raise RuntimeError(f"VNINDEX CSV has no readable date: {market_path}")
        latest = datetime.fromisoformat(latest_text.replace("Z", "+00:00")).date()

    requested = date.fromisoformat(requested_end)
    if latest > requested:
        raise RuntimeError(
            f"Snapshot contains a future market bar ({latest}) after requested cutoff ({requested})."
        )
    stale_days = (requested - latest).days
    if stale_days > max_staleness_days:
        raise RuntimeError(
            f"Market data are stale by {stale_days} calendar day(s): "
            f"requested={requested}, latest_market_date={latest}."
        )
    return latest.isoformat()


def validate_feature_manifest(
    manifest: dict[str, Any],
    *,
    feature_run: Path,
    expected_feature_version: str,
    expected_price_policy: str,
) -> dict[str, Any]:
    if manifest.get("feature_version") != expected_feature_version:
        raise RuntimeError(
            f"Feature version mismatch: actual={manifest.get('feature_version')}, "
            f"expected={expected_feature_version}"
        )
    if manifest.get("price_adjustment_policy") != expected_price_policy:
        raise RuntimeError("Feature price adjustment policy does not match production config.")
    if manifest.get("promotion_status") != "candidate_for_training":
        raise RuntimeError(
            f"Feature run is not eligible for shadow scoring: {manifest.get('promotion_status')}"
        )
    quality_path = feature_run / "audit/feature_quality_report.json"
    if not quality_path.is_file():
        raise RuntimeError(f"Feature quality report is missing: {quality_path}")
    quality = read_json(quality_path)
    if int(quality.get("non_finite_rows", 0)):
        raise RuntimeError("Feature quality report contains non-finite rows.")
    if int(quality.get("duplicate_symbol_dates", 0)):
        raise RuntimeError("Feature quality report contains duplicate symbol/date keys.")
    ready_rows = int(quality.get("ready_rows", -1))
    ready_rate = float(quality.get("ready_rate", 0.0) or 0.0)
    if ("ready_rows" in quality and ready_rows <= 0) or ("ready_rows" not in quality and ready_rate <= 0.0):
        failures = quality.get("quality_gate_failure_counts_non_exclusive", {})
        raise RuntimeError(
            "Feature eligibility is empty; no symbols can be scored. "
            f"ready_rows={ready_rows}, failure_counts={failures}"
        )
    return {
        "run_id": manifest.get("run_id"),
        "last_date": quality.get("last_date"),
        "ready_rate": quality.get("ready_rate"),
    }


def run_step(
    name: str,
    command: Sequence[str],
    *,
    log_path: Path,
    timeout_seconds: int,
    retries: int,
) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, retries + 2):
        attempt_started = time.monotonic()
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n=== {name} attempt {attempt} ===\n")
            log.write("$ " + " ".join(command) + "\n")
            try:
                completed = subprocess.run(
                    list(command),
                    cwd=ROOT,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=timeout_seconds,
                    text=True,
                )
                attempts.append(
                    {
                        "attempt": attempt,
                        "return_code": completed.returncode,
                        "duration_seconds": round(time.monotonic() - attempt_started, 3),
                    }
                )
                if completed.returncode == 0:
                    return {
                        "name": name,
                        "status": "ok",
                        "started_at_utc": started.isoformat(),
                        "finished_at_utc": datetime.now(UTC).isoformat(),
                        "attempts": attempts,
                        "log": str(log_path.relative_to(ROOT).as_posix()),
                    }
            except subprocess.TimeoutExpired:
                attempts.append(
                    {
                        "attempt": attempt,
                        "return_code": None,
                        "timeout": True,
                        "duration_seconds": round(time.monotonic() - attempt_started, 3),
                    }
                )
    return {
        "name": name,
        "status": "failed",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "attempts": attempts,
        "log": str(log_path.relative_to(ROOT).as_posix()),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of-date",
        help="Requested data cutoff YYYY-MM-DD; defaults to --snapshot-date.",
    )
    parser.add_argument(
        "--snapshot-date",
        help="Download/snapshot date YYYY-MM-DD; defaults to today in Asia/Ho_Chi_Minh.",
    )
    parser.add_argument("--start-date", default="2015-09-28")
    parser.add_argument(
        "--history-sessions", type=int,
        default=int(os.environ.get("WAVE_HISTORY_SESSIONS", "480")),
        help="Bounded OHLCV history fetched per symbol (default: 480).",
    )
    parser.add_argument(
        "--minimum-history-sessions", type=int, default=372,
        help="Minimum market history required before feature generation (default: 372).",
    )
    parser.add_argument("--price-policy", choices=("raw", "adjusted"), default="adjusted")
    parser.add_argument("--snapshot-root", type=Path, default=Path("data/vnstock/v6_snapshot"))
    parser.add_argument(
        "--universe-symbols",
        type=Path,
        default=Path(
            os.environ.get(
                "WAVE_H120_UNIVERSE_SYMBOLS",
                "deploy/wave_h120_shadow/universe_symbols.csv",
            )
        ),
        help="Frozen-universe CSV with a symbol column used for daily scoring.",
    )
    parser.add_argument("--run-root", type=Path, default=Path("runs/wave_h120_shadow"))
    parser.add_argument("--bundle", type=Path, default=Path("deploy/wave_h120_shadow/bundle_manifest.json"))
    parser.add_argument(
        "--serving-release",
        type=Path,
        default=Path(
            os.environ.get(
                "WAVE_H120_SERVING_RELEASE",
                "deploy/wave_h120_shadow/serving_release.json",
            )
        ),
    )
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--feature-config", type=Path, default=Path("configs/wave_ignition_features_v2.yaml"))
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--force-sync", action="store_true")
    parser.add_argument("--minimum-coverage", type=float, default=0.95)
    parser.add_argument(
        "--requests-per-minute",
        type=float,
        default=float(os.environ.get("WAVE_H120_REQUESTS_PER_MINUTE", "20")),
        help="Maximum per-symbol provider calls per minute during sync.",
    )
    parser.add_argument(
        "--max-staleness-days",
        type=int,
        default=int(os.environ.get("WAVE_H120_MAX_STALENESS_DAYS", "0")),
        help="Maximum allowed gap from requested cutoff to the last market bar.",
    )
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--step-timeout-seconds", type=int, default=7_200)
    parser.add_argument("--lock-path", type=Path)
    return parser.parse_args(argv)


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    if not 0.0 < args.minimum_coverage <= 1.0:
        raise ValueError("minimum-coverage must be in (0, 1].")
    if args.history_sessions < 372 or args.minimum_history_sessions < 372:
        raise ValueError("history-sessions and minimum-history-sessions must be at least 372.")
    if args.retries < 0:
        raise ValueError("retries must be non-negative.")
    snapshot_date = args.snapshot_date or datetime.now(VIETNAM_TZ).date().isoformat()
    requested_end = args.as_of_date or snapshot_date
    date.fromisoformat(snapshot_date)
    date.fromisoformat(requested_end)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = local_path(args.run_root) / f"{snapshot_date}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    snapshot_dir = local_path(args.snapshot_root) if args.skip_sync else run_dir / "snapshot"
    clean_dir = run_dir / "processed"
    feature_root = run_dir / "features"
    logs_dir = run_dir / "logs"
    manifest_path = run_dir / "orchestration_manifest.json"
    steps: list[dict[str, Any]] = []
    started = datetime.now(UTC)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "pipeline": "wave_h120_shadow",
        "run_id": run_id,
        "snapshot_date": snapshot_date,
        "requested_as_of_date": requested_end,
        "as_of_date": None,
        "started_at_utc": started.isoformat(),
        "status": "running",
        "deployment_status": "shadow_candidate_requires_new_holdout",
        "trade_authorized": False,
        "steps": steps,
    }
    write_json(manifest_path, payload)

    def execute(name: str, command: list[str]) -> None:
        result = run_step(
            name,
            command,
            log_path=logs_dir / f"{name}.log",
            timeout_seconds=args.step_timeout_seconds,
            retries=args.retries,
        )
        steps.append(result)
        write_json(manifest_path, payload)
        if result["status"] != "ok":
            raise RuntimeError(f"Pipeline step failed: {name}")

    try:
        if not args.skip_sync:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            execute(
                "sync",
                [
                    sys.executable,
                    "scripts/wave_v6/v6_data_adapter.py",
                    "sync",
                    "--start",
                    args.start_date,
                    "--end",
                    requested_end,
                    "--stock-dir",
                    str(snapshot_dir),
                    "--market-output",
                    str(snapshot_dir / "market/VNINDEX.csv"),
                    "--industry-output",
                    str(snapshot_dir / "industry_map.csv"),
                    "--symbols-output",
                    str(snapshot_dir / "symbols.csv"),
                    "--symbols-file",
                    str(local_path(args.universe_symbols)),
                    "--icb-level",
                    "2",
                    "--manifest-output",
                    str(snapshot_dir / "snapshot_manifest.json"),
                    "--price-policy",
                    args.price_policy,
                    "--requests-per-minute",
                    str(args.requests_per_minute),
                    "--history-sessions",
                    str(args.history_sessions),
                ]
                + (["--force"] if args.force_sync else []),
            )
        snapshot_manifest_path = snapshot_dir / "snapshot_manifest.json"
        snapshot_manifest = read_json(snapshot_manifest_path)
        payload["snapshot"] = {
            "manifest": str(snapshot_manifest_path.relative_to(ROOT).as_posix()),
            "quality": validate_snapshot_manifest(
                snapshot_manifest,
                requested_end=requested_end,
                minimum_coverage=args.minimum_coverage,
                expected_price_policy=args.price_policy,
                minimum_history_sessions=args.minimum_history_sessions,
            ),
        }
        effective_as_of_date = resolve_effective_as_of_date(
            snapshot_manifest,
            snapshot_dir=snapshot_dir,
            requested_end=requested_end,
            max_staleness_days=args.max_staleness_days,
        )
        payload["as_of_date"] = effective_as_of_date
        payload["snapshot"]["effective_as_of_date"] = effective_as_of_date
        payload["snapshot"]["staleness_days"] = (
            date.fromisoformat(requested_end) - date.fromisoformat(effective_as_of_date)
        ).days
        write_json(manifest_path, payload)

        execute(
            "clean",
            [
                sys.executable,
                "scripts/build_clean_training_inputs.py",
                "--input-layout",
                "v6_snapshot",
                "--snapshot-dir",
                str(snapshot_dir),
                "--output-dir",
                str(clean_dir),
                "--price-policy",
                args.price_policy,
            ],
        )
        execute(
            "features",
            [
                sys.executable,
                "scripts/build_wave_ignition_features.py",
                "--input-dir",
                str(clean_dir),
                "--config",
                str(local_path(args.feature_config)),
                "--output-root",
                str(feature_root),
            ],
        )
        feature_latest_path = feature_root / "wave_ignition_v2/latest.json"
        feature_latest = read_json(feature_latest_path)
        feature_run = Path(feature_latest["run_directory"])
        feature_manifest_path = feature_run / "feature_manifest.json"
        feature_manifest = read_json(feature_manifest_path)
        payload["features"] = {
            "manifest": str(feature_manifest_path.relative_to(ROOT).as_posix()),
            "run": str(feature_run.relative_to(ROOT).as_posix()),
            "quality": validate_feature_manifest(
                feature_manifest,
                feature_run=feature_run,
                expected_feature_version="wave_ignition_v2",
                expected_price_policy=args.price_policy,
            ),
        }
        write_json(manifest_path, payload)

        prediction_root = run_dir / "predictions"
        execute(
            "inference",
            [
                sys.executable,
                "scripts/run_h120_daily_inference.py",
                "--bundle",
                str(local_path(args.bundle)),
                "--features",
                str(feature_run),
                "--feature-manifest",
                str(feature_manifest_path),
                "--as-of-date",
                effective_as_of_date,
                "--output-root",
                str(prediction_root),
            ],
        )
        prediction_run = prediction_root / effective_as_of_date
        prediction_manifest_path = prediction_run / "prediction_manifest.json"
        prediction_manifest = read_json(prediction_manifest_path)
        payload["predictions"] = {
            "manifest": str(prediction_manifest_path.relative_to(ROOT).as_posix()),
            "output": prediction_manifest["output"],
            "summary": prediction_manifest["summary"],
        }
        payload["status"] = "publishing"
        write_json(manifest_path, payload)
        if not args.no_publish:
            release_path = local_path(args.serving_release)
            release = publish_serving_release(
                payload=payload,
                manifest_path=manifest_path,
                release_path=release_path,
                bundle_path=local_path(args.bundle),
            )
            payload["release"] = {
                "status": "published",
                "path": release_path.relative_to(ROOT).as_posix(),
                "release_id": release["release_id"],
            }
        payload["status"] = "success"
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        payload["finished_at_utc"] = datetime.now(UTC).isoformat()
        write_json(manifest_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    lock_path = local_path(args.lock_path or (args.run_root / ".pipeline.lock"))
    with RunLock(lock_path):
        result = run_pipeline(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
