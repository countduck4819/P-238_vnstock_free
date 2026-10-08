"""Train and calibrate the XGBoost + CatBoost V6 ensemble candidate."""

from _run_v6_candidate import run_candidate


if __name__ == "__main__":
    run_candidate(
        "xgb_cat_ensemble", ("xgb", "cat"), default_trials=15, default_device="cuda"
    )
