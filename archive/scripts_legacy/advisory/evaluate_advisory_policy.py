"""Evaluate the abstaining daily Top-K advisory policy using temporal OOF predictions."""

from __future__ import annotations

import argparse
import json
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
    AdvisoryPolicyConfig,
    advisory_summary,
    apply_nested_temporal_advisory_policy,
    apply_temporal_advisory_policy,
    build_confidence_profile,
    month_block_bootstrap_comparison,
    select_policy_from_history,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-run",
        type=Path,
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=Path("models/wave_ignition/xgboost_wave_v5_h150"),
        help="Used only when --model-run is omitted; resolves that root's latest.json.",
    )
    parser.add_argument(
        "--dataset-run",
        type=Path,
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("data/training/wave_ignition/wave_dataset_v5_h150"),
        help="Used only when --dataset-run is omitted; resolves that root's latest.json.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/wave_ignition_advisory_v1.yaml"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("eval/runs/wave_advisory"),
    )
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--random-seed", type=int, default=238)
    return parser.parse_args()


def resolve_run(explicit_run: Path | None, root: Path) -> Path:
    if explicit_run is not None:
        return explicit_run.resolve()
    latest_path = root / "latest.json"
    if not latest_path.is_file():
        raise FileNotFoundError(f"Missing --run and latest pointer: {latest_path}")
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    run = payload.get("run_directory")
    if not run:
        raise ValueError(f"latest pointer has no run_directory: {latest_path}")
    return Path(run).resolve()


def normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    return value


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(
        json.dumps(normalize_json(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def load_dataset_metadata(run: Path, regime_feature: str) -> pd.DataFrame:
    columns = ["symbol", "date", "event_id", regime_feature]
    paths = sorted(run.glob("dataset/year=*/dataset.parquet"))
    if not paths:
        raise FileNotFoundError(f"No dataset partitions found under {run}")
    metadata = pd.concat(
        (pd.read_parquet(path, columns=columns) for path in paths), ignore_index=True
    )
    metadata["date"] = pd.to_datetime(metadata["date"], errors="raise")
    if metadata.duplicated(["symbol", "date"]).any():
        raise RuntimeError("Dataset metadata has duplicate symbol/date keys.")
    return metadata


def main() -> None:
    args = parse_args()
    config = AdvisoryPolicyConfig.from_yaml(args.config)
    model_run = resolve_run(args.model_run, args.model_root)
    dataset_run = resolve_run(args.dataset_run, args.dataset_root)
    predictions = pd.read_parquet(model_run / "predictions/oof_predictions.parquet")
    predictions["date"] = pd.to_datetime(predictions["date"], errors="raise")
    predictions = predictions.loc[predictions["p_entry_calibrated_temporal"].notna()].copy()
    metadata = load_dataset_metadata(dataset_run, config.market_regime_feature)
    frame = predictions.merge(metadata, on=["symbol", "date"], how="inner", validate="one_to_one")
    if len(frame) != len(predictions):
        raise RuntimeError("OOF advisory evaluation lost prediction rows during metadata merge.")

    evaluated, selection_audit = apply_nested_temporal_advisory_policy(frame, config)
    summary = advisory_summary(evaluated)
    bootstrap = month_block_bootstrap_comparison(
        evaluated,
        config,
        samples=args.bootstrap_samples,
        random_seed=args.random_seed,
    )
    deployed_config, deployment_candidate_audit = select_policy_from_history(frame, config)
    profile_history = apply_temporal_advisory_policy(frame, deployed_config)
    profile_history = profile_history.loc[
        profile_history["daily_rank"].le(deployed_config.top_k_max)
    ].copy()
    confidence_profile = build_confidence_profile(profile_history, config)
    fold_summary = []
    for fold_id, fold in evaluated.groupby("fold_id", sort=True):
        fold_summary.append({"fold_id": fold_id, **advisory_summary(fold)})

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final_dir = args.output_root / config.policy_version / "runs" / run_id
    incomplete = final_dir.parent / f".incomplete-{run_id}"
    if final_dir.exists() or incomplete.exists():
        raise FileExistsError(f"Evaluation run already exists: {run_id}")
    incomplete.mkdir(parents=True)
    evaluated.to_parquet(incomplete / "advisory_recommendations_oof.parquet", index=False)
    confidence_profile.to_parquet(incomplete / "confidence_profile.parquet", index=False)
    selection_audit.to_json(
        incomplete / "nested_policy_selection.json",
        orient="records",
        force_ascii=False,
        indent=2,
    )
    pd.DataFrame(fold_summary).to_csv(incomplete / "fold_summary.csv", index=False, encoding="utf-8-sig")
    write_json(
        {
            "policy_candidates": config.to_dict(),
            "deployment_policy_selected_from_all_oof_history": deployed_config.to_dict(),
            "deployment_candidate_audit": deployment_candidate_audit,
            "model_run": str(model_run),
            "dataset_run": str(dataset_run),
            "scope": "nested_temporal_oof_only",
            "final_test_evaluated": False,
            "warning": (
                "Nested-fold results are policy-selection evaluation. The frozen deployment "
                "policy still requires a future paper-trading or sealed holdout validation."
            ),
            "summary": summary,
            "bootstrap": bootstrap,
            "fold_summary": fold_summary,
        },
        incomplete / "advisory_summary.json",
    )
    incomplete.rename(final_dir)
    write_json(
        {
            "policy_version": config.policy_version,
            "run_id": run_id,
            "run_directory": str(final_dir.resolve()),
            "final_test_evaluated": False,
        },
        args.output_root / config.policy_version / "latest.json",
    )
    print(json.dumps(normalize_json(summary), ensure_ascii=False, indent=2), flush=True)
    print(f"Advisory evaluation: {final_dir.resolve()}", flush=True)


if __name__ == "__main__":
    main()
