"""Evaluate a frozen XGBoost wave artifact without retraining it."""

from __future__ import annotations

import argparse
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

from src.evaluation import (  # noqa: E402
    EvaluationConfig,
    evaluate_acceptance_gates,
    evaluate_predictions,
    verify_artifact,
)
from src.evaluation.backtest import BacktestConfig, run_backtest  # noqa: E402
from src.evaluation.wave_model import sha256_file  # noqa: E402
from src.models import WaveXGBoostPredictor  # noqa: E402
from src.training import subset_by_keys  # noqa: E402

FINAL_TEST_CONFIRMATION = "OPEN_FINAL_TEST_ONCE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("models/artifacts/xgboost_wave_v1"),
    )
    parser.add_argument("--artifact-run", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/wave_ignition_evaluation_v1.yaml"),
    )
    parser.add_argument("--split", choices=("oof", "final-test"), default="oof")
    parser.add_argument(
        "--confirm-final-test",
        default="",
        help=f"Required exact value for final-test: {FINAL_TEST_CONFIRMATION}",
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("eval/runs/wave_model")
    )
    return parser.parse_args()


def resolve_artifact(explicit: Path | None, root: Path) -> Path:
    if explicit is not None:
        return explicit.resolve()
    latest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    return Path(latest["artifact_directory"]).resolve()


def normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            normalize_json(payload), ensure_ascii=False, indent=2, allow_nan=False
        ),
        encoding="utf-8",
    )


def load_dataset_columns(dataset_run: Path, columns: list[str]) -> pd.DataFrame:
    paths = sorted(dataset_run.glob("dataset/year=*/dataset.parquet"))
    if not paths:
        raise RuntimeError(f"No dataset partitions found in {dataset_run}")
    frame = pd.concat(
        (pd.read_parquet(path, columns=columns) for path in paths), ignore_index=True
    )
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame.duplicated(["symbol", "date"]).any():
        raise RuntimeError("Dataset metadata contains duplicate symbol/date keys.")
    return frame


def load_oof_frame(
    artifact: Path,
    dataset_run: Path,
    label_run: Path,
    config: EvaluationConfig,
) -> pd.DataFrame:
    predictions = pd.read_parquet(
        artifact / "predictions/oof_predictions.parquet"
    )
    predictions["date"] = pd.to_datetime(predictions["date"], errors="raise")
    metadata_columns = [
        "symbol",
        "date",
        config.industry_column,
        config.market_regime_feature,
        config.liquidity_feature,
    ]
    metadata = load_dataset_columns(dataset_run, metadata_columns)
    frame = predictions.merge(
        metadata, on=["symbol", "date"], how="left", validate="one_to_one"
    )
    if frame[config.market_regime_feature].isna().any():
        raise RuntimeError("OOF evaluation lost required market-regime metadata.")
    if frame[config.liquidity_feature].isna().all():
        raise RuntimeError("OOF evaluation has no usable liquidity metadata.")
    return merge_label_outcomes(frame, label_run)


def load_label_outcomes(label_run: Path) -> pd.DataFrame:
    columns = [
        "symbol",
        "date",
        "terminal_return",
        "excess_market_return",
        "mfe",
        "mae",
        "entry_date",
        "label_end_date",
    ]
    paths = sorted(label_run.glob("labels/year=*/labels.parquet"))
    outcomes = pd.concat(
        (pd.read_parquet(path, columns=columns) for path in paths), ignore_index=True
    )
    outcomes["date"] = pd.to_datetime(outcomes["date"], errors="raise")
    if outcomes.duplicated(["symbol", "date"]).any():
        raise RuntimeError("Label outcomes contain duplicate symbol/date keys.")
    return outcomes


def merge_label_outcomes(frame: pd.DataFrame, label_run: Path) -> pd.DataFrame:
    outcomes = load_label_outcomes(label_run)
    result = frame.merge(
        outcomes, on=["symbol", "date"], how="left", validate="one_to_one"
    )
    if result["terminal_return"].isna().any():
        raise RuntimeError("Evaluation rows are missing realized label outcomes.")
    return result


def load_backtest_stock_data(
    stock_directory: Path,
    symbols: set[str],
    first_date: pd.Timestamp,
    last_date: pd.Timestamp,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in sorted(symbols):
        path = stock_directory / f"{symbol}.csv"
        if not path.is_file():
            continue
        frame = pd.read_csv(path, parse_dates=["date"])
        frame = frame.loc[frame["date"].between(first_date, last_date)]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        raise RuntimeError("No stock OHLCV could be loaded for backtesting.")
    return pd.concat(frames, ignore_index=True)


def load_final_test_frame(
    artifact: Path,
    dataset_run: Path,
    config: EvaluationConfig,
) -> pd.DataFrame:
    feature_payload = json.loads(
        (artifact / "model/features.json").read_text(encoding="utf-8")
    )
    feature_columns = list(feature_payload["feature_columns"])
    required_columns = list(
        dict.fromkeys(
            [
                "symbol",
                "date",
                config.industry_column,
                "y_entry",
                "y_strength",
                "sample_weight",
                *feature_columns,
            ]
        )
    )
    dataset = load_dataset_columns(dataset_run, required_columns)
    dataset.set_index(["symbol", "date"], verify_integrity=True, inplace=True)
    test = subset_by_keys(
        dataset, dataset_run / "splits/final/test_keys.parquet"
    )
    predictor = WaveXGBoostPredictor.from_run(artifact)
    prediction = predictor.predict(test)
    frame = test.merge(prediction, on=["symbol", "date"], validate="one_to_one")
    frame.rename(columns={"p_strength_conditional": "p_strength"}, inplace=True)
    frame["fold_id"] = "final_test"
    return frame


def render_markdown(
    evaluation_manifest: dict[str, Any],
    report: dict[str, Any],
    acceptance: dict[str, Any],
) -> str:
    classification = report["classification"]
    strength = report["strength_positive_rows_only"]
    strength_ranking = report.get("strength_ranking", {})
    calibration = report["calibration"]
    backtest = report.get("backtest")
    lines = [
        f"# Wave Model Evaluation — {evaluation_manifest['evaluation_id']}",
        "",
        "## Status",
        "",
        f"- Split: `{evaluation_manifest['split']}`",
        f"- Frozen artifact: `{evaluation_manifest['artifact_id']}`",
        "- Artifact checksum verified: **Yes**",
        f"- Pre-final gates passed: **{acceptance['pre_final_gates_passed']}**",
        f"- Deployment eligible: **{acceptance['deployment_eligible']}**",
        "",
        "## Overall metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| PR-AUC | {classification['average_precision']:.6f} |",
        f"| ROC-AUC | {classification['roc_auc']:.6f} |",
        f"| Event-weighted positive rate | {classification['positive_rate']:.6f} |",
        f"| Weighted precision at 5% | {classification['weighted_precision_at_fraction']:.6f} |",
        f"| Strength MAE | {strength['mae']:.6f} |",
        f"| Strength Spearman | {strength['spearman']:.6f} |",
        f"| Strength vs terminal return Spearman | {strength.get('spearman_terminal_return', float('nan')):.6f} |",
        f"| Strength ranking precision lift | {strength_ranking.get('precision_lift', float('nan')):.6f} |",
        f"| Calibration ECE | {calibration['expected_calibration_error']:.6f} |",
        f"| Brier skill score | {calibration['brier_skill_score']:.6f} |",
        f"| Calibration slope | {calibration['calibration_slope']:.6f} |",
        "",
    ]
    if backtest:
        lines.extend(
            [
                "## OOF backtest",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Cumulative return | {backtest['cumulative_return']:.6f} |",
                f"| Benchmark return | {backtest['benchmark_cumulative_return']:.6f} |",
                f"| Sharpe ratio | {backtest['sharpe_ratio']:.6f} |",
                f"| Maximum drawdown | {backtest['maximum_drawdown']:.6f} |",
                f"| Trades | {backtest['trades']} |",
                f"| Win rate | {backtest['win_rate']:.6f} |",
                f"| Profit factor | {backtest['profit_factor']:.6f} |",
                f"| Turnover ratio | {backtest['turnover_ratio']:.6f} |",
                "",
            ]
        )
    lines.extend(
        [
            "## Acceptance gates",
            "",
            "| Gate | Actual | Required | Passed |",
            "|---|---:|---:|:---:|",
        ]
    )
    for check in acceptance["checks"]:
        actual = check["actual"]
        required = check["required"]
        actual_text = f"{actual:.6f}" if isinstance(actual, float) else str(actual)
        required_text = f"{required:.6f}" if isinstance(required, float) else str(required)
        lines.append(
            f"| {check['gate']} | {actual_text} | {check['operator']} {required_text} | "
            f"{'PASS' if check['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "This evaluator loads a frozen artifact and never retrains it. Final-test",
            "evaluation requires an explicit confirmation token.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    if args.split == "final-test" and args.confirm_final_test != FINAL_TEST_CONFIRMATION:
        raise RuntimeError(
            "Final test remains sealed. Supply "
            f"--confirm-final-test {FINAL_TEST_CONFIRMATION} only after gates are frozen."
        )
    if args.split == "oof" and args.confirm_final_test:
        raise ValueError("--confirm-final-test is only valid with --split final-test.")

    config = EvaluationConfig.from_yaml(args.config)
    artifact = resolve_artifact(args.artifact_run, args.artifact_root)
    artifact_manifest = verify_artifact(artifact)
    model_manifest = json.loads(
        (artifact / "model_manifest.json").read_text(encoding="utf-8")
    )
    dataset_run = Path(model_manifest["dataset_dependency"]["run"])
    dataset_manifest_path = dataset_run / "dataset_manifest.json"
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    expected_dataset_hash = model_manifest["dataset_dependency"]["manifest_sha256"]
    if sha256_file(dataset_manifest_path) != expected_dataset_hash:
        raise RuntimeError("Dataset manifest checksum no longer matches the frozen model.")

    label_run = Path(dataset_manifest["label_dependency"]["run"])
    label_manifest = json.loads(
        (label_run / "label_manifest.json").read_text(encoding="utf-8")
    )
    if args.split == "oof":
        frame = load_oof_frame(artifact, dataset_run, label_run, config)
        if "p_entry_calibrated_temporal" not in frame:
            raise RuntimeError(
                "Frozen artifact predates temporal OOF calibration; create a new model run."
            )
        frame = frame.loc[frame["p_entry_calibrated_temporal"].notna()].copy()
        probability_column = "p_entry_calibrated_temporal"
    else:
        frame = load_final_test_frame(artifact, dataset_run, config)
        frame = merge_label_outcomes(frame, label_run)
        probability_column = "p_entry_calibrated"
    if frame["p_strength"].isna().any():
        raise RuntimeError(
            "Strength predictions must cover the entire evaluation universe."
        )
    frame["wave_score"] = frame[probability_column] * frame["p_strength"]
    threshold = float(model_manifest["decision_threshold"])
    report, tables = evaluate_predictions(
        frame, probability_column, threshold, config
    )
    if config.backtest.get("enabled", False):
        backtest_config = BacktestConfig.from_dict(config.backtest)
        if backtest_config.score_column not in frame:
            raise RuntimeError(
                f"Backtest score column is missing: {backtest_config.score_column}"
            )
        vnindex_path = Path(label_manifest["data_sources"]["vnindex_ohlcv"])
        stock_directory = Path(label_manifest["data_sources"]["stock_ohlcv"])
        vnindex = pd.read_csv(vnindex_path, parse_dates=["date"])
        if args.split == "oof":
            final_test_start = pd.Timestamp(
                dataset_manifest["split_configuration"]["test_start"]
            )
            vnindex = vnindex.loc[vnindex["date"] < final_test_start].copy()
        else:
            final_test_start = vnindex["date"].max() + pd.Timedelta(days=1)
        backtest_start = frame["date"].min()
        backtest_end = min(
            vnindex["date"].max(),
            final_test_start - pd.Timedelta(days=1),
            frame["date"].max()
            + pd.Timedelta(days=backtest_config.maximum_holding_sessions * 3),
        )
        stock_ohlcv = load_backtest_stock_data(
            stock_directory,
            set(frame["symbol"]),
            backtest_start,
            backtest_end,
        )
        (
            backtest_metrics,
            equity_curve,
            trade_log,
            skipped_log,
            yearly_backtest,
        ) = run_backtest(frame, stock_ohlcv, vnindex, backtest_config)
        report["backtest"] = backtest_metrics
        tables["backtest_equity_curve"] = equity_curve
        tables["backtest_trades"] = trade_log
        tables["backtest_skipped_signals"] = skipped_log
        tables["backtest_yearly"] = yearly_backtest
    training_oof_metrics = json.loads(
        (artifact / "audit/oof_metrics.json").read_text(encoding="utf-8")
    )
    gate_manifest = {
        **artifact_manifest,
        "final_test_evaluated": args.split == "final-test",
    }
    acceptance = evaluate_acceptance_gates(
        report,
        tables["segments"],
        training_oof_metrics,
        gate_manifest,
        config,
    )

    evaluation_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final_directory = args.output_root / config.evaluation_version / evaluation_id
    temporary = args.output_root / config.evaluation_version / f".incomplete-{evaluation_id}"
    temporary.mkdir(parents=True, exist_ok=False)
    completed = False
    try:
        for name, table in tables.items():
            table.to_csv(temporary / f"{name}.csv", index=False, encoding="utf-8-sig")
        if args.split == "final-test":
            frame[
                [
                    "symbol",
                    "date",
                    "y_entry",
                    "y_strength",
                    "sample_weight",
                    "p_entry_raw",
                    "p_entry_calibrated",
                    "p_strength",
                    "wave_score",
                ]
            ].to_parquet(temporary / "final_test_predictions.parquet", index=False)
        generated_at = datetime.now(UTC).isoformat()
        evaluation_manifest = {
            "evaluation_version": config.evaluation_version,
            "evaluation_id": evaluation_id,
            "generated_at_utc": generated_at,
            "split": args.split,
            "artifact_id": artifact_manifest["artifact_id"],
            "artifact_payload_sha256": artifact_manifest["payload_sha256"],
            "artifact_directory": str(artifact.resolve()),
            "dataset_manifest_sha256": expected_dataset_hash,
            "evaluation_config_sha256": sha256_file(args.config),
            "retrained": False,
            "final_test_opened": args.split == "final-test",
            "deployment_eligible": acceptance["deployment_eligible"],
        }
        write_json(report, temporary / "metrics.json")
        write_json(acceptance, temporary / "acceptance_gates.json")
        write_json(evaluation_manifest, temporary / "evaluation_manifest.json")
        (temporary / "report.md").write_text(
            render_markdown(evaluation_manifest, report, acceptance),
            encoding="utf-8",
        )
        temporary.rename(final_directory)
        write_json(
            {
                **evaluation_manifest,
                "evaluation_directory": str(final_directory.resolve()),
            },
            args.output_root / config.evaluation_version / "latest.json",
        )
        completed = True
        print(json.dumps(normalize_json(evaluation_manifest), indent=2), flush=True)
        print(json.dumps(normalize_json(acceptance), indent=2), flush=True)
        print(f"Evaluation run: {final_directory.resolve()}", flush=True)
    finally:
        if not completed and temporary.exists():
            shutil.rmtree(temporary)


if __name__ == "__main__":
    main()
