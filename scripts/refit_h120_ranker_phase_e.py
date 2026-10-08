"""Refit the frozen H120 ranker through the latest mature label cutoff.

This script creates a research-only model bundle.  It neither scores a live
universe nor changes the frozen champion or trade authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.train_h120_ranker import DEFAULT_GROUPS, load_dataset
from src.training.h120_experiment_protocol import H120ExperimentProtocol
from src.training.h120_ranker import H120RankerConfig, prepare_ranking_frame, ranking_group_sizes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-run", type=Path, required=True)
    parser.add_argument("--selection-record", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True, help="Maturity cutoff YYYY-MM-DD.")
    parser.add_argument("--feature-groups", type=Path, default=DEFAULT_GROUPS)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("models/wave_ignition/h120_ranker_generation_v2_phase_e"),
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    args = parse_args()
    dataset_run = args.dataset_run.resolve()
    dataset_manifest = json.loads((dataset_run / "dataset_manifest.json").read_text(encoding="utf-8"))
    selection = json.loads(args.selection_record.read_text(encoding="utf-8"))
    protocol = H120ExperimentProtocol.from_yaml(args.protocol)
    protocol.validate_dataset_manifest(dataset_run)
    if selection.get("status") != "configuration_frozen_research_eligible":
        raise ValueError("Phase E requires a frozen research-eligible selection record.")
    if selection.get("protocol") != args.protocol.as_posix():
        raise ValueError("Selection record protocol does not match requested protocol.")
    if Path(selection.get("frozen_config", "")).as_posix() != args.config.as_posix():
        raise ValueError("Phase E config differs from the frozen selection record.")
    if selection.get("frozen_config_sha256") != sha256(args.config):
        raise ValueError("Frozen config checksum does not match selection record.")
    if selection.get("trade_authorized", True):
        raise ValueError("Phase E refit must remain research/shadow only.")
    config = H120RankerConfig.from_yaml(args.config)
    groups = json.loads(args.feature_groups.read_text(encoding="utf-8"))
    features = protocol.validate_feature_group(args.feature_groups)
    if groups["groups"][protocol.feature_group] != features:
        raise ValueError("Resolved feature group differs from frozen protocol.")
    dataset = load_dataset(dataset_run, features, extra_columns=("label_end_date",))
    frame = dataset.reset_index()
    frame["label_end_date"] = pd.to_datetime(frame["label_end_date"], errors="raise")
    as_of_date = pd.Timestamp(args.as_of_date)
    mature = frame.loc[frame["label_end_date"] <= as_of_date].copy()
    if mature.empty:
        raise ValueError("No labels are mature at the requested Phase E cutoff.")
    train = prepare_ranking_frame(mature, features)
    parameters = dict(config.ranker)
    parameters.pop("early_stopping_rounds", None)
    parameters["n_estimators"] = int(selection["final_n_estimators"])
    from xgboost import XGBRanker

    model = XGBRanker(**parameters, random_state=config.random_seed, n_jobs=config.n_jobs)
    model.fit(train[features], train["y_entry"].astype(float), group=ranking_group_sizes(train), verbose=False)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final = args.output_root.resolve() / "runs" / run_id
    incomplete = final.parent / f".incomplete-{run_id}"
    (incomplete / "model").mkdir(parents=True, exist_ok=False)
    model.get_booster().save_model(incomplete / "model" / "ranker.json")
    (incomplete / "feature_list.json").write_text(json.dumps(features, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "status": "research_only_refit_ready_for_shadow_preparation",
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "protocol": protocol.to_manifest(),
        "selection_record": str(args.selection_record),
        "dataset_run": str(dataset_run),
        "feature_dependency": dataset_manifest["feature_dependency"],
        "as_of_date": str(as_of_date.date()),
        "latest_matured_decision_date": str(train["date"].max().date()),
        "latest_matured_label_end_date": str(train["label_end_date"].max().date()),
        "training_rows": int(len(train)),
        "training_symbols": int(train["symbol"].nunique()),
        "positive_rate": float(train["y_entry"].mean()),
        "feature_group": protocol.feature_group,
        "feature_count": len(features),
        "ranker_parameters": parameters,
        "checksums": {
            "config": sha256(args.config),
            "selection_record": sha256(args.selection_record),
            "dataset_manifest": sha256(dataset_run / "dataset_manifest.json"),
            "feature_groups": sha256(args.feature_groups),
        },
        "calibration_status": "unvalidated_probability_not_for_decision_order",
        "ranking_policy": "rank_score_only",
        "trade_authorized": False,
    }
    (incomplete / "model_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    incomplete.rename(final)
    print(json.dumps({"status": manifest["status"], "run_directory": str(final)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
