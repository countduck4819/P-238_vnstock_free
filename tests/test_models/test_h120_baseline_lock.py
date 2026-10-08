from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_h120_baseline_lock import (
    CASCADE_RUN,
    DEFAULT_LOCK,
    DEFAULT_REPORT_ROOT,
    METRIC_TOLERANCE,
    UPSTREAM_RUN,
    evaluate_baseline,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[2]


def _assert_metric_tree(actual: object, expected: object, path: str = "") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        for key, value in expected.items():
            assert key in actual, f"Missing metric at {path}{key}"
            _assert_metric_tree(actual[key], value, f"{path}{key}.")
    elif isinstance(expected, float):
        assert float(actual) == pytest.approx(expected, abs=METRIC_TOLERANCE, rel=0.0), path
    else:
        assert actual == expected, path


def test_h120_baseline_lock_reproduces_frozen_oof_metrics() -> None:
    lock_path = ROOT / DEFAULT_LOCK
    report_path = ROOT / DEFAULT_REPORT_ROOT / "metrics.json"
    assert lock_path.is_file(), "Run scripts/run_h120_baseline_lock.py before this test."
    assert report_path.is_file(), "Phase-0 metrics report is missing."

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    metrics, _, _, _ = evaluate_baseline(
        upstream_run=ROOT / UPSTREAM_RUN,
        cascade_run=ROOT / CASCADE_RUN,
    )

    assert lock["baseline_id"] == "h120_shadow_champion_e00_20260824"
    assert lock["status"] == "frozen_shadow_champion_reproduced"
    assert lock["final_test_used_for_selection"] is False
    assert lock["champion"]["trade_authorized"] is False
    assert lock["final_test_policy"]["status"] == "contaminated_postmortem_only"
    assert lock["metric_tolerance"] == METRIC_TOLERANCE
    _assert_metric_tree(metrics, lock["reproduced_metric_surfaces"])
    _assert_metric_tree(metrics, report["surfaces"])


def test_h120_baseline_lock_checksums_still_match_artifacts() -> None:
    lock_path = ROOT / DEFAULT_LOCK
    assert lock_path.is_file(), "Run scripts/run_h120_baseline_lock.py before this test."
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    for record in lock["files"]:
        path = ROOT / record["path"]
        assert path.is_file(), record["path"]
        assert path.stat().st_size == record["size_bytes"], record["path"]
        assert sha256_file(path) == record["sha256"], record["path"]
