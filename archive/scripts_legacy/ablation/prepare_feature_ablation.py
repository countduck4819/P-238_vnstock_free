"""Generate auditable selection configs for the experimental feature matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.features.technical_experimental import EXPERIMENTAL_FEATURES, EXPERIMENTAL_GROUPS  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-run", type=Path, required=True)
    parser.add_argument("--source-dataset-version", default="wave_dataset_ablation_superset_h20")
    parser.add_argument(
        "--matrix-config",
        type=Path,
        default=ROOT / "configs/experiments/wave_feature_ablation_v2.yaml",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "configs/experiments/generated")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = json.loads((args.feature_run / "feature_manifest.json").read_text(encoding="utf-8"))
    source_features = list(manifest["feature_columns"])
    missing_experimental = sorted(set(EXPERIMENTAL_FEATURES) - set(source_features))
    if missing_experimental:
        raise ValueError(f"Feature run is not an experimental superset: {missing_experimental}")
    baseline = [feature for feature in source_features if feature not in EXPERIMENTAL_FEATURES]
    matrix = yaml.safe_load(args.matrix_config.read_text(encoding="utf-8"))
    required_version = matrix["feature_run_required"]
    if manifest["feature_version"] != required_version:
        raise ValueError(
            f"Feature version mismatch: expected {required_version}, "
            f"got {manifest['feature_version']}."
        )
    experiment_version = matrix["experiment_version"]
    args.output.mkdir(parents=True, exist_ok=True)
    generated: dict[str, str] = {}
    for name, spec in matrix["experiments"].items():
        groups = list(spec.get("groups", []))
        selected = list(baseline) if spec.get("baseline", True) else []
        for group in groups:
            selected.extend(EXPERIMENTAL_GROUPS[group])
        selected = list(dict.fromkeys(selected))
        excluded = [feature for feature in source_features if feature not in selected]
        payload: dict[str, Any] = {
            "selection_version": f"{experiment_version}_{name.lower()}",
            "dataset_version": f"wave_dataset_ablation_{name.lower()}_h20",
            "source_dataset_version": args.source_dataset_version,
            "source_feature_version": manifest["feature_version"],
            "status": "candidate_for_cv",
            "expected_feature_count": len(selected),
            "selection_basis": [
                "predeclared_feature_ablation_matrix",
                "same_labels_temporal_splits_and_model_parameters",
                "final_test_not_used_for_selection",
            ],
            "guardrails": {
                "experiment": name,
                "description": spec["description"],
                "feature_run": str(args.feature_run.resolve()),
                "final_test_used_for_selection": False,
            },
            "feature_groups": {"baseline": baseline} if spec.get("baseline", True) else {},
            "exclusions": {"not_in_experiment": excluded} if excluded else {},
        }
        if groups:
            payload["feature_groups"].update({group: list(EXPERIMENTAL_GROUPS[group]) for group in groups})
        path = args.output / f"selection_{name.lower()}.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        generated[name] = str(path.resolve())
    (args.output / "manifest.json").write_text(
        json.dumps(
            {
                "experiment_version": experiment_version,
                "feature_run": str(args.feature_run.resolve()),
                "matrix_config": str(args.matrix_config.resolve()),
                "generated": generated,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(generated, indent=2))


if __name__ == "__main__":
    main()
