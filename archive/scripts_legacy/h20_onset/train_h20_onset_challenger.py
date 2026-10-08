"""Train XGBoost-only wave entry and conditional strength models."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from xgboost import XGBClassifier, XGBRegressor  # noqa: E402

from src.training import (  # noqa: E402
    XGBoostTrainingConfig,
    classification_metrics,
    fit_sigmoid_calibration,
    median_best_round,
    regression_metrics,
    select_f1_threshold,
    subset_by_keys,
    temporal_calibration_predictions,
    weighted_class_ratio,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("data/training/wave_ignition/wave_dataset_v1"),
    )
    parser.add_argument("--dataset-run", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/wave_ignition_xgboost_v6_trend20.yaml"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("models/wave_ignition"),
    )
    parser.add_argument(
        "--cv-only",
        action="store_true",
        help="Create OOF evaluation but do not fit deployable final models.",
    )
    parser.add_argument(
        "--evaluate-final-test",
        action="store_true",
        help="Explicitly open and score the untouched final test split.",
    )
    parser.add_argument(
        "--anchor-dataset-run",
        type=Path,
        help=(
            "Optional second dataset run whose fold validation keys receive "
            "causal predictions from the fold-local model. Used to export a "
            "shared-population OOF table for cascade training."
        ),
    )
    return parser.parse_args()


def resolve_dataset_run(explicit_run: Path | None, root: Path) -> Path:
    if explicit_run is not None:
        return explicit_run.resolve()
    latest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    return Path(latest["run_directory"]).resolve()


def load_dataset(run: Path) -> pd.DataFrame:
    partitions = sorted(run.glob("dataset/year=*/dataset.parquet"))
    if not partitions:
        raise RuntimeError(f"No dataset partitions found in {run}")
    frame = pd.concat((pd.read_parquet(path) for path in partitions), ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame.duplicated(["symbol", "date"]).any():
        raise RuntimeError("Training store contains duplicate symbol/date keys.")
    frame.sort_values(["date", "symbol"], kind="stable", inplace=True)
    frame.set_index(["symbol", "date"], verify_integrity=True, inplace=True)
    return frame


def write_json(payload: dict[str, Any], path: Path) -> None:
    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return None if not np.isfinite(value) else float(value)
        if isinstance(value, float) and not np.isfinite(value):
            return None
        if isinstance(value, (pd.Timestamp, datetime)):
            return value.isoformat()
        return value

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            normalize(payload), ensure_ascii=False, indent=2, allow_nan=False
        ),
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def feature_matrix(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    matrix = frame.loc[:, columns].astype("float32")
    finite_or_missing = np.isfinite(matrix.to_numpy()) | matrix.isna().to_numpy()
    if not finite_or_missing.all():
        raise RuntimeError("Feature matrix contains non-finite values.")
    return matrix


def best_round(model: XGBClassifier | XGBRegressor, configured: int) -> int:
    try:
        return int(model.best_iteration) + 1
    except (AttributeError, TypeError):
        return int(configured)


def classifier_parameters(
    config: XGBoostTrainingConfig,
    class_ratio: float,
    *,
    final_rounds: int | None = None,
) -> dict[str, Any]:
    parameters = dict(config.classifier)
    if final_rounds is not None:
        parameters["n_estimators"] = final_rounds
        parameters.pop("early_stopping_rounds", None)
    parameters.update(
        random_state=config.random_seed,
        n_jobs=config.n_jobs,
        scale_pos_weight=class_ratio,
        verbosity=0,
    )
    return parameters


def regressor_parameters(
    config: XGBoostTrainingConfig,
    *,
    final_rounds: int | None = None,
) -> dict[str, Any]:
    parameters = dict(config.strength_regressor)
    if final_rounds is not None:
        parameters["n_estimators"] = final_rounds
        parameters.pop("early_stopping_rounds", None)
    parameters.update(
        random_state=config.random_seed,
        n_jobs=config.n_jobs,
        verbosity=0,
    )
    return parameters


def train_fold(
    fold_id: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_columns: list[str],
    config: XGBoostTrainingConfig,
    *,
    anchor: pd.DataFrame | None = None,
    return_importance: bool = False,
) -> tuple[Any, ...]:
    x_train = feature_matrix(train, feature_columns)
    x_validation = feature_matrix(validation, feature_columns)
    y_train = train["y_entry"].astype("int8")
    y_validation = validation["y_entry"].astype("int8")
    train_weight = train["sample_weight"].astype(float)
    validation_weight = validation["sample_weight"].astype(float)
    class_ratio = weighted_class_ratio(y_train, train_weight)

    classifier = XGBClassifier(**classifier_parameters(config, class_ratio))
    classifier.fit(
        x_train,
        y_train,
        sample_weight=train_weight,
        eval_set=[(x_validation, y_validation)],
        sample_weight_eval_set=[validation_weight],
        verbose=False,
    )
    entry_probability = classifier.predict_proba(x_validation)[:, 1]

    positive_train = y_train.eq(1)
    positive_validation = y_validation.eq(1)
    if positive_train.sum() < 2 or positive_validation.sum() < 2:
        raise RuntimeError(f"{fold_id} has too few positive rows for strength training.")
    regressor = XGBRegressor(**regressor_parameters(config))
    regressor.fit(
        x_train.loc[positive_train],
        train.loc[positive_train, "y_strength"].astype(float),
        sample_weight=train_weight.loc[positive_train],
        eval_set=[
            (
                x_validation.loc[positive_validation],
                validation.loc[positive_validation, "y_strength"].astype(float),
            )
        ],
        sample_weight_eval_set=[validation_weight.loc[positive_validation]],
        verbose=False,
    )
    strength_prediction = np.clip(regressor.predict(x_validation), 0.0, 1.0)

    fold_predictions = validation[
        ["symbol", "date", "y_entry", "y_strength", "sample_weight"]
    ].copy()
    fold_predictions.insert(0, "fold_id", fold_id)
    fold_predictions["p_entry_raw"] = entry_probability
    fold_predictions["p_strength"] = strength_prediction
    fold_metrics = {
        "fold_id": fold_id,
        "weighted_class_ratio": class_ratio,
        "classifier_best_round": best_round(
            classifier, int(config.classifier["n_estimators"])
        ),
        "strength_best_round": best_round(
            regressor, int(config.strength_regressor["n_estimators"])
        ),
        **{
            f"classification_{key}": value
            for key, value in classification_metrics(
                y_validation,
                entry_probability,
                validation_weight,
                threshold=0.5,
                top_fraction=config.precision_at_fraction,
            ).items()
        },
        **{
            f"strength_{key}": value
            for key, value in regression_metrics(
                validation.loc[positive_validation, "y_strength"],
                strength_prediction[positive_validation.to_numpy()],
                validation_weight.loc[positive_validation],
            ).items()
        },
    }
    fold_importance = feature_importance(classifier, feature_columns)
    fold_importance.insert(0, "fold_id", fold_id)
    anchor_predictions = None
    if anchor is not None and not anchor.empty:
        x_anchor = feature_matrix(anchor, feature_columns)
        anchor_predictions = anchor[["symbol", "date"]].copy()
        anchor_predictions.insert(0, "fold_id", fold_id)
        anchor_predictions["p_entry_raw"] = classifier.predict_proba(x_anchor)[:, 1]
        anchor_predictions["p_strength"] = np.clip(regressor.predict(x_anchor), 0.0, 1.0)
    result = (
        fold_predictions,
        fold_metrics,
        int(fold_metrics["classifier_best_round"]),
        int(fold_metrics["strength_best_round"]),
        fold_importance,
        anchor_predictions,
    )
    if return_importance:
        return result
    return result[:4]


def apply_prior_fold_calibration(
    anchor_oof: pd.DataFrame,
    source_oof: pd.DataFrame,
    config: XGBoostTrainingConfig,
) -> pd.DataFrame:
    """Calibrate anchor predictions using only prior source OOF folds."""
    result = anchor_oof.copy()
    # The first causal fold has no prior OOF history. Keep its fold-local raw
    # score as an explicit fallback so the anchor population remains visible
    # to downstream coverage audits; later folds receive prior-fold sigmoid
    # calibration only.
    result["p_entry_calibrated_temporal"] = result["p_entry_raw"]
    result["p_entry_calibration_status"] = "raw_no_prior_fold"
    source_folds = sorted(source_oof["fold_id"].astype(str).unique())
    for position, fold_id in enumerate(source_folds):
        current = result["fold_id"].astype(str).eq(fold_id)
        if not current.any() or position == 0:
            continue
        prior = source_oof["fold_id"].astype(str).isin(source_folds[:position])
        calibrator = fit_sigmoid_calibration(
            source_oof.loc[prior, "p_entry_raw"],
            source_oof.loc[prior, "y_entry"],
            source_oof.loc[prior, "sample_weight"],
            clip_epsilon=config.calibration_clip_epsilon,
            random_seed=config.random_seed,
        )
        result.loc[current, "p_entry_calibrated_temporal"] = calibrator.predict(
            result.loc[current, "p_entry_raw"]
        )
        result.loc[current, "p_entry_calibration_status"] = "prior_fold_temporal"
    return result


def temporal_calibration_audit(
    oof: pd.DataFrame,
    config: XGBoostTrainingConfig,
) -> dict[str, Any]:
    fold_ids = sorted(oof["fold_id"].unique())
    if len(fold_ids) < 2:
        return {"status": "not_available", "reason": "At least two folds are required."}
    audit_fold = fold_ids[-1]
    calibration_rows = oof["fold_id"].ne(audit_fold)
    audit_rows = ~calibration_rows
    calibrator = fit_sigmoid_calibration(
        oof.loc[calibration_rows, "p_entry_raw"],
        oof.loc[calibration_rows, "y_entry"],
        oof.loc[calibration_rows, "sample_weight"],
        clip_epsilon=config.calibration_clip_epsilon,
        random_seed=config.random_seed,
    )
    calibration_probability = calibrator.predict(
        oof.loc[calibration_rows, "p_entry_raw"]
    )
    threshold, _ = select_f1_threshold(
        oof.loc[calibration_rows, "y_entry"],
        calibration_probability,
        oof.loc[calibration_rows, "sample_weight"],
        grid_size=config.threshold_grid_size,
    )
    audit_probability = calibrator.predict(oof.loc[audit_rows, "p_entry_raw"])
    return {
        "status": "ok",
        "calibration_folds": fold_ids[:-1],
        "audit_fold": audit_fold,
        "threshold_selected_without_audit_fold": threshold,
        "metrics": classification_metrics(
            oof.loc[audit_rows, "y_entry"],
            audit_probability,
            oof.loc[audit_rows, "sample_weight"],
            threshold=threshold,
            top_fraction=config.precision_at_fraction,
        ),
    }


def feature_importance(model: XGBClassifier, feature_columns: list[str]) -> pd.DataFrame:
    gain = model.get_booster().get_score(importance_type="gain")
    weight = model.get_booster().get_score(importance_type="weight")
    return pd.DataFrame(
        {
            "feature": feature_columns,
            "gain": [float(gain.get(column, 0.0)) for column in feature_columns],
            "split_count": [float(weight.get(column, 0.0)) for column in feature_columns],
        }
    ).sort_values(["gain", "split_count"], ascending=False, kind="stable")


def fit_final_models(
    train: pd.DataFrame,
    feature_columns: list[str],
    config: XGBoostTrainingConfig,
    classifier_rounds: int,
    strength_rounds: int,
) -> tuple[XGBClassifier, XGBRegressor, float]:
    matrix = feature_matrix(train, feature_columns)
    target = train["y_entry"].astype("int8")
    weights = train["sample_weight"].astype(float)
    class_ratio = weighted_class_ratio(target, weights)
    classifier = XGBClassifier(
        **classifier_parameters(config, class_ratio, final_rounds=classifier_rounds)
    )
    classifier.fit(matrix, target, sample_weight=weights, verbose=False)
    positive = target.eq(1)
    regressor = XGBRegressor(
        **regressor_parameters(config, final_rounds=strength_rounds)
    )
    regressor.fit(
        matrix.loc[positive],
        train.loc[positive, "y_strength"].astype(float),
        sample_weight=weights.loc[positive],
        verbose=False,
    )
    return classifier, regressor, class_ratio


def evaluate_test(
    test: pd.DataFrame,
    feature_columns: list[str],
    classifier: XGBClassifier,
    regressor: XGBRegressor,
    calibrator: Any,
    threshold: float,
    config: XGBoostTrainingConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    matrix = feature_matrix(test, feature_columns)
    raw_probability = classifier.predict_proba(matrix)[:, 1]
    probability = calibrator.predict(raw_probability)
    conditional_strength = np.clip(regressor.predict(matrix), 0.0, 1.0)
    predictions = test[
        ["symbol", "date", "y_entry", "y_strength", "sample_weight"]
    ].copy()
    predictions["p_entry_raw"] = raw_probability
    predictions["p_entry_calibrated"] = probability
    predictions["predicted_entry"] = (probability >= threshold).astype("int8")
    predictions["p_strength_conditional"] = conditional_strength
    predictions["wave_score"] = probability * conditional_strength
    positive = test["y_entry"].eq(1)
    metrics = {
        "classification": classification_metrics(
            test["y_entry"],
            probability,
            test["sample_weight"],
            threshold=threshold,
            top_fraction=config.precision_at_fraction,
        ),
        "strength_positive_rows_only": regression_metrics(
            test.loc[positive, "y_strength"],
            conditional_strength[positive.to_numpy()],
            test.loc[positive, "sample_weight"],
        ),
    }
    return predictions, metrics


def main() -> None:
    args = parse_args()
    if args.cv_only and args.evaluate_final_test:
        raise ValueError("--evaluate-final-test cannot be combined with --cv-only.")
    config = XGBoostTrainingConfig.from_yaml(args.config)
    dataset_run = resolve_dataset_run(args.dataset_run, args.dataset_root)
    dataset_manifest_path = dataset_run / "dataset_manifest.json"
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    feature_columns = list(dataset_manifest["feature_columns"])
    dataset = load_dataset(dataset_run)
    missing_features = sorted(set(feature_columns) - set(dataset.columns))
    if missing_features:
        raise RuntimeError(f"Dataset is missing features: {missing_features}")
    anchor_dataset = None
    anchor_manifest = None
    if args.anchor_dataset_run is not None:
        anchor_dataset_run = args.anchor_dataset_run.resolve()
        anchor_manifest = json.loads(
            (anchor_dataset_run / "dataset_manifest.json").read_text(encoding="utf-8")
        )
        anchor_dataset = load_dataset(anchor_dataset_run)
        missing_anchor_features = sorted(set(feature_columns) - set(anchor_dataset.columns))
        if missing_anchor_features:
            raise RuntimeError(
                f"Anchor dataset is missing features: {missing_anchor_features}"
            )

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    runs_root = args.output_root / config.model_version / "runs"
    final_run_dir = runs_root / run_id
    run_dir = runs_root / f".incomplete-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    completed = False
    try:
        fold_directories = sorted(
            path
            for path in (dataset_run / "splits").glob("fold_*")
            if path.is_dir()
        )
        if not fold_directories:
            raise RuntimeError("No walk-forward fold directories were found.")
        oof_frames: list[pd.DataFrame] = []
        fold_metrics: list[dict[str, Any]] = []
        classifier_rounds: list[int] = []
        strength_rounds: list[int] = []
        fold_importance_frames: list[pd.DataFrame] = []
        anchor_prediction_frames: list[pd.DataFrame] = []
        for fold_directory in fold_directories:
            fold_id = fold_directory.name
            train = subset_by_keys(dataset, fold_directory / "train_keys.parquet")
            validation = subset_by_keys(
                dataset, fold_directory / "validation_keys.parquet"
            )
            anchor = None
            if anchor_dataset is not None:
                anchor_fold_keys = anchor_dataset_run / "splits" / fold_id / "validation_keys.parquet"
                if not anchor_fold_keys.exists():
                    raise RuntimeError(
                        f"Anchor dataset is missing validation keys for {fold_id}: {anchor_fold_keys}"
                    )
                anchor = subset_by_keys(anchor_dataset, anchor_fold_keys).reset_index()
                anchor["date"] = pd.to_datetime(anchor["date"], errors="raise")
            print(
                f"Training {fold_id}: train={len(train):,}, validation={len(validation):,}",
                flush=True,
            )
            (
                predictions,
                metrics,
                classifier_best,
                strength_best,
                fold_importance,
                anchor_predictions,
            ) = train_fold(
                fold_id,
                train,
                validation,
                feature_columns,
                config,
                anchor=anchor,
                return_importance=True,
            )
            oof_frames.append(predictions)
            fold_metrics.append(metrics)
            classifier_rounds.append(classifier_best)
            strength_rounds.append(strength_best)
            fold_importance_frames.append(fold_importance)
            if anchor_predictions is not None:
                anchor_prediction_frames.append(anchor_predictions)

        oof = pd.concat(oof_frames, ignore_index=True)
        oof.sort_values(["date", "symbol"], kind="stable", inplace=True)
        oof, temporal_calibration = temporal_calibration_predictions(
            oof,
            clip_epsilon=config.calibration_clip_epsilon,
            random_seed=config.random_seed,
            threshold_grid_size=config.threshold_grid_size,
            top_fraction=config.precision_at_fraction,
        )
        valid_temporal_audit = temporal_calibration.loc[
            temporal_calibration["status"].eq("ok")
        ]
        latest_temporal = valid_temporal_audit.iloc[-1].to_dict()
        calibration_audit = {
            "status": "ok",
            "calibration_folds": latest_temporal["calibration_folds"].split(","),
            "audit_fold": latest_temporal["fold_id"],
            "threshold_selected_without_audit_fold": latest_temporal["threshold"],
            "metrics": {
                key: value
                for key, value in latest_temporal.items()
                if key
                not in {
                    "fold_id",
                    "status",
                    "calibration_folds",
                    "calibration_coefficient",
                    "calibration_intercept",
                }
            },
        }
        calibrator = fit_sigmoid_calibration(
            oof["p_entry_raw"],
            oof["y_entry"],
            oof["sample_weight"],
            clip_epsilon=config.calibration_clip_epsilon,
            random_seed=config.random_seed,
        )
        oof["p_entry_calibrated"] = calibrator.predict(oof["p_entry_raw"])
        threshold, selected_f1 = select_f1_threshold(
            oof["y_entry"],
            oof["p_entry_calibrated"],
            oof["sample_weight"],
            grid_size=config.threshold_grid_size,
        )
        oof["predicted_entry"] = (oof["p_entry_calibrated"] >= threshold).astype(
            "int8"
        )
        anchor_oof = None
        if anchor_prediction_frames:
            anchor_oof = pd.concat(anchor_prediction_frames, ignore_index=True)
            anchor_oof.sort_values(["date", "symbol"], kind="stable", inplace=True)
            anchor_oof = apply_prior_fold_calibration(anchor_oof, oof, config)
        overall_metrics = {
            "raw_oof_at_0_5": classification_metrics(
                oof["y_entry"],
                oof["p_entry_raw"],
                oof["sample_weight"],
                threshold=0.5,
                top_fraction=config.precision_at_fraction,
            ),
            "calibrated_oof_at_selected_threshold": classification_metrics(
                oof["y_entry"],
                oof["p_entry_calibrated"],
                oof["sample_weight"],
                threshold=threshold,
                top_fraction=config.precision_at_fraction,
            ),
            "strength_oof_positive_rows_only": regression_metrics(
                oof.loc[oof["y_entry"].eq(1), "y_strength"],
                oof.loc[oof["y_entry"].eq(1), "p_strength"],
                oof.loc[oof["y_entry"].eq(1), "sample_weight"],
            ),
            "temporal_calibration_audit": calibration_audit,
        }
        selected_classifier_rounds = median_best_round(
            classifier_rounds, int(config.classifier["n_estimators"])
        )
        selected_strength_rounds = median_best_round(
            strength_rounds, int(config.strength_regressor["n_estimators"])
        )

        predictions_dir = run_dir / "predictions"
        audit_dir = run_dir / "audit"
        model_dir = run_dir / "model"
        predictions_dir.mkdir(parents=True, exist_ok=True)
        audit_dir.mkdir(parents=True, exist_ok=True)
        model_dir.mkdir(parents=True, exist_ok=True)
        oof.to_parquet(predictions_dir / "oof_predictions.parquet", index=False)
        if anchor_oof is not None:
            anchor_oof.to_parquet(
                predictions_dir / "anchor_oof_predictions.parquet", index=False
            )
        pd.DataFrame(fold_metrics).to_csv(
            audit_dir / "fold_metrics.csv", index=False, encoding="utf-8-sig"
        )
        fold_importance = pd.concat(fold_importance_frames, ignore_index=True)
        fold_importance.to_csv(
            audit_dir / "fold_entry_feature_importance.csv",
            index=False,
            encoding="utf-8-sig",
        )
        importance_stability = (
            fold_importance.groupby("feature", as_index=False)
            .agg(
                mean_gain=("gain", "mean"),
                median_gain=("gain", "median"),
                gain_std=("gain", "std"),
                nonzero_fold_count=("gain", lambda values: int((values > 0).sum())),
                mean_split_count=("split_count", "mean"),
            )
            .sort_values(["median_gain", "mean_gain"], ascending=False, kind="stable")
        )
        importance_stability.to_csv(
            audit_dir / "entry_feature_importance_stability.csv",
            index=False,
            encoding="utf-8-sig",
        )
        temporal_calibration.to_csv(
            audit_dir / "temporal_calibration_metrics.csv",
            index=False,
            encoding="utf-8-sig",
        )
        write_json(overall_metrics, audit_dir / "oof_metrics.json")
        write_json(calibrator.to_dict(), model_dir / "calibration.json")
        write_json(
            {
                "threshold": threshold,
                "selection_metric": config.threshold_metric,
                "selection_metric_value_on_oof": selected_f1,
                "precision_at_fraction": config.precision_at_fraction,
            },
            model_dir / "decision_policy.json",
        )
        write_json({"feature_columns": feature_columns}, model_dir / "features.json")

        final_test_evaluated = False
        final_training: dict[str, Any] | None = None
        if not args.cv_only:
            final_train = subset_by_keys(
                dataset, dataset_run / "splits/final/train_keys.parquet"
            )
            classifier, regressor, final_class_ratio = fit_final_models(
                final_train,
                feature_columns,
                config,
                selected_classifier_rounds,
                selected_strength_rounds,
            )
            classifier.save_model(str(model_dir / "entry_classifier.json"))
            regressor.save_model(str(model_dir / "strength_regressor.json"))
            feature_importance(classifier, feature_columns).to_csv(
                audit_dir / "entry_feature_importance.csv",
                index=False,
                encoding="utf-8-sig",
            )
            final_training = {
                "rows": len(final_train),
                "positive_rows": int(final_train["y_entry"].eq(1).sum()),
                "weighted_class_ratio": final_class_ratio,
                "classifier_rounds": selected_classifier_rounds,
                "strength_rounds": selected_strength_rounds,
                "last_training_date": final_train["date"].max(),
            }
            if args.evaluate_final_test:
                final_test = subset_by_keys(
                    dataset, dataset_run / "splits/final/test_keys.parquet"
                )
                test_predictions, test_metrics = evaluate_test(
                    final_test,
                    feature_columns,
                    classifier,
                    regressor,
                    calibrator,
                    threshold,
                    config,
                )
                test_predictions.to_parquet(
                    predictions_dir / "final_test_predictions.parquet", index=False
                )
                write_json(test_metrics, audit_dir / "final_test_metrics.json")
                final_test_evaluated = True

        generated_at = datetime.now(UTC).isoformat()
        manifest = {
            "model_version": config.model_version,
            "run_id": run_id,
            "generated_at_utc": generated_at,
            "dataset_dependency": {
                "dataset_version": dataset_manifest["dataset_version"],
                "run": str(dataset_run),
                "manifest_sha256": file_sha256(dataset_manifest_path),
            },
            "anchor_dataset_dependency": (
                {
                    "dataset_version": anchor_manifest["dataset_version"],
                    "run": str(args.anchor_dataset_run.resolve()),
                    "manifest_sha256": file_sha256(
                        args.anchor_dataset_run.resolve() / "dataset_manifest.json"
                    ),
                    "prediction_output": str(
                        (final_run_dir / "predictions/anchor_oof_predictions.parquet").resolve()
                    ),
                }
                if anchor_manifest is not None
                else None
            ),
            "configuration": config.to_dict(),
            "configuration_sha256": file_sha256(args.config),
            "architecture": {
                "entry": "XGBClassifier binary:logistic",
                "strength": "XGBRegressor trained on y_entry=1 only",
                "ensemble": False,
                "calibration": "Sigmoid calibration fitted from OOF predictions",
            },
            "selected_rounds": {
                "classifier": selected_classifier_rounds,
                "strength_regressor": selected_strength_rounds,
            },
            "decision_threshold": threshold,
            "final_training": final_training,
            "final_test_evaluated": final_test_evaluated,
            "test_policy": (
                "Final test is read only when --evaluate-final-test is explicitly supplied."
            ),
        }
        write_json(manifest, run_dir / "model_manifest.json")
        run_dir.rename(final_run_dir)
        write_json(
            {
                "model_version": config.model_version,
                "run_id": run_id,
                "run_directory": str(final_run_dir.resolve()),
                "generated_at_utc": generated_at,
                "final_test_evaluated": final_test_evaluated,
            },
            args.output_root / config.model_version / "latest.json",
        )
        completed = True
        print(json.dumps(overall_metrics, ensure_ascii=False, indent=2), flush=True)
        print(f"Model run: {final_run_dir.resolve()}", flush=True)
    finally:
        if not completed and run_dir.exists():
            shutil.rmtree(run_dir)


if __name__ == "__main__":
    main()
