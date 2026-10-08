from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.evaluation.wave_model import (
    EvaluationConfig,
    cluster_bootstrap_daily_top_k,
    daily_top_k_metrics,
    evaluate_acceptance_gates,
    evaluate_predictions,
    paired_daily_ranking_comparison,
    verify_artifact,
)


def make_config() -> EvaluationConfig:
    return EvaluationConfig(
        evaluation_version="test_eval",
        random_seed=238,
        bootstrap_samples=5,
        confidence_level=0.95,
        minimum_segment_rows=10,
        calibration_bins=5,
        top_fractions=(0.05, 0.10),
        industry_column="icb_level_2_name",
        market_regime_feature="market_regime_score",
        bearish_upper=-0.25,
        bullish_lower=0.25,
        liquidity_feature="log_median_turnover_20",
        liquidity_quantiles=(0.2, 0.8),
        acceptance_gates={
            "minimum_oof_average_precision_lift": 1.5,
            "minimum_fold_average_precision_lift": 1.5,
            "minimum_fold_roc_auc": 0.55,
            "minimum_weighted_precision_at_5pct": 0.12,
            "minimum_temporal_threshold_f1": 0.05,
            "minimum_strength_spearman": 0.15,
            "minimum_fold_strength_spearman": 0.0,
            "minimum_strength_terminal_return_spearman": 0.2,
            "minimum_strength_ranking_precision_lift": 1.0,
            "minimum_brier_skill_score": 0.0,
            "maximum_expected_calibration_error": 0.02,
            "minimum_calibration_slope": 0.8,
            "maximum_calibration_slope": 1.2,
            "minimum_backtest_sharpe_ratio": 0.5,
            "minimum_backtest_excess_cumulative_return": 0.0,
            "minimum_backtest_trades": 100,
            "maximum_backtest_drawdown": -0.25,
            "final_test_required_for_deployment": True,
            "all_gates_required": True,
        },
        backtest={},
    )


def make_predictions() -> pd.DataFrame:
    rows = 200
    index = np.arange(rows)
    target = (index % 5 == 0).astype(int)
    probability = np.where(target == 1, 0.8, 0.1) + (index % 7) * 0.005
    strength = np.where(target == 1, 0.5 + (index % 10) / 50, np.nan)
    return pd.DataFrame(
        {
            "symbol": [f"S{value % 20:02d}" for value in index],
            "date": pd.Timestamp("2023-01-02") + pd.to_timedelta(index // 20, unit="D"),
            "fold_id": np.where(index < 100, "fold_2022", "fold_2023"),
            "y_entry": target,
            "y_strength": strength,
            "sample_weight": np.ones(rows),
            "p_entry_calibrated": probability,
            "p_strength": np.where(target == 1, strength + 0.01, 0.30),
            "icb_level_2_name": np.where(index % 2 == 0, "Industry A", "Industry B"),
            "market_regime_score": np.select(
                [index % 3 == 0, index % 3 == 1], [-0.5, 0.5], default=0.0
            ),
            "log_median_turnover_20": np.log1p(index + 1),
        }
    )


def test_verify_artifact_detects_tampering(tmp_path: Path) -> None:
    payload_path = tmp_path / "model.json"
    payload_path.write_text("frozen", encoding="utf-8")
    digest = hashlib.sha256(b"frozen").hexdigest()
    manifest = {
        "immutable": True,
        "files": [
            {
                "path": "model.json",
                "size_bytes": payload_path.stat().st_size,
                "sha256": digest,
            }
        ],
    }
    (tmp_path / "artifact_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    assert verify_artifact(tmp_path)["immutable"] is True
    payload_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(RuntimeError, match="size mismatch|checksum mismatch"):
        verify_artifact(tmp_path)


def test_evaluation_generates_segments_ranking_and_bootstrap() -> None:
    report, tables = evaluate_predictions(
        make_predictions(), "p_entry_calibrated", 0.5, make_config()
    )

    assert report["classification"]["average_precision"] == pytest.approx(1.0)
    assert report["strength_positive_rows_only"]["spearman"] > 0.9
    assert set(tables) == {
        "daily_ranking",
        "daily_top_k",
        "calibration",
        "segments",
        "strength_bins",
        "strength_ranking",
    }
    assert not tables["strength_ranking"].empty
    assert set(tables["segments"]["segment_type"]) >= {
        "fold_id",
        "calendar_year",
        "market_regime",
        "liquidity_bucket",
        "icb_level_2_name",
    }
    assert report["cluster_bootstrap_by_date"]["average_precision"]["lower"] > 0.9
    assert np.isfinite(report["daily_top_k_bootstrap_by_date"]["precision_at_k"]["lower"])


def test_daily_top_k_handles_small_equal_large_universes_and_ties() -> None:
    small = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01"] * 2),
            "symbol": ["BBB", "AAA"],
            "score": [0.5, 0.5],
            "y_entry": [0, 1],
            "sample_weight": [1.0, 1.0],
        }
    )
    equal = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02"] * 10),
            "symbol": [f"E{value:02d}" for value in range(10)],
            "score": list(range(10, 0, -1)),
            "y_entry": [1] + [0] * 9,
            "sample_weight": [1.0] * 10,
        }
    )
    large = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-03"] * 12),
            "symbol": [f"L{value:02d}" for value in range(12)],
            "score": list(range(12, 0, -1)),
            "y_entry": [1] + [0] * 11,
            "sample_weight": [1.0] * 12,
        }
    )
    daily = daily_top_k_metrics(pd.concat([small, equal, large]), "score", k=10)

    assert daily["selected_rows"].tolist() == [2, 10, 10]
    assert daily.loc[0, "precision_at_k"] == pytest.approx(0.5)
    assert daily.loc[0, "hit_rate_at_k"] == 1.0
    assert daily.loc[2, "universe_rows"] == 12


def test_daily_top_k_bootstrap_and_paired_comparison_use_dates() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01"] * 2 + ["2025-01-02"] * 2),
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "score": [0.9, 0.1, 0.8, 0.2],
            "y_entry": [1, 0, 1, 0],
            "sample_weight": [1.0] * 4,
        }
    )
    bootstrap = cluster_bootstrap_daily_top_k(
        frame, "score", k=1, samples=5, confidence_level=0.95, random_seed=238
    )
    assert bootstrap["precision_at_k"]["estimate"] == pytest.approx(1.0)

    champion = daily_top_k_metrics(frame, "score", k=1)
    challenger = champion.copy()
    challenger["date"] = pd.to_datetime(["2025-01-02", "2025-01-03"])
    challenger["precision_at_k"] = [0.0, 1.0]
    paired, summary = paired_daily_ranking_comparison(champion, challenger)
    assert paired["date"].dt.strftime("%Y-%m-%d").tolist() == ["2025-01-02"]
    assert summary["paired_dates"] == 1
    assert summary["mean_delta_precision_at_k"] == pytest.approx(-1.0)


def test_moving_block_bootstrap_paired_daily_uses_requested_block_size() -> None:
    from src.evaluation.wave_model import moving_block_bootstrap_paired_daily

    paired = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-02", periods=8, freq="B"),
            "delta_precision_at_k": [0.0, 0.0, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2],
        }
    )
    result = moving_block_bootstrap_paired_daily(
        paired, "precision_at_k", samples=100, random_seed=238, block_size=3
    )
    assert result["estimate"] == pytest.approx(0.1125)
    assert result["samples"] == 100
    assert result["block_size_dates"] == 3


def test_acceptance_gates_fail_closed_for_unstable_model() -> None:
    report, tables = evaluate_predictions(
        make_predictions(), "p_entry_calibrated", 0.5, make_config()
    )
    report["strength_positive_rows_only"]["spearman"] = 0.12
    training_metrics = {"temporal_calibration_audit": {"metrics": {"f1": 0.0}}}
    artifact_manifest = {
        "deployment_eligible": False,
        "final_test_evaluated": False,
    }

    acceptance = evaluate_acceptance_gates(
        report,
        tables["segments"],
        training_metrics,
        artifact_manifest,
        make_config(),
    )

    failed = {check["gate"] for check in acceptance["checks"] if not check["passed"]}
    assert "temporal_threshold_f1" in failed
    assert "strength_spearman" in failed
    assert "final_test_evaluated" in failed
    assert acceptance["pre_final_gates_passed"] is False
    assert acceptance["deployment_eligible"] is False
