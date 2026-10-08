"""Train the lightly-tuned LightGBM V6 benchmark candidate."""

from _run_v6_candidate import run_candidate


if __name__ == "__main__":
    run_candidate("lightgbm", ("lgb",), default_trials=5)
