from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_stock_primitives_exclude_unverified_feature_lineage() -> None:
    """The first ranker must remain stock-only until lineage gates are closed."""
    config = yaml.safe_load(
        (ROOT / "configs/experiments/h120_feature_groups_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    resolved = json.loads(
        (ROOT / "reports/h120_improvement/feature_governance/feature_groups_resolved.json").read_text(
            encoding="utf-8"
        )
    )
    stock_primitives = resolved["groups"]["stock_primitives"]

    assert (
        config["groups"]["stock_plus_sector_relative"]["status"]
        == "blocked_by_phase_1_4_industry_lineage"
    )
    assert resolved["constraints"]["corporate_action_features"].startswith("excluded_")
    assert not any(feature.startswith(("market_", "sector_", "relative_sector_")) for feature in stock_primitives)
    assert "corporate_action_jump" not in stock_primitives
    assert "corporate_action_recent" not in stock_primitives
