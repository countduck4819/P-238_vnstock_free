"""Run a reproducible research-only inner walk-forward search for the H120 ranker."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.train_h120_ranker import (  # noqa: E402
    DEFAULT_DATASET_RUN,
    DEFAULT_GROUPS,
    load_dataset,
    selected_folds,
)
from src.evaluation.wave_model import daily_top_k_metrics  # noqa: E402
from src.training.h120_experiment_protocol import H120ExperimentProtocol  # noqa: E402
from src.training.h120_ranker import H120RankerConfig, fit_h120_ranker_fold  # noqa: E402
from src.training.xgboost_pipeline import subset_by_keys  # noqa: E402

DEFAULT_TUNING_CONFIG = Path("configs/experiments/h120_ranker_tuning_generation_v2.yaml")
DEFAULT_MODEL_CONFIG = Path("configs/experiments/h120_ranker_stock_primitives_v1.yaml")
DEFAULT_PROTOCOL = Path("configs/experiments/h120_ranker_generation_v2.yaml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-run", type=Path, default=DEFAULT_DATASET_RUN)
    parser.add_argument("--feature-groups", type=Path, default=DEFAULT_GROUPS)
    parser.add_argument("--model-config", type=Path, default=DEFAULT_MODEL_CONFIG)
    parser.add_argument("--tuning-config", type=Path, default=DEFAULT_TUNING_CONFIG)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--trials", type=int, default=4)
    parser.add_argument("--folds", default="fold_2020,fold_2021,fold_2022,fold_2023")
    parser.add_argument(
        "--output", type=Path, default=Path("experiments/h120_improvement/E08_generation_v2_inner_tuning")
    )
    return parser.parse_args()


def log_uniform(random: np.random.Generator, low: float, high: float) -> float:
    return float(np.exp(random.uniform(np.log(low), np.log(high))))


def sample_parameters(random: np.random.Generator) -> dict[str, float | int]:
    return {
        "max_depth": int(random.choice([2, 3, 4, 5])),
        "min_child_weight": log_uniform(random, 10.0, 100.0),
        "learning_rate": float(random.uniform(0.02, 0.06)),
        "subsample": float(random.uniform(0.6, 0.9)),
        "colsample_bytree": float(random.uniform(0.5, 0.9)),
        "reg_lambda": log_uniform(random, 2.0, 20.0),
        "reg_alpha": float(random.uniform(0.0, 0.5)),
        "gamma": float(random.uniform(0.0, 0.5)),
    }


def evaluate_trial(
    dataset: pd.DataFrame,
    dataset_run: Path,
    folds: list[str],
    feature_columns: list[str],
    config: H120RankerConfig,
) -> dict[str, Any]:
    fold_metrics: dict[str, dict[str, float]] = {}
    for fold_id in folds:
        split = dataset_run / "splits" / fold_id
        train = subset_by_keys(dataset, split / "train_keys.parquet")
        validation = subset_by_keys(dataset, split / "validation_keys.parquet")
        _, prediction = fit_h120_ranker_fold(train, validation, feature_columns, config)
        prediction["sample_weight"] = validation["sample_weight"].to_numpy()
        daily = daily_top_k_metrics(prediction, "rank_score", k=10)
        fold_metrics[fold_id] = {
            "precision_at_10": float(daily["precision_at_k"].mean()),
            "map_at_10": float(daily["map_at_k"].mean()),
            "ndcg_at_10": float(daily["ndcg_at_k"].mean()),
        }
    precision = [metrics["precision_at_10"] for metrics in fold_metrics.values()]
    ranking_objective = [
        metrics["precision_at_10"] + metrics["map_at_10"] + metrics["ndcg_at_10"]
        for metrics in fold_metrics.values()
    ]
    return {
        "fold_metrics": fold_metrics,
        "mean_precision_at_10": float(np.mean(precision)),
        "worst_fold_precision_at_10": float(np.min(precision)),
        "mean_ranking_objective": float(np.mean(ranking_objective)),
    }


def main() -> int:
    args = parse_args()
    if args.trials <= 0:
        raise ValueError("trials must be positive.")
    tuning = yaml.safe_load(args.tuning_config.read_text(encoding="utf-8"))
    protocol = H120ExperimentProtocol.from_yaml(args.protocol)
    if tuning["feature_group"] != protocol.feature_group:
        raise ValueError("Tuning config feature group does not match the frozen protocol.")
    feature_columns = protocol.validate_feature_group(args.feature_groups)
    label_config = Path(protocol.raw["label_contract"]["config"])
    protocol.validate_label_config(ROOT / label_config if not label_config.is_absolute() else label_config)
    dataset_run = args.dataset_run.resolve()
    protocol.validate_dataset_manifest(dataset_run)
    folds = selected_folds(dataset_run, args.folds)
    protocol.validate_selection_folds(folds)
    if int(tuning["search"]["random_seed"]) != protocol.raw["selection_contract"]["tuning_seed"]:
        raise ValueError("Tuning seed does not match the frozen protocol.")
    base_config = H120RankerConfig.from_yaml(args.model_config)
    dataset = load_dataset(dataset_run, feature_columns)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    trials_path = output / "trials.jsonl"
    if trials_path.exists():
        raise FileExistsError(f"{trials_path} already exists; choose a new output path.")
    random = np.random.default_rng(int(tuning["search"]["random_seed"]))
    records: list[dict[str, Any]] = []
    with trials_path.open("x", encoding="utf-8") as handle:
        for trial_id in range(args.trials):
            parameters = sample_parameters(random)
            candidate = replace(
                base_config,
                ranker={**base_config.ranker, **parameters},
            )
            record: dict[str, Any] = {
                "trial_id": trial_id,
                "parameters": parameters,
                "folds": folds,
                "status": "running",
            }
            try:
                record.update(
                    evaluate_trial(dataset, dataset_run, folds, feature_columns, candidate)
                )
                record["status"] = "completed"
            except Exception as exc:  # Preserve failed trials for auditability.
                record["status"] = "failed"
                record["error"] = repr(exc)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            records.append(record)
    completed = [record for record in records if record["status"] == "completed"]
    ranked = sorted(completed, key=lambda record: record["mean_ranking_objective"], reverse=True)
    summary = {
        "status": "research_only_inner_search_not_outer_evaluation",
        "protocol_status": tuning["status"],
        "protocol": protocol.to_manifest(),
        "trials_requested": args.trials,
        "trials_completed": len(completed),
        "folds": folds,
        "best_trial": ranked[0] if ranked else None,
        "not_trade_authorized": True,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
