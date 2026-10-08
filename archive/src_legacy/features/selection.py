"""Validated feature-selection specifications for derived model datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class FeatureSelectionConfig:
    """A versioned, auditable selection over an existing feature set."""

    selection_version: str
    dataset_version: str
    source_dataset_version: str
    source_feature_version: str
    status: str
    expected_feature_count: int
    groups: tuple[tuple[str, tuple[str, ...]], ...]
    exclusions: tuple[tuple[str, tuple[str, ...]], ...]
    selection_basis: tuple[str, ...]
    guardrails: tuple[tuple[str, Any], ...]

    @property
    def selected_features(self) -> list[str]:
        return [feature for _, features in self.groups for feature in features]

    @property
    def excluded_features(self) -> list[str]:
        return [feature for _, features in self.exclusions for feature in features]

    @property
    def groups_by_name(self) -> dict[str, list[str]]:
        return {name: list(features) for name, features in self.groups}

    @property
    def exclusions_by_reason(self) -> dict[str, list[str]]:
        return {name: list(features) for name, features in self.exclusions}

    @property
    def guardrails_by_name(self) -> dict[str, Any]:
        return dict(self.guardrails)

    @classmethod
    def from_yaml(cls, path: Path) -> FeatureSelectionConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Feature selection config must be a YAML mapping.")

        groups = cls._parse_feature_groups(payload.get("feature_groups"), "feature_groups")
        exclusions = cls._parse_feature_groups(payload.get("exclusions"), "exclusions")
        config = cls(
            selection_version=str(payload["selection_version"]),
            dataset_version=str(payload["dataset_version"]),
            source_dataset_version=str(payload["source_dataset_version"]),
            source_feature_version=str(payload["source_feature_version"]),
            status=str(payload["status"]),
            expected_feature_count=int(payload["expected_feature_count"]),
            groups=groups,
            exclusions=exclusions,
            selection_basis=tuple(str(item) for item in payload.get("selection_basis", [])),
            guardrails=tuple((str(key), value) for key, value in payload.get("guardrails", {}).items()),
        )
        config.validate()
        return config

    @staticmethod
    def _parse_feature_groups(
        payload: Any,
        field_name: str,
    ) -> tuple[tuple[str, tuple[str, ...]], ...]:
        if field_name == "exclusions" and payload in (None, {}):
            return ()
        if not isinstance(payload, dict) or not payload:
            raise ValueError(f"{field_name} must be a non-empty mapping.")
        result: list[tuple[str, tuple[str, ...]]] = []
        for name, values in payload.items():
            if not isinstance(values, list) or not values:
                raise ValueError(f"{field_name}.{name} must be a non-empty list.")
            result.append((str(name), tuple(str(value) for value in values)))
        return tuple(result)

    def validate(self) -> None:
        selected = self.selected_features
        excluded = self.excluded_features
        duplicate_selected = sorted({item for item in selected if selected.count(item) > 1})
        duplicate_excluded = sorted({item for item in excluded if excluded.count(item) > 1})
        overlap = sorted(set(selected) & set(excluded))

        if duplicate_selected:
            raise ValueError(f"Duplicate selected features: {duplicate_selected}")
        if duplicate_excluded:
            raise ValueError(f"Duplicate excluded features: {duplicate_excluded}")
        if overlap:
            raise ValueError(f"Features cannot be both selected and excluded: {overlap}")
        if len(selected) != self.expected_feature_count:
            raise ValueError(
                f"Expected {self.expected_feature_count} selected features, found {len(selected)}."
            )
        if self.status != "candidate_for_cv":
            raise ValueError("A newly selected feature set must have status candidate_for_cv.")
        if not self.selection_basis:
            raise ValueError("selection_basis must document how the feature set was selected.")

    def validate_source(self, manifest: dict[str, Any]) -> None:
        if manifest.get("dataset_version") != self.source_dataset_version:
            raise ValueError(
                "Source dataset mismatch: "
                f"expected {self.source_dataset_version}, got {manifest.get('dataset_version')}."
            )
        feature_dependency = manifest.get("feature_dependency", {})
        if feature_dependency.get("version") != self.source_feature_version:
            raise ValueError(
                "Source feature version mismatch: "
                f"expected {self.source_feature_version}, got {feature_dependency.get('version')}."
            )

        source_features = list(manifest.get("feature_columns", []))
        source_set = set(source_features)
        unknown = sorted((set(self.selected_features) | set(self.excluded_features)) - source_set)
        unclassified = sorted(source_set - set(self.selected_features) - set(self.excluded_features))
        if unknown:
            raise ValueError(f"Selection references unknown source features: {unknown}")
        if unclassified:
            raise ValueError(f"Source features are not classified by the selection: {unclassified}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_version": self.selection_version,
            "dataset_version": self.dataset_version,
            "source_dataset_version": self.source_dataset_version,
            "source_feature_version": self.source_feature_version,
            "status": self.status,
            "expected_feature_count": self.expected_feature_count,
            "feature_groups": self.groups_by_name,
            "exclusions": self.exclusions_by_reason,
            "selection_basis": list(self.selection_basis),
            "guardrails": self.guardrails_by_name,
        }
