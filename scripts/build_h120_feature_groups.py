"""Resolve Phase-4 H120 feature groups from schema and a deterministic audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/h120_feature_groups_v1.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/h120_improvement/feature_governance"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def read_sample(feature_root: Path, features: list[str], rows_per_year: int, seed: int) -> pd.DataFrame:
    samples: list[pd.DataFrame] = []
    for offset, path in enumerate(sorted(feature_root.glob("year=*/features.parquet"))):
        frame = pd.read_parquet(path, columns=["feature_ready", *features])
        frame = frame.loc[frame["feature_ready"].fillna(False).astype(bool), features]
        if len(frame) > rows_per_year:
            frame = frame.sample(rows_per_year, random_state=seed + offset)
        samples.append(frame)
    if not samples:
        raise FileNotFoundError(f"No feature partitions found under {feature_root}")
    return pd.concat(samples, ignore_index=True)


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = args.output.resolve()
    expected = output / "feature_groups_resolved.json"
    if expected.exists() and not args.overwrite:
        raise FileExistsError(f"{expected} exists; use --overwrite to replace it.")
    manifest_path = (ROOT / config["feature_manifest"]).resolve()
    feature_root = (ROOT / config["feature_root"]).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    features = list(manifest["feature_columns"])
    audit_config = config["audit"]
    sample = read_sample(
        feature_root,
        features,
        rows_per_year=int(audit_config["sample_rows_per_year"]),
        seed=int(audit_config["random_seed"]),
    )
    summary = pd.DataFrame(
        {
            "feature": features,
            "non_null_rate": [float(sample[column].notna().mean()) for column in features],
            "std": [float(sample[column].std()) for column in features],
            "nunique": [int(sample[column].nunique(dropna=True)) for column in features],
        }
    )
    constant = set(
        summary.loc[
            summary["std"].le(float(audit_config["constant_std_epsilon"]))
            | summary["nunique"].le(1),
            "feature",
        ]
    )
    correlation = sample.corr(numeric_only=True)
    duplicate_pairs: list[dict[str, object]] = []
    removed_duplicate: set[str] = set()
    threshold = float(audit_config["duplicate_abs_correlation"])
    for left_position, left in enumerate(features):
        if left not in correlation:
            continue
        for right in features[left_position + 1 :]:
            if right not in correlation or right in removed_duplicate:
                continue
            value = correlation.loc[left, right]
            if pd.notna(value) and abs(float(value)) >= threshold:
                duplicate_pairs.append(
                    {"kept_feature": left, "removed_feature": right, "correlation": float(value)}
                )
                removed_duplicate.add(right)
    market = {feature for feature in features if feature.startswith("market_")}
    sector = {
        feature
        for feature in features
        if feature.startswith("sector_") or feature.startswith("relative_sector_")
    }
    corporate_lineage_risk = {"corporate_action_jump", "corporate_action_recent"}
    composites = {
        feature
        for feature in features
        if feature.endswith("_score") or feature in {"leader_consistency_20"}
    }
    stock_primitives = [
        feature
        for feature in features
        if feature not in market | sector | corporate_lineage_risk
    ]
    sector_relative = [feature for feature in features if feature.startswith("sector_relative_")]
    groups = {
        "full_83": features,
        "stock_primitives": stock_primitives,
        "stock_plus_sector_relative": [*stock_primitives, *sector_relative],
        "no_composites": [feature for feature in features if feature not in composites],
        "deduplicated": [
            feature for feature in features if feature not in constant | removed_duplicate
        ],
        "market_regime": sorted(market),
    }
    output.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output / "feature_variance_summary.csv", index=False)
    pd.DataFrame(duplicate_pairs).to_csv(output / "feature_duplicate_pairs.csv", index=False)
    payload = {
        "feature_group_version": config["feature_group_version"],
        "feature_manifest": str(manifest_path.relative_to(ROOT).as_posix()),
        "feature_version": manifest["feature_version"],
        "sample_rows": int(len(sample)),
        "audit": {
            **audit_config,
            "constant_features": sorted(constant),
            "near_duplicate_features_removed": sorted(removed_duplicate),
        },
        "groups": groups,
        "constraints": {
            "stock_plus_sector_relative": config["groups"]["stock_plus_sector_relative"]["status"],
            "market_regime": "calibration_or_exposure_only_not_stock_ranker",
            "corporate_action_features": "excluded_from_stock_primitives_until_phase_1_1_lineage_closes",
        },
    }
    (output / "feature_groups_resolved.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"status": "ok", "groups": {name: len(values) for name, values in groups.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
