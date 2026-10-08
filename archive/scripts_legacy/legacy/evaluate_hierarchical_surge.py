"""Evaluate predeclared H0--H3 hierarchical H20 surge selection on OOF only."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.hierarchical_surge import (  # noqa: E402
    HierarchicalSurgeConfig,
    causal_hierarchical_oof,
    fit_deployment_meta_model,
    join_expert_oof,
    load_expert_oof,
    matched_day_month_bootstrap,
    select_technical_gate,
    summarize_candidates,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-run", type=Path, required=True, help="A model run")
    parser.add_argument("--technical-run", type=Path, required=True, help="F model run")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/experiments/wave_hierarchical_surge_v1.yaml",
    )
    parser.add_argument("--bootstrap-samples", type=int)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "models/wave_ignition/hierarchical_surge_v1",
    )
    return parser.parse_args()


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(
        json.dumps(normalize_json(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


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


def main() -> None:
    args = parse_args()
    payload = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if payload.get("final_test_used_for_selection"):
        raise ValueError("Hierarchical selection must not use final-test outcomes.")
    bootstrap_samples = int(
        args.bootstrap_samples or payload["evaluation"]["bootstrap_samples"]
    )
    bootstrap_random_seed = int(payload["evaluation"]["bootstrap_random_seed"])
    if bootstrap_samples <= 0:
        raise ValueError("--bootstrap-samples must be positive.")
    config = HierarchicalSurgeConfig.from_dict(payload)
    stock = load_expert_oof(
        args.stock_run / "predictions/oof_predictions.parquet", "stock"
    )
    technical = load_expert_oof(
        args.technical_run / "predictions/oof_predictions.parquet", "technical"
    )
    joined = join_expert_oof(stock, technical)
    evaluated, fold_metrics, gate_audit = causal_hierarchical_oof(joined, config)
    summary = summarize_candidates(evaluated, config)
    bootstrap = {
        candidate: matched_day_month_bootstrap(
            evaluated,
            candidate,
            config,
            samples=bootstrap_samples,
            random_seed=bootstrap_random_seed,
        )
        for candidate in ("H1", "H2", "H3")
    }
    promotion = promotion_report(
        summary, fold_metrics, payload["promotion"], bootstrap
    )
    for candidate, report in promotion.items():
        summary[candidate]["promotion_gate"] = report
    deployment_meta = fit_deployment_meta_model(joined, config)
    deployment_policies = {
        "H1": select_technical_gate(joined, score_column="p_stock_raw", config=config),
        "H3": select_technical_gate(
            evaluated.loc[evaluated["p_h2"].notna()], score_column="p_h2", config=config
        ),
    }

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final_dir = args.output_root / "runs" / run_id
    incomplete = final_dir.parent / f".incomplete-{run_id}"
    if final_dir.exists() or incomplete.exists():
        raise FileExistsError(f"Hierarchical run already exists: {run_id}")
    (incomplete / "predictions").mkdir(parents=True)
    (incomplete / "audit").mkdir()
    (incomplete / "model").mkdir()
    evaluated.to_parquet(incomplete / "predictions/hierarchical_oof.parquet", index=False)
    fold_metrics.to_csv(incomplete / "audit/fold_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(promotion).T.to_csv(
        incomplete / "audit/promotion_gate.csv", index_label="candidate", encoding="utf-8-sig"
    )
    gate_audit.to_csv(incomplete / "audit/technical_gate_audit.csv", index=False, encoding="utf-8-sig")
    joblib.dump(deployment_meta, incomplete / "model/meta_model.joblib")
    write_json(deployment_policies, incomplete / "model/candidate_decision_policies.json")
    write_json(
        {
            "run_id": run_id,
            "experiment_version": payload["experiment_version"],
            "status": "candidate_oof_only",
            "final_test_evaluated": False,
            "stock_run": str(args.stock_run.resolve()),
            "technical_run": str(args.technical_run.resolve()),
            "stock_oof_sha256": sha256_file(args.stock_run / "predictions/oof_predictions.parquet"),
            "technical_oof_sha256": sha256_file(
                args.technical_run / "predictions/oof_predictions.parquet"
            ),
            "configuration_sha256": sha256_file(args.config),
            "config": config.to_dict(),
            "candidates": summary,
            "bootstrap": bootstrap,
            "warning": (
                "H0--H3 were selected and evaluated on causal OOF folds only. "
                "No final holdout or production claim is implied."
            ),
        },
        incomplete / "audit/summary.json",
    )
    write_json(
        {
            "run_id": run_id,
            "run_directory": str(final_dir.resolve()),
            "status": "candidate_oof_only",
            "final_test_evaluated": False,
        },
        incomplete / "model_manifest.json",
    )
    incomplete.rename(final_dir)
    write_json(
        {
            "run_id": run_id,
            "run_directory": str(final_dir.resolve()),
            "status": "candidate_oof_only",
            "final_test_evaluated": False,
        },
        args.output_root / "latest_experiment.json",
    )
    print(json.dumps(normalize_json(summary), ensure_ascii=False, indent=2))
    print(f"Hierarchical OOF run: {final_dir}")


def promotion_report(
    summary: dict[str, dict[str, Any]],
    fold_metrics: pd.DataFrame,
    promotion: dict[str, Any],
    bootstrap: dict[str, dict[str, float]],
) -> dict[str, dict[str, Any]]:
    """Apply predeclared Top-K gates without using final-holdout outcomes."""
    reports: dict[str, dict[str, Any]] = {
        "H0": {"status": "baseline", "checks": {"baseline": True}}
    }
    for candidate in ("H1", "H2", "H3"):
        candidate_summary = summary[candidate]
        if candidate_summary["status"] != "ok":
            reports[candidate] = {"status": "not_available", "checks": {}}
            continue
        paired = fold_metrics.loc[fold_metrics["candidate"].eq(candidate)].copy()
        paired["relative_gain"] = (
            paired["daily_precision_at_k"]
            / paired["matched_h0_daily_precision_at_k"]
            - 1.0
        )
        gain = candidate_summary["daily_precision_at_k_relative_gain_vs_h0"]
        candidate_ece = candidate_summary["temporal_calibration"]["ece_10"]
        baseline_ece = candidate_summary["comparable_h0_temporal_calibration"]["ece_10"]
        ece_delta = candidate_ece - baseline_ece
        interval = bootstrap[candidate]
        checks = {
            "top_k_gain": gain >= promotion["minimum_relative_gain_vs_h0"],
            "positive_fold_count": int((paired["relative_gain"] >= 0).sum())
            >= promotion["minimum_positive_fold_count"],
            "ece": ece_delta <= promotion["maximum_ece_increase"],
            "bootstrap_lower_bound": interval["lower"] > 0,
        }
        reports[candidate] = {
            "relative_daily_precision_at_k_gain": gain,
            "positive_fold_count": int((paired["relative_gain"] >= 0).sum()),
            "folds_evaluated": int(len(paired)),
            "temporal_ece_delta_vs_h0": ece_delta,
            "matched_day_bootstrap_precision_delta": interval,
            "checks": checks,
            "status": "candidate" if all(checks.values()) else "reject_for_next_stage",
        }
    return reports


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
