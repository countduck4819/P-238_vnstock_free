from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.models.wave_production import (
    CASCADE_RUNTIME_FILES,
    H120_RUNTIME_FILES,
    FrozenH120Runtime,
    file_record,
    score_h120_daily,
    verify_frozen_bundle,
)
from src.training.xgboost_pipeline import SigmoidCalibration


class FakePredictor:
    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {"p_entry_calibrated": frame["signal"].to_numpy(float)},
            index=frame.index,
        )


class FakeCascade:
    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        return frame["p_h120"].to_numpy(float)


def contract(feature_columns: list[str] | None = None) -> dict[str, object]:
    return {
        "feature_version": "wave_ignition_v2",
        "feature_columns": feature_columns or ["signal"],
        "probability_columns": ["p_h120"],
        "continuous_columns": [],
        "candidate_mode": "universe",
        "hard_gate_enabled": False,
        "shortlist_k": 10,
        "strength_weight": 0.0,
        "decision_threshold": 0.5,
    }


def runtime() -> FrozenH120Runtime:
    return FrozenH120Runtime(
        manifest={
            "deployment_status": "shadow_candidate_requires_new_holdout",
            "contract": contract(),
        },
        predictor=FakePredictor(),  # type: ignore[arg-type]
        cascade_model=FakeCascade(),  # type: ignore[arg-type]
        cascade_calibrator=SigmoidCalibration(coefficient=1.0, intercept=0.0),
    )


def daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [f"S{index:02d}" for index in range(12)],
            "date": pd.Timestamp("2026-08-24"),
            "feature_version": "wave_ignition_v2",
            "feature_ready": [True] * 11 + [False],
            "quality_score": 90.0,
            "signal": np.linspace(0.05, 0.95, 12),
        }
    )


def test_daily_scoring_is_deterministic_and_never_authorizes_shadow_trades() -> None:
    first, summary = score_h120_daily(runtime(), daily_frame())
    second, _ = score_h120_daily(runtime(), daily_frame())

    pd.testing.assert_frame_equal(first, second)
    assert summary == {
        "as_of_date": "2026-08-24",
        "input_rows_for_date": 12,
        "eligible_rows": 11,
        "excluded_rows": 1,
        "shortlist_rows": 10,
        "above_threshold_rows": 5,
    }
    assert first.iloc[0]["symbol"] == "S10"
    assert first["selected_top_k"].sum() == 10
    assert not first["trade_authorized"].any()


def test_daily_scoring_fails_closed_on_schema_and_duplicate_keys() -> None:
    wrong_version = daily_frame()
    wrong_version["feature_version"] = "wave_ignition_v3"
    with pytest.raises(RuntimeError, match="feature version mismatch"):
        score_h120_daily(runtime(), wrong_version)

    duplicate = pd.concat([daily_frame(), daily_frame().iloc[[0]]], ignore_index=True)
    with pytest.raises(RuntimeError, match="duplicate symbol/date"):
        score_h120_daily(runtime(), duplicate)


def _write_runtime_tree(root: Path) -> tuple[Path, Path, Path]:
    h120_run = root / "models/h120/run"
    cascade_run = root / "models/cascade/run"
    source_lock = root / "locks/cascade.json"
    for relative in H120_RUNTIME_FILES:
        path = h120_run / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("payload", encoding="utf-8")
    for relative in CASCADE_RUNTIME_FILES:
        path = cascade_run / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("payload", encoding="utf-8")
    source_lock.parent.mkdir(parents=True, exist_ok=True)
    source_lock.write_text("{}", encoding="utf-8")
    (h120_run / "model_manifest.json").write_text(
        json.dumps({"architecture": {"ensemble": False}}), encoding="utf-8"
    )
    (h120_run / "model/features.json").write_text(
        json.dumps({"feature_columns": ["signal"]}), encoding="utf-8"
    )
    (cascade_run / "model_manifest.json").write_text(
        json.dumps(
            {
                "probability_columns": ["p_h120"],
                "continuous_columns": [],
                "meta_model": "logistic",
                "threshold_calibrated": 0.5,
            }
        ),
        encoding="utf-8",
    )
    return h120_run, cascade_run, source_lock


def test_bundle_verification_detects_artifact_tampering(tmp_path: Path) -> None:
    h120_run, cascade_run, source_lock = _write_runtime_tree(tmp_path)
    paths = [
        *(h120_run / relative for relative in H120_RUNTIME_FILES),
        *(cascade_run / relative for relative in CASCADE_RUNTIME_FILES),
        source_lock,
    ]
    manifest = {
        "schema_version": 1,
        "bundle_id": "test",
        "deployment_status": "shadow_candidate_requires_new_holdout",
        "artifacts": {
            "h120_model_run": "models/h120/run",
            "cascade_model_run": "models/cascade/run",
            "source_lock": "locks/cascade.json",
        },
        "contract": contract(),
        "files": [
            file_record(path, tmp_path, role="test") for path in paths
        ],
    }
    manifest_path = tmp_path / "bundle.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    verified, artifacts = verify_frozen_bundle(
        manifest_path, project_root=tmp_path
    )
    assert verified["bundle_id"] == "test"
    assert artifacts["h120_model_run"] == h120_run

    (h120_run / "model/entry_classifier.json").write_text(
        "PAYLOAD", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        verify_frozen_bundle(manifest_path, project_root=tmp_path)
