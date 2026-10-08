import numpy as np
import pandas as pd
import pytest

from src.models.hierarchical_surge import (
    HierarchicalSurgeConfig,
    causal_hierarchical_oof,
    join_expert_oof,
    selection_metrics,
)


def make_expert_frame(name: str) -> pd.DataFrame:
    rows = []
    for fold_index, fold in enumerate(("fold_2020", "fold_2021", "fold_2022")):
        for day in range(4):
            for stock in range(3):
                target = int(stock == (day + fold_index) % 3)
                rows.append(
                    {
                        "fold_id": fold,
                        "symbol": f"S{stock}",
                        "date": pd.Timestamp("2020-01-01")
                        + pd.Timedelta(days=fold_index * 20 + day),
                        "y_entry": target,
                        "sample_weight": 1.0,
                        "p_entry_raw": 0.15 + 0.65 * target + 0.02 * stock,
                        "p_entry_calibrated_temporal": 0.2 + 0.5 * target,
                    }
                )
    result = pd.DataFrame(rows)
    if name == "technical":
        result["p_entry_raw"] = result["p_entry_raw"] * 0.9 + 0.03
    return result


def config() -> HierarchicalSurgeConfig:
    return HierarchicalSurgeConfig(
        top_k=2,
        technical_gate_quantiles=(0.5, 0.75),
        minimum_gate_day_coverage=0.2,
        minimum_gate_history_folds=1,
        meta_c=1.0,
    )


def test_join_experts_rejects_mismatched_coverage():
    stock = make_expert_frame("stock")
    technical = make_expert_frame("technical").iloc[1:].copy()
    with pytest.raises(ValueError, match="key coverage differs"):
        join_expert_oof(
            stock.rename(
                columns={
                    "p_entry_raw": "p_stock_raw",
                    "p_entry_calibrated_temporal": "p_stock_calibrated_temporal",
                }
            ),
            technical.rename(
                columns={
                    "p_entry_raw": "p_technical_raw",
                    "p_entry_calibrated_temporal": "p_technical_calibrated_temporal",
                }
            ),
        )


def test_hierarchical_oof_is_nested_and_first_fold_has_no_meta_score():
    stock = make_expert_frame("stock").rename(
        columns={
            "p_entry_raw": "p_stock_raw",
            "p_entry_calibrated_temporal": "p_stock_calibrated_temporal",
        }
    )
    technical = make_expert_frame("technical").rename(
        columns={
            "p_entry_raw": "p_technical_raw",
            "p_entry_calibrated_temporal": "p_technical_calibrated_temporal",
        }
    )
    joined = join_expert_oof(stock, technical)
    result, fold_metrics, gate_audit = causal_hierarchical_oof(joined, config())

    first_fold = result["fold_id"].eq("fold_2020")
    assert result.loc[first_fold, "p_h0"].notna().all()
    assert result.loc[first_fold, "p_h2"].isna().all()
    assert result.loc[first_fold, "p_h3"].isna().all()
    assert set(fold_metrics["candidate"]) == {"H0", "H1", "H2", "H3"}
    assert not gate_audit.empty
    selected_per_day = result.loc[result["selected_h0"]].groupby("date").size()
    assert selected_per_day.le(2).all()


def test_later_fold_target_cannot_change_earlier_meta_prediction():
    stock = make_expert_frame("stock").rename(
        columns={
            "p_entry_raw": "p_stock_raw",
            "p_entry_calibrated_temporal": "p_stock_calibrated_temporal",
        }
    )
    technical = make_expert_frame("technical").rename(
        columns={
            "p_entry_raw": "p_technical_raw",
            "p_entry_calibrated_temporal": "p_technical_calibrated_temporal",
        }
    )
    joined = join_expert_oof(stock, technical)
    baseline, _, _ = causal_hierarchical_oof(joined, config())
    changed = joined.copy()
    future = changed["fold_id"].eq("fold_2022")
    changed.loc[future, "y_entry"] = 1 - changed.loc[future, "y_entry"]
    altered, _, _ = causal_hierarchical_oof(changed, config())
    mask = baseline["fold_id"].eq("fold_2021")
    np.testing.assert_allclose(
        baseline.loc[mask, "p_h2"], altered.loc[mask, "p_h2"], equal_nan=True
    )


def test_selection_metrics_handles_zero_event_weights():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-01"]),
            "y_entry": [1, 0],
            "sample_weight": [0.0, 0.0],
            "selected": [True, False],
        }
    )
    metrics = selection_metrics(frame)
    assert metrics["base_rate"] == 0.5
    assert metrics["daily_precision_at_k"] == 1.0


def test_selection_metrics_handles_empty_matched_slice():
    frame = pd.DataFrame(
        columns=["date", "y_entry", "sample_weight", "selected"]
    )
    metrics = selection_metrics(frame)
    assert metrics["days_total"] == 0.0
    assert metrics["day_coverage"] == 0.0
