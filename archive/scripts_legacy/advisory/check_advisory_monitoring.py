"""Check whether a live advisory ledger is due for recalibration or retraining."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.evaluation.monitoring import MonitoringConfig, build_refresh_plan  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--last-retrained-at", required=True, help="ISO date or timestamp")
    parser.add_argument("--last-recalibrated-at", required=True, help="ISO date or timestamp")
    parser.add_argument(
        "--config", type=Path, default=Path("configs/wave_ignition_advisory_v1.yaml")
    )
    args = parser.parse_args()
    plan = build_refresh_plan(
        pd.read_parquet(args.ledger),
        last_retrained_at=pd.Timestamp(args.last_retrained_at),
        last_recalibrated_at=pd.Timestamp(args.last_recalibrated_at),
        config=MonitoringConfig.from_yaml(args.config),
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False, default=str))


if __name__ == "__main__":
    main()
