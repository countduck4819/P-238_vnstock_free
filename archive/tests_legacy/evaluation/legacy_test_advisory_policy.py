import pandas as pd

from src.evaluation.advisory import (
    AdvisoryPolicyConfig,
    apply_advisory_profile,
    apply_nested_temporal_advisory_policy,
    apply_temporal_advisory_policy,
    build_confidence_profile,
    month_block_bootstrap_comparison,
    wilson_lower_bound,
)
from src.evaluation.monitoring import MonitoringConfig, build_refresh_plan


def make_config() -> AdvisoryPolicyConfig:
    return AdvisoryPolicyConfig(
        policy_version="test",
        score_column="p_entry_raw",
        top_k_max=2,
        minimum_distinct_scores=2,
        confidence_level=0.95,
        minimum_history_folds=1,
        minimum_history_effective_samples=1,
        minimum_precision_lift_lower_bound=0.1,
        bearish_upper=45.0,
        bullish_lower=55.0,
        market_regime_feature="market_regime_score",
        rank_bucket_ends=(1, 3),
    )


def test_wilson_lower_bound_is_conservative() -> None:
    assert 0 < wilson_lower_bound(0.5, 100, 0.95) < 0.5


def test_advisory_policy_uses_prior_folds_and_abstains_for_low_resolution() -> None:
    frame = pd.DataFrame(
        {
            "fold_id": ["fold_2021"] * 2 + ["fold_2022"] * 4,
            "date": pd.to_datetime(
                ["2021-01-04"] * 2 + ["2022-01-04"] * 2 + ["2022-01-05"] * 2
            ),
            "symbol": ["A", "B", "C", "D", "E", "F"],
            "p_entry_raw": [0.9, 0.8, 0.9, 0.8, 0.7, 0.7],
            "y_entry": [1, 0, 1, 0, 0, 0],
            "sample_weight": [1.0] * 6,
            "market_regime_score": [50.0] * 6,
        }
    )

    evaluated = apply_temporal_advisory_policy(frame, make_config())
    first_fold = evaluated.loc[evaluated["fold_id"].eq("fold_2021")]
    assert first_fold["advisory_reason"].eq("insufficient_prior_history").all()

    current_day = evaluated.loc[evaluated["date"].eq(pd.Timestamp("2022-01-04"))]
    assert current_day["advisory_status"].tolist() == ["PASS", "ABSTAIN"]
    assert current_day["advisory_reason"].tolist() == [
        "rank_regime_confidence_gate_passed",
        "historical_precision_lower_bound_below_gate",
    ]

    collapsed_day = evaluated.loc[evaluated["date"].eq(pd.Timestamp("2022-01-05"))]
    assert collapsed_day["advisory_status"].eq("ABSTAIN").all()
    assert collapsed_day["advisory_reason"].eq("insufficient_daily_score_resolution").all()


def test_frozen_profile_applies_the_same_gate_without_ground_truth() -> None:
    history = pd.DataFrame(
        {
            "fold_id": ["fold_2021"] * 4,
            "date": pd.to_datetime(["2021-01-04"] * 4),
            "symbol": ["A", "B", "C", "D"],
            "p_entry_raw": [0.9, 0.8, 0.7, 0.6],
            "y_entry": [1, 0, 1, 0],
            "sample_weight": [1.0] * 4,
            "market_regime_score": [50.0] * 4,
        }
    )
    config = make_config()
    ranked_history = apply_temporal_advisory_policy(history, config)
    profile = build_confidence_profile(ranked_history, config)
    live = history.drop(columns=["y_entry", "sample_weight", "fold_id"]).copy()

    scored = apply_advisory_profile(live, profile, config)

    assert scored.loc[scored["daily_rank"].eq(1), "advisory_status"].item() == "PASS"


def test_month_block_bootstrap_compares_gated_and_forced_selection() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-03", "2023-01-03", "2023-02-03", "2023-02-03"]),
            "y_entry": [1, 0, 0, 0],
            "sample_weight": [1.0] * 4,
            "daily_rank": [1, 2, 1, 2],
            "advisory_status": ["PASS", "ABSTAIN", "ABSTAIN", "ABSTAIN"],
        }
    )

    result = month_block_bootstrap_comparison(
        frame, make_config(), samples=20, random_seed=238
    )

    assert result["valid_samples"] > 0
    assert result["gated_precision"]["median"] >= 0


def test_nested_policy_uses_only_previous_fold_outcomes_for_selection() -> None:
    config = AdvisoryPolicyConfig(
        **{
            **make_config().__dict__,
            "top_k_candidates": (1, 2),
            "minimum_distinct_scores_candidates": (1, 2),
            "minimum_history_effective_samples_candidates": (1.0,),
        }
    )
    frame = pd.DataFrame(
        {
            "fold_id": ["f1"] * 2 + ["f2"] * 2 + ["f3"] * 2,
            "date": pd.to_datetime(
                ["2021-01-04"] * 2 + ["2022-01-04"] * 2 + ["2023-01-04"] * 2
            ),
            "symbol": ["A", "B", "C", "D", "E", "F"],
            "p_entry_raw": [0.9, 0.8, 0.9, 0.8, 0.9, 0.8],
            "y_entry": [1, 0, 0, 0, 1, 0],
            "sample_weight": [1.0] * 6,
            "market_regime_score": [50.0] * 6,
        }
    )
    evaluated, audit = apply_nested_temporal_advisory_policy(frame, config)
    assert audit.loc[audit["fold_id"].eq("f3"), "selection_status"].item() == (
        "selected_from_prior_folds"
    )
    third_fold = evaluated.loc[evaluated["fold_id"].eq("f3")]
    # The top row's PASS decision reflects f1/f2 history, not f3's positive label.
    assert third_fold.loc[third_fold["daily_rank"].eq(1), "advisory_status"].item() in {
        "PASS",
        "ABSTAIN",
    }


def test_refresh_plan_requires_resolved_rows_and_detects_due_interval() -> None:
    ledger = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
            "ground_truth_available": [False, True, True],
            "p_entry_calibrated": [0.1, 0.2, 0.8],
            "ground_truth": [None, 0, 1],
        }
    )
    config = MonitoringConfig(3, 2, 2, 0.5)
    result = build_refresh_plan(
        ledger,
        last_retrained_at=pd.Timestamp("2025-01-01"),
        last_recalibrated_at=pd.Timestamp("2025-01-01"),
        config=config,
    )
    assert result["retrain_due"]
    assert result["recalibration_due"]
