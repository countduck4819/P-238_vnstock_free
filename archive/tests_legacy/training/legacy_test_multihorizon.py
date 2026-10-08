import pandas as pd

from src.models.multihorizon import causal_meta_oof


def test_causal_meta_oof_does_not_score_first_fold_without_history():
    rows = []
    for fold, values in [("fold_2020", [0, 1]), ("fold_2021", [0, 1]), ("fold_2022", [1, 0])]:
        for idx, target in enumerate(values):
            rows.append(
                {
                    "fold_id": fold,
                    "symbol": f"S{idx}",
                    "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=idx),
                    "y_entry": target,
                    "sample_weight": 1.0,
                    "p_entry_calibrated": 0.1 + 0.8 * target,
                }
            )
    frame = pd.DataFrame(rows)
    result, metrics = causal_meta_oof({"h20": frame, "h60": frame, "h120": frame})
    assert result.loc[result["fold_id"].eq("fold_2020"), "p_meta"].isna().all()
    assert set(metrics["fold_id"]) == {"fold_2021", "fold_2022"}
