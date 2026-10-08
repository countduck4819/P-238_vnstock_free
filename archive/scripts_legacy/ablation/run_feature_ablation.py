"""Train the predeclared A/B/C/D/F feature matrix with identical model settings."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", action="append", required=True, help="NAME=DATASET_RUN")
    parser.add_argument(
        "--template-config",
        type=Path,
        default=ROOT / "configs/wave_ignition_xgboost_v6_trend20.yaml",
    )
    parser.add_argument("--output-root", type=Path, default=ROOT / "models/wave_ignition")
    parser.add_argument("--artifact-root", type=Path, default=ROOT / "experiments/feature_ablation")
    args = parser.parse_args()
    template = yaml.safe_load(args.template_config.read_text(encoding="utf-8"))
    configs_dir = args.artifact_root / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    run_manifest: dict[str, object] = {"template": str(args.template_config.resolve()), "runs": {}}
    for item in args.dataset:
        name, separator, dataset_run = item.partition("=")
        if not separator or not name or not dataset_run:
            raise ValueError("dataset must use NAME=DATASET_RUN")
        payload = dict(template)
        payload["model_version"] = f"xgboost_feature_ablation_{name.lower()}_h20"
        config_path = configs_dir / f"xgboost_{name.lower()}.yaml"
        config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        command = [
            sys.executable,
            str(ROOT / "scripts/train_xgboost_wave.py"),
            "--dataset-run",
            str(Path(dataset_run).resolve()),
            "--config",
            str(config_path),
            "--output-root",
        ]
        command.append(str(args.output_root.resolve()))
        command.append("--cv-only")
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
        latest = json.loads(
            (args.output_root / payload["model_version"] / "latest.json").read_text(encoding="utf-8")
        )
        run_manifest["runs"][name] = {
            "dataset_run": str(Path(dataset_run).resolve()),
            "model_run": latest["run_directory"],
            "config": str(config_path.resolve()),
        }
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    (args.artifact_root / "run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(run_manifest, indent=2))


if __name__ == "__main__":
    main()
