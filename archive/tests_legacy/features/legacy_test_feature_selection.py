from pathlib import Path

import pytest

from src.features import FeatureSelectionConfig

def test_selection_rejects_duplicate_features(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
selection_version: invalid
dataset_version: invalid
source_dataset_version: source
source_feature_version: source_features
status: candidate_for_cv
expected_feature_count: 2
selection_basis: [temporal_cv]
guardrails: {}
feature_groups:
  stock: [momentum_20]
  market: [momentum_20]
exclusions:
  unused: [coverage_20]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate selected features"):
        FeatureSelectionConfig.from_yaml(path)
