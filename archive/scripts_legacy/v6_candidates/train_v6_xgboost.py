"""Train the isolated XGBoost V6 benchmark candidate."""

from _run_v6_candidate import run_candidate


if __name__ == "__main__":
    run_candidate("xgboost", ("xgb",), default_trials=15, default_device="cuda")
