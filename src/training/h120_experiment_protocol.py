"""Immutable policy checks for a new H120 ranker experiment generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class H120ExperimentProtocol:
    """Validate the pre-registered feature, label and selection contracts."""

    protocol_id: str
    feature_group: str
    expected_feature_count: int
    label_version: str
    horizon_sessions: int
    selection_folds: tuple[str, ...]
    prohibited_selection_folds: tuple[str, ...]
    confirmation_seeds: tuple[int, ...]
    raw: dict[str, Any]

    @classmethod
    def from_yaml(cls, path: Path) -> H120ExperimentProtocol:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        feature = payload["feature_contract"]
        label = payload["label_contract"]
        selection = payload["selection_contract"]
        if label["target"] != "y_entry_binary":
            raise ValueError("The new H120 ranker generation may optimize only binary y_entry.")
        if bool(label.get("strength_target_enabled", False)):
            raise ValueError("Conditional strength must not be an optimization target in this generation.")
        if int(label["horizon_sessions"]) != 120:
            raise ValueError("The protocol is restricted to a 120-session horizon.")
        if feature["group"] != "stock_primitives":
            raise ValueError("The first new ranker generation must use stock_primitives only.")
        prohibited = tuple(str(value) for value in selection["prohibited_folds"])
        selected = tuple(str(value) for value in selection["inner_folds"])
        overlap = sorted(set(selected).intersection(prohibited))
        if overlap:
            raise ValueError(f"Selection folds are prohibited by protocol: {overlap}")
        if "fold_2024" not in prohibited:
            raise ValueError("fold_2024 must remain excluded from configuration selection.")
        return cls(
            protocol_id=str(payload["protocol_id"]),
            feature_group=str(feature["group"]),
            expected_feature_count=int(feature["expected_feature_count"]),
            label_version=str(label["label_version"]),
            horizon_sessions=int(label["horizon_sessions"]),
            selection_folds=selected,
            prohibited_selection_folds=prohibited,
            confirmation_seeds=tuple(int(seed) for seed in selection["confirmation_seeds"]),
            raw=payload,
        )

    def validate_feature_group(self, resolved_groups_path: Path) -> list[str]:
        resolved = json.loads(resolved_groups_path.read_text(encoding="utf-8"))
        features = list(resolved["groups"][self.feature_group])
        if len(features) != self.expected_feature_count:
            raise ValueError(
                f"{self.feature_group} has {len(features)} features; "
                f"expected {self.expected_feature_count}."
            )
        forbidden_prefixes = ("market_", "sector_", "relative_sector_")
        forbidden = [
            feature
            for feature in features
            if feature.startswith(forbidden_prefixes)
            or feature in {"corporate_action_jump", "corporate_action_recent"}
        ]
        if forbidden:
            raise ValueError(f"Feature group violates stock-only lineage policy: {forbidden}")
        return features

    def validate_label_config(self, label_config_path: Path) -> None:
        label = yaml.safe_load(label_config_path.read_text(encoding="utf-8"))
        if str(label["label_version"]) != self.label_version:
            raise ValueError("Label version does not match the frozen protocol.")
        if int(label["horizon"]) != self.horizon_sessions:
            raise ValueError("Label horizon does not match the frozen protocol.")

    def validate_dataset_manifest(self, dataset_run: Path) -> None:
        """Ensure the actual rows, not only the config, satisfy the label contract."""
        manifest_path = dataset_run / "dataset_manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        dependency = payload.get("label_dependency", {})
        actual = str(dependency.get("version", ""))
        if actual != self.label_version:
            raise ValueError(
                f"Dataset label version {actual or '<missing>'} does not match "
                f"frozen protocol {self.label_version}."
            )

    def validate_selection_folds(self, folds: list[str]) -> None:
        unknown = sorted(set(folds).difference(self.selection_folds))
        if unknown:
            raise ValueError(
                "Configuration selection is limited to the frozen inner folds; "
                f"received {unknown}."
            )
        if tuple(folds) != self.selection_folds:
            raise ValueError(
                f"Selection folds must be exactly {list(self.selection_folds)}, got {folds}."
            )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "feature_group": self.feature_group,
            "expected_feature_count": self.expected_feature_count,
            "label_version": self.label_version,
            "horizon_sessions": self.horizon_sessions,
            "selection_folds": list(self.selection_folds),
            "prohibited_selection_folds": list(self.prohibited_selection_folds),
            "confirmation_seeds": list(self.confirmation_seeds),
            "trade_authorized": False,
        }
