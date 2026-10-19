from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.run_wave_h120_shadow import (
    RunLock,
    publish_serving_release,
    resolve_effective_as_of_date,
    validate_feature_manifest,
    validate_snapshot_manifest,
)


def valid_snapshot() -> dict[str, object]:
    return {
        "requested_as_of_end": "2026-08-24",
        "coverage_ratio": 1.0,
        "price_adjustment_policy": "adjusted",
        "failed_symbols": 0,
        "calendar_alignment_summary": {"current_to_vnindex_ratio": 1.0},
        "successful_symbols": 1500,
        "vnindex": {"max_time": "2026-08-24T00:00:00"},
    }


def test_snapshot_quality_gate_rejects_partial_or_misaligned_data() -> None:
    quality = validate_snapshot_manifest(
        valid_snapshot(),
        requested_end="2026-08-24",
        minimum_coverage=0.95,
        expected_price_policy="adjusted",
    )
    assert quality["successful_symbols"] == 1500

    broken = valid_snapshot()
    broken["failed_symbols"] = 2
    with pytest.raises(RuntimeError, match="failed symbols"):
        validate_snapshot_manifest(
            broken,
            requested_end="2026-08-24",
            minimum_coverage=0.95,
            expected_price_policy="adjusted",
        )


def test_snapshot_quality_gate_tolerates_a_bounded_number_of_failed_symbols() -> None:
    partial = valid_snapshot()
    partial["failed_symbols"] = 2
    quality = validate_snapshot_manifest(
        partial,
        requested_end="2026-08-24",
        minimum_coverage=0.95,
        expected_price_policy="adjusted",
        max_failed_symbols=30,
    )
    assert quality["failed_symbols"] == 2

    partial["failed_symbols"] = 31
    with pytest.raises(RuntimeError, match="failed symbols"):
        validate_snapshot_manifest(
            partial,
            requested_end="2026-08-24",
            minimum_coverage=0.95,
            expected_price_policy="adjusted",
            max_failed_symbols=30,
        )


def test_effective_as_of_is_last_market_bar_not_download_date(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    manifest = valid_snapshot()
    manifest["vnindex"] = {"max_time": "2026-08-21T00:00:00"}

    assert resolve_effective_as_of_date(
        manifest,
        snapshot_dir=snapshot_dir,
        requested_end="2026-08-23",
        max_staleness_days=4,
    ) == "2026-08-21"

    with pytest.raises(RuntimeError, match="stale"):
        resolve_effective_as_of_date(
            manifest,
            snapshot_dir=snapshot_dir,
            requested_end="2026-08-30",
            max_staleness_days=4,
        )


def test_feature_quality_gate_reads_the_run_local_quality_report(tmp_path: Path) -> None:
    feature_run = tmp_path / "feature_run"
    (feature_run / "audit").mkdir(parents=True)
    (feature_run / "audit/feature_quality_report.json").write_text(
        json.dumps(
            {
                "non_finite_rows": 0,
                "duplicate_symbol_dates": 0,
                "ready_rate": 0.8,
                "last_date": "2026-08-24",
            }
        ),
        encoding="utf-8",
    )
    result = validate_feature_manifest(
        {
            "feature_version": "wave_ignition_v2",
            "price_adjustment_policy": "adjusted",
            "promotion_status": "candidate_for_training",
            "run_id": "test",
        },
        feature_run=feature_run,
        expected_feature_version="wave_ignition_v2",
        expected_price_policy="adjusted",
    )
    assert result["ready_rate"] == 0.8


def test_run_lock_rejects_concurrent_execution(tmp_path: Path) -> None:
    lock_path = tmp_path / "shadow.lock"
    with RunLock(lock_path):
        with pytest.raises(RuntimeError, match="already running"):
            with RunLock(lock_path):
                pass
    assert not lock_path.exists()


def test_run_lock_replaces_a_lock_left_by_a_killed_worker(tmp_path: Path) -> None:
    lock_path = tmp_path / "shadow.lock"
    # Owner process no longer exists (container recreated mid-run).
    lock_path.write_text(json.dumps({"pid": 999_999_999, "identity": "gone:1"}), encoding="utf-8")
    with RunLock(lock_path):
        assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] > 0
    assert not lock_path.exists()

    # Legacy ``pid=`` lock files fall back to their age.
    lock_path.write_text("pid=1\n", encoding="ascii")
    with pytest.raises(RuntimeError, match="already running"):
        with RunLock(lock_path):
            pass
    with RunLock(lock_path, stale_after_seconds=0):
        pass


def test_publish_release_is_atomic_and_preserves_old_release_on_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("scripts.run_wave_h120_shadow.ROOT", tmp_path)
    run_dir = tmp_path / "runs/wave_h120_shadow/test"
    output = run_dir / "predictions/2026-08-28/predictions.parquet"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"verified prediction")
    manifest_path = run_dir / "orchestration_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    bundle = tmp_path / "deploy/wave_h120_shadow/bundle_manifest.json"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("{}", encoding="utf-8")
    release_path = bundle.parent / "serving_release.json"
    release_path.write_text('{"release_id":"old"}', encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    payload = {
        "run_id": "20260901T000000Z",
        "snapshot_date": "2026-08-28",
        "as_of_date": "2026-08-28",
        "trade_authorized": False,
        "predictions": {
            "output": {
                "path": output.relative_to(tmp_path).as_posix(),
                "size_bytes": output.stat().st_size,
                "sha256": digest,
            }
        },
    }

    release = publish_serving_release(
        payload=payload,
        manifest_path=manifest_path,
        release_path=release_path,
        bundle_path=bundle,
    )
    assert release["as_of_date"] == "2026-08-28"
    assert json.loads(release_path.read_text(encoding="utf-8"))["release_id"] != "old"

    previous = release_path.read_bytes()
    payload["predictions"]["output"]["sha256"] = "invalid"
    with pytest.raises(RuntimeError, match="checksum"):
        publish_serving_release(
            payload=payload,
            manifest_path=manifest_path,
            release_path=release_path,
            bundle_path=bundle,
        )
    assert release_path.read_bytes() == previous
