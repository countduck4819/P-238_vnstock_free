import numpy as np
import pandas as pd

from src.models.wave_cascade import (
    causal_cascade_oof,
    find_duplicate_probability_heads,
    fit_cascade_calibration,
    fit_cascade_model,
)


def make_frame() -> pd.DataFrame:
    rows = []
    for fold_number, year in enumerate((2020, 2021, 2022, 2023), start=1):
        for symbol, target in (("AAA", 1), ("BBB", 0)):
            rows.append(
                {
                    "fold_id": f"fold_{fold_number}",
                    "symbol": symbol,
                    "date": pd.Timestamp(f"{year}-01-02"),
                    "y_actionable": target,
                    "sample_weight": 1.0,
                    "p_v6_trend": 0.8 if target else 0.2,
                    "p_h20": 0.85 if target else 0.15,
                    "p_h60": 0.7 if target else 0.3,
                    "p_h120": 0.75 if target else 0.25,
                    "p_break_h120": 0.1 if target else 0.7,
                    "strength_h120": 0.8 if target else 0.1,
                }
            )
    return pd.DataFrame(rows)


def test_cascade_oof_is_prior_fold_only_and_handles_missing_columns() -> None:
    frame = make_frame()
    frame.loc[frame["fold_id"].eq("fold_3"), "p_h60"] = np.nan
    scored, metrics = causal_cascade_oof(
        frame,
        probability_columns=("p_v6_trend", "p_h20", "p_h60", "p_h120"),
        continuous_columns=("strength_h120",),
    )
    assert len(metrics) == 3
    assert scored.loc[scored["fold_id"].eq("fold_1"), "p_cascade"].isna().all()
    assert scored.loc[scored["fold_id"].eq("fold_2"), "p_cascade"].notna().all()


def test_deployment_model_exposes_missing_indicators() -> None:
    frame = make_frame()
    model = fit_cascade_model(
        frame,
        probability_columns=("p_v6_trend", "p_h20", "p_h60", "p_h120"),
        continuous_columns=("strength_h120",),
    )
    inference = frame.iloc[:2].copy()
    inference.loc[inference.index[0], "p_h60"] = np.nan
    probability = model.predict_proba(inference)
    assert probability.shape == (2,)
    assert np.isfinite(probability).all()


def test_causal_calibration_is_temporal_and_monotonic() -> None:
    frame = make_frame()
    scored, metrics = causal_cascade_oof(
        frame,
        probability_columns=("p_v6_trend", "p_h20", "p_h60", "p_h120"),
        continuous_columns=("strength_h120",),
    )
    assert len(metrics) == 3
    assert scored.loc[scored["cascade_calibration_is_temporal"], "p_cascade_calibrated"].notna().all()
    valid = scored["p_cascade"].notna()
    calibration = fit_cascade_calibration(scored.loc[valid])
    calibrated = calibration.predict(scored.loc[valid, "p_cascade"])
    assert np.isfinite(calibrated).all()
    assert np.argsort(scored.loc[valid, "p_cascade"].to_numpy()).tolist() == np.argsort(calibrated).tolist()


def test_hist_gradient_boosting_and_positive_weight_are_supported() -> None:
    frame = make_frame()
    scored, metrics = causal_cascade_oof(
        frame,
        probability_columns=("p_v6_trend", "p_h20", "p_h60", "p_h120"),
        continuous_columns=("strength_h120",),
        model_kind="hist_gradient_boosting",
        positive_class_weight=2.0,
    )
    assert len(metrics) == 3
    assert scored["p_cascade"].notna().sum() == 6
    model = fit_cascade_model(
        frame,
        probability_columns=("p_v6_trend", "p_h20", "p_h60", "p_h120"),
        continuous_columns=("strength_h120",),
        model_kind="hist_gradient_boosting",
        positive_class_weight=2.0,
    )
    assert model.estimator_kind == "hist_gradient_boosting"
    assert np.isfinite(model.predict_proba(frame)).all()


def test_duplicate_probability_heads_are_rejected_at_inference() -> None:
    frame = make_frame()
    model = fit_cascade_model(
        frame,
        probability_columns=("p_h20", "p_h120"),
        continuous_columns=(),
    )
    inference = pd.concat([frame] * 3, ignore_index=True)
    inference["p_h20"] = inference["p_h120"]
    assert find_duplicate_probability_heads(
        inference, ("p_h20", "p_h120")
    ) == [("p_h20", "p_h120")]
    with np.testing.assert_raises_regex(ValueError, "duplicate probability heads"):
        model.predict_proba(inference)
