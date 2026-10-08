"""Causal Top-K advisory policy with empirical rank confidence gates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
import yaml


@dataclass(frozen=True)
class AdvisoryPolicyConfig:
    """Parameters for an abstaining daily stock-selection policy."""

    policy_version: str
    score_column: str
    top_k_max: int
    minimum_distinct_scores: int
    confidence_level: float
    minimum_history_folds: int
    minimum_history_effective_samples: float
    minimum_precision_lift_lower_bound: float
    bearish_upper: float
    bullish_lower: float
    market_regime_feature: str
    rank_bucket_ends: tuple[int, ...] = ()
    top_k_candidates: tuple[int, ...] = ()
    minimum_distinct_scores_candidates: tuple[int, ...] = ()
    minimum_history_effective_samples_candidates: tuple[float, ...] = ()

    @classmethod
    def from_yaml(cls, path: Path) -> AdvisoryPolicyConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        ranking = payload["ranking"]
        confidence = payload["confidence"]
        regime = payload["market_regime"]
        config = cls(
            policy_version=str(payload["policy_version"]),
            score_column=str(ranking["score_column"]),
            top_k_max=int(ranking["top_k_max"]),
            minimum_distinct_scores=int(ranking["minimum_distinct_scores"]),
            confidence_level=float(confidence["level"]),
            minimum_history_folds=int(confidence["minimum_history_folds"]),
            minimum_history_effective_samples=float(confidence["minimum_history_effective_samples"]),
            minimum_precision_lift_lower_bound=float(
                confidence["minimum_precision_lift_lower_bound"]
            ),
            bearish_upper=float(regime["bearish_upper"]),
            bullish_lower=float(regime["bullish_lower"]),
            market_regime_feature=str(regime["feature"]),
            rank_bucket_ends=tuple(int(value) for value in ranking["rank_bucket_ends"]),
            top_k_candidates=tuple(int(value) for value in ranking.get("top_k_candidates", [])),
            minimum_distinct_scores_candidates=tuple(
                int(value) for value in ranking.get("minimum_distinct_scores_candidates", [])
            ),
            minimum_history_effective_samples_candidates=tuple(
                float(value)
                for value in confidence.get("minimum_history_effective_samples_candidates", [])
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.top_k_max <= 0:
            raise ValueError("top_k_max must be positive.")
        if not 1 <= self.minimum_distinct_scores <= self.top_k_max:
            raise ValueError("minimum_distinct_scores must be in [1, top_k_max].")
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence level must be in (0, 1).")
        if self.minimum_history_effective_samples <= 0:
            raise ValueError("minimum_history_effective_samples must be positive.")
        if self.minimum_history_folds <= 0:
            raise ValueError("minimum_history_folds must be positive.")
        if self.minimum_precision_lift_lower_bound <= 0:
            raise ValueError("minimum_precision_lift_lower_bound must be positive.")
        if any(value <= 0 for value in self.top_k_candidates):
            raise ValueError("top_k_candidates must be positive.")
        if any(value <= 0 for value in self.minimum_history_effective_samples_candidates):
            raise ValueError("minimum history candidates must be positive.")
        if not self.rank_bucket_ends or any(
            value <= 0 for value in self.rank_bucket_ends
        ):
            raise ValueError("rank_bucket_ends must contain positive rank endpoints.")
        if tuple(sorted(set(self.rank_bucket_ends))) != self.rank_bucket_ends:
            raise ValueError("rank_bucket_ends must be strictly increasing.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "ranking": {
                "score_column": self.score_column,
                "top_k_max": self.top_k_max,
                "minimum_distinct_scores": self.minimum_distinct_scores,
                "top_k_candidates": list(self.top_k_candidates),
                "minimum_distinct_scores_candidates": list(
                    self.minimum_distinct_scores_candidates
                ),
                "rank_bucket_ends": list(self.rank_bucket_ends),
            },
            "confidence": {
                "level": self.confidence_level,
                "minimum_history_folds": self.minimum_history_folds,
                "minimum_history_effective_samples": self.minimum_history_effective_samples,
                "minimum_precision_lift_lower_bound": self.minimum_precision_lift_lower_bound,
                "minimum_history_effective_samples_candidates": list(
                    self.minimum_history_effective_samples_candidates
                ),
            },
            "market_regime": {
                "feature": self.market_regime_feature,
                "bearish_upper": self.bearish_upper,
                "bullish_lower": self.bullish_lower,
            },
        }

    def candidate_policies(self) -> list[AdvisoryPolicyConfig]:
        """Return only the policy candidates declared in the configuration."""
        top_k_values = self.top_k_candidates or (self.top_k_max,)
        distinct_values = self.minimum_distinct_scores_candidates or (
            self.minimum_distinct_scores,
        )
        history_values = self.minimum_history_effective_samples_candidates or (
            self.minimum_history_effective_samples,
        )
        candidates: list[AdvisoryPolicyConfig] = []
        seen: set[tuple[int, int, float]] = set()
        for top_k, minimum_distinct, minimum_history in product(
            top_k_values, distinct_values, history_values
        ):
            if minimum_distinct > top_k:
                continue
            key = (top_k, minimum_distinct, minimum_history)
            if key not in seen:
                candidates.append(
                    replace(
                        self,
                        top_k_max=top_k,
                        minimum_distinct_scores=minimum_distinct,
                        minimum_history_effective_samples=minimum_history,
                    )
                )
                seen.add(key)
        if not candidates:
            raise ValueError("No valid advisory policy candidates were configured.")
        return candidates


def add_market_regime(frame: pd.DataFrame, config: AdvisoryPolicyConfig) -> pd.DataFrame:
    """Add a stable three-state market regime from a configured feature."""
    if config.market_regime_feature not in frame:
        raise ValueError(f"Missing market regime feature: {config.market_regime_feature}")
    result = frame.copy()
    values = result[config.market_regime_feature]
    if values.isna().any():
        raise ValueError("Market regime feature contains missing values.")
    result["market_regime"] = np.select(
        [values <= config.bearish_upper, values >= config.bullish_lower],
        ["bearish", "bullish"],
        default="neutral",
    )
    return result


def assign_daily_ranks(frame: pd.DataFrame, config: AdvisoryPolicyConfig) -> pd.DataFrame:
    """Rank candidates deterministically within a trading day using the entry score only."""
    required = {"date", "symbol", config.score_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing ranking columns: {missing}")
    if frame[config.score_column].isna().any():
        raise ValueError("Ranking score contains missing values.")
    result = frame.sort_values(
        ["date", config.score_column, "symbol"],
        ascending=[True, False, True],
        kind="stable",
    ).copy()
    result["daily_rank"] = result.groupby("date", sort=False).cumcount() + 1
    result["daily_score_levels"] = result.groupby("date", sort=False)[config.score_column].transform(
        "nunique"
    )
    starts = (1, *(endpoint + 1 for endpoint in config.rank_bucket_ends[:-1]))
    labels = [
        f"rank_{start}_{endpoint}" if start != endpoint else f"rank_{endpoint}"
        for start, endpoint in zip(starts, config.rank_bucket_ends, strict=True)
    ]
    labels.append(f"rank_{config.rank_bucket_ends[-1] + 1}_plus")
    result["rank_bucket"] = np.select(
        [result["daily_rank"].le(endpoint) for endpoint in config.rank_bucket_ends],
        labels[:-1],
        default=labels[-1],
    )
    return result


def weighted_rate_and_effective_n(frame: pd.DataFrame) -> tuple[float, float]:
    """Return event-weighted rate and Kish effective sample size."""
    if frame.empty:
        return float("nan"), 0.0
    weight = frame["sample_weight"].to_numpy(dtype=float)
    target = frame["y_entry"].to_numpy(dtype=float)
    total_weight = weight.sum()
    if total_weight <= 0:
        return float("nan"), 0.0
    rate = float(np.average(target, weights=weight))
    effective_n = float(total_weight**2 / np.square(weight).sum())
    return rate, effective_n


def wilson_lower_bound(rate: float, effective_n: float, confidence_level: float) -> float:
    """Conservative lower bound for a weighted rate using effective sample size."""
    if not np.isfinite(rate) or effective_n <= 0:
        return float("nan")
    z = NormalDist().inv_cdf(1 - (1 - confidence_level) / 2)
    denominator = 1 + z**2 / effective_n
    centre = rate + z**2 / (2 * effective_n)
    radius = z * np.sqrt(rate * (1 - rate) / effective_n + z**2 / (4 * effective_n**2))
    return float(max(0.0, (centre - radius) / denominator))


def history_statistics(
    history: pd.DataFrame,
    regime: str,
    rank_bucket: str,
    config: AdvisoryPolicyConfig,
) -> dict[str, float]:
    """Estimate a candidate's empirical probability without reading future folds."""
    regime_history = history.loc[history["market_regime"].eq(regime)]
    bucket_history = regime_history.loc[regime_history["rank_bucket"].eq(rank_bucket)]
    rate, effective_n = weighted_rate_and_effective_n(bucket_history)
    base_rate, _ = weighted_rate_and_effective_n(regime_history)
    return {
        "empirical_probability": rate,
        "confidence_lower_bound": wilson_lower_bound(
            rate, effective_n, config.confidence_level
        ),
        "history_effective_samples": effective_n,
        "history_folds": float(bucket_history["fold_id"].nunique()),
        "history_regime_base_rate": base_rate,
    }


def build_confidence_profile(
    history: pd.DataFrame,
    config: AdvisoryPolicyConfig,
) -> pd.DataFrame:
    """Freeze empirical rank/regime confidence statistics for live inference."""
    required = {"fold_id", "y_entry", "sample_weight", "market_regime", "rank_bucket"}
    missing = sorted(required - set(history.columns))
    if missing:
        raise ValueError(f"History is missing profile columns: {missing}")
    records: list[dict[str, Any]] = []
    for regime, regime_history in history.groupby("market_regime", sort=True):
        base_rate, _ = weighted_rate_and_effective_n(regime_history)
        for bucket, bucket_history in regime_history.groupby("rank_bucket", sort=True):
            rate, effective_n = weighted_rate_and_effective_n(bucket_history)
            lower_bound = wilson_lower_bound(rate, effective_n, config.confidence_level)
            records.append(
                {
                    "market_regime": regime,
                    "rank_bucket": bucket,
                    "empirical_probability": rate,
                    "confidence_lower_bound": lower_bound,
                    "history_effective_samples": effective_n,
                    "history_folds": int(bucket_history["fold_id"].nunique()),
                    "history_regime_base_rate": base_rate,
                    "confidence_lift_lower_bound": lower_bound / base_rate
                    if np.isfinite(base_rate) and base_rate > 0
                    else np.nan,
                }
            )
    return pd.DataFrame(records).sort_values(["market_regime", "rank_bucket"]).reset_index(
        drop=True
    )


def apply_advisory_profile(
    frame: pd.DataFrame,
    profile: pd.DataFrame,
    config: AdvisoryPolicyConfig,
) -> pd.DataFrame:
    """Apply a frozen empirical confidence profile to live daily predictions."""
    required = {
        "market_regime",
        "rank_bucket",
        "empirical_probability",
        "confidence_lower_bound",
        "history_effective_samples",
        "history_folds",
        "history_regime_base_rate",
        "confidence_lift_lower_bound",
    }
    missing = sorted(required - set(profile.columns))
    if missing:
        raise ValueError(f"Confidence profile is missing columns: {missing}")
    ranked = assign_daily_ranks(add_market_regime(frame, config), config)
    ranked["advisory_status"] = "NOT_TOP_K"
    ranked["advisory_reason"] = "outside_top_k"
    candidates = ranked["daily_rank"].le(config.top_k_max)
    ranked.loc[candidates, "advisory_status"] = "ABSTAIN"
    ranked = ranked.merge(
        profile,
        on=["market_regime", "rank_bucket"],
        how="left",
        validate="many_to_one",
    )
    low_resolution = candidates & ranked["daily_score_levels"].lt(config.minimum_distinct_scores)
    ranked.loc[low_resolution, "advisory_reason"] = "insufficient_daily_score_resolution"
    history_missing = candidates & ranked["history_effective_samples"].isna()
    ranked.loc[history_missing, "advisory_reason"] = "insufficient_regime_history"
    insufficient_rows = candidates & ranked["history_effective_samples"].lt(
        config.minimum_history_effective_samples
    )
    ranked.loc[insufficient_rows, "advisory_reason"] = "insufficient_regime_history"
    insufficient_periods = candidates & ranked["history_folds"].lt(config.minimum_history_folds)
    ranked.loc[insufficient_periods, "advisory_reason"] = "insufficient_prior_regime_periods"
    weak_confidence = candidates & ranked["confidence_lift_lower_bound"].lt(
        config.minimum_precision_lift_lower_bound
    )
    ranked.loc[weak_confidence, "advisory_reason"] = (
        "historical_precision_lower_bound_below_gate"
    )
    passed = (
        candidates
        & ~low_resolution
        & ~history_missing
        & ~insufficient_rows
        & ~insufficient_periods
        & ~weak_confidence
    )
    ranked.loc[passed, "advisory_status"] = "PASS"
    ranked.loc[passed, "advisory_reason"] = "rank_regime_confidence_gate_passed"
    return ranked.sort_values(["date", "daily_rank", "symbol"], kind="stable").reset_index(drop=True)


def apply_temporal_advisory_policy(
    frame: pd.DataFrame,
    config: AdvisoryPolicyConfig,
) -> pd.DataFrame:
    """Apply a causal 0..K policy using only strictly preceding OOF folds as history."""
    required = {
        "fold_id",
        "date",
        "symbol",
        "y_entry",
        "sample_weight",
        config.score_column,
        config.market_regime_feature,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing advisory columns: {missing}")

    ranked = assign_daily_ranks(add_market_regime(frame, config), config)
    ranked["advisory_status"] = "NOT_TOP_K"
    ranked["advisory_reason"] = "outside_top_k"
    ranked["empirical_probability"] = np.nan
    ranked["confidence_lower_bound"] = np.nan
    ranked["history_effective_samples"] = np.nan
    ranked["history_regime_base_rate"] = np.nan
    ranked["confidence_lift_lower_bound"] = np.nan

    folds = sorted(ranked["fold_id"].unique())
    for position, fold_id in enumerate(folds):
        current_mask = ranked["fold_id"].eq(fold_id)
        candidate_mask = current_mask & ranked["daily_rank"].le(config.top_k_max)
        ranked.loc[candidate_mask, "advisory_status"] = "ABSTAIN"
        if position == 0:
            ranked.loc[candidate_mask, "advisory_reason"] = "insufficient_prior_history"
            continue

        history = ranked.loc[ranked["fold_id"].isin(folds[:position])]
        for index, row in ranked.loc[candidate_mask].iterrows():
            if row["daily_score_levels"] < config.minimum_distinct_scores:
                ranked.loc[index, "advisory_reason"] = "insufficient_daily_score_resolution"
                continue
            statistics = history_statistics(
                history,
                str(row["market_regime"]),
                str(row["rank_bucket"]),
                config,
            )
            for name, value in statistics.items():
                ranked.loc[index, name] = value
            base_rate = statistics["history_regime_base_rate"]
            lower_bound = statistics["confidence_lower_bound"]
            if statistics["history_effective_samples"] < config.minimum_history_effective_samples:
                ranked.loc[index, "advisory_reason"] = "insufficient_regime_history"
                continue
            if statistics["history_folds"] < config.minimum_history_folds:
                ranked.loc[index, "advisory_reason"] = "insufficient_prior_regime_periods"
                continue
            if not np.isfinite(base_rate) or base_rate <= 0:
                ranked.loc[index, "advisory_reason"] = "missing_regime_base_rate"
                continue
            lift = lower_bound / base_rate
            ranked.loc[index, "confidence_lift_lower_bound"] = lift
            if lift < config.minimum_precision_lift_lower_bound:
                ranked.loc[index, "advisory_reason"] = "historical_precision_lower_bound_below_gate"
                continue
            ranked.loc[index, "advisory_status"] = "PASS"
            ranked.loc[index, "advisory_reason"] = "rank_regime_confidence_gate_passed"
    return ranked.sort_values(["date", "daily_rank", "symbol"], kind="stable").reset_index(drop=True)


def advisory_summary(frame: pd.DataFrame) -> dict[str, Any]:
    """Compute event-weighted performance and abstention coverage for PASS candidates."""
    selected = frame.loc[frame["advisory_status"].eq("PASS")]
    daily = frame.groupby("date", sort=True)["advisory_status"].apply(
        lambda value: int(value.eq("PASS").sum())
    )
    precision, _ = weighted_rate_and_effective_n(selected)
    base_rate, _ = weighted_rate_and_effective_n(frame)
    return {
        "days": int(daily.size),
        "days_with_recommendations": int(daily.gt(0).sum()),
        "abstain_days": int(daily.eq(0).sum()),
        "coverage_days": float(daily.gt(0).mean()),
        "selected_rows": int(len(selected)),
        "selected_event_weighted_precision": precision,
        "base_event_weighted_rate": base_rate,
        "selected_precision_lift": float(precision / base_rate)
        if np.isfinite(precision) and base_rate > 0
        else float("nan"),
        "selected_positive_rows": int(selected["y_entry"].sum()),
        "reason_counts": frame.loc[frame["advisory_status"].ne("NOT_TOP_K"), "advisory_reason"]
        .value_counts()
        .to_dict(),
    }


def _selection_utility(frame: pd.DataFrame, config: AdvisoryPolicyConfig) -> dict[str, float]:
    """Score a candidate using only already-resolved causal decisions."""
    summary = advisory_summary(frame)
    selected = frame.loc[frame["advisory_status"].eq("PASS")]
    precision, effective_n = weighted_rate_and_effective_n(selected)
    lower_bound = wilson_lower_bound(precision, effective_n, config.confidence_level)
    base_rate = float(summary["base_event_weighted_rate"])
    coverage = float(summary["coverage_days"])
    lift_lower_bound = lower_bound / base_rate if base_rate > 0 else float("nan")
    # A no-trade policy has no utility. Square-root coverage prevents a broad,
    # weak policy from winning merely because it issues more recommendations.
    utility = lift_lower_bound * np.sqrt(coverage) if coverage > 0 else float("-inf")
    return {
        "utility": float(utility),
        "selected_precision": precision,
        "selected_effective_samples": effective_n,
        "selected_precision_lower_bound": lower_bound,
        "selected_precision_lift_lower_bound": lift_lower_bound,
        "coverage_days": coverage,
    }


def select_policy_from_history(
    history: pd.DataFrame,
    config: AdvisoryPolicyConfig,
) -> tuple[AdvisoryPolicyConfig, list[dict[str, Any]]]:
    """Choose a declared policy from past folds, never its evaluation fold."""
    if history.empty:
        raise ValueError("Cannot select an advisory policy without history.")
    audit: list[dict[str, Any]] = []
    for candidate in config.candidate_policies():
        evaluated = apply_temporal_advisory_policy(history, candidate)
        audit.append(
            {
                "top_k_max": candidate.top_k_max,
                "minimum_distinct_scores": candidate.minimum_distinct_scores,
                "minimum_history_effective_samples": candidate.minimum_history_effective_samples,
                **_selection_utility(evaluated, candidate),
            }
        )
    eligible = [entry for entry in audit if np.isfinite(entry["utility"])]
    if not eligible:
        # Deterministic conservative fallback: it normally abstains until the
        # history is sufficient, rather than forcing a selection.
        return config.candidate_policies()[0], audit
    winner = sorted(
        eligible,
        key=lambda entry: (
            -entry["utility"],
            entry["top_k_max"],
            -entry["minimum_distinct_scores"],
            -entry["minimum_history_effective_samples"],
        ),
    )[0]
    return (
        replace(
            config,
            top_k_max=int(winner["top_k_max"]),
            minimum_distinct_scores=int(winner["minimum_distinct_scores"]),
            minimum_history_effective_samples=float(winner["minimum_history_effective_samples"]),
        ),
        audit,
    )


def apply_nested_temporal_advisory_policy(
    frame: pd.DataFrame,
    config: AdvisoryPolicyConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select policy on prior folds and score the next fold without leakage."""
    required = {
        "fold_id",
        "date",
        "symbol",
        "y_entry",
        "sample_weight",
        config.score_column,
        config.market_regime_feature,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing nested-policy columns: {missing}")
    folds = sorted(frame["fold_id"].unique())
    outputs: list[pd.DataFrame] = []
    audit: list[dict[str, Any]] = []
    for position, fold_id in enumerate(folds):
        visible = frame.loc[frame["fold_id"].isin(folds[: position + 1])].copy()
        if position == 0:
            selected_config = config.candidate_policies()[0]
            candidate_audit: list[dict[str, Any]] = []
            selection_status = "insufficient_prior_history"
        else:
            history = frame.loc[frame["fold_id"].isin(folds[:position])].copy()
            selected_config, candidate_audit = select_policy_from_history(history, config)
            selection_status = "selected_from_prior_folds"
        scored = apply_temporal_advisory_policy(visible, selected_config)
        current = scored.loc[scored["fold_id"].eq(fold_id)].copy()
        current["selected_top_k_max"] = selected_config.top_k_max
        current["selected_minimum_distinct_scores"] = selected_config.minimum_distinct_scores
        current["selected_minimum_history_effective_samples"] = (
            selected_config.minimum_history_effective_samples
        )
        outputs.append(current)
        audit.append(
            {
                "fold_id": fold_id,
                "selection_status": selection_status,
                "selected_policy": {
                    "top_k_max": selected_config.top_k_max,
                    "minimum_distinct_scores": selected_config.minimum_distinct_scores,
                    "minimum_history_effective_samples": selected_config.minimum_history_effective_samples,
                },
                "candidate_audit": candidate_audit,
            }
        )
    return pd.concat(outputs, ignore_index=True), pd.DataFrame(audit)


def month_block_bootstrap_comparison(
    frame: pd.DataFrame,
    config: AdvisoryPolicyConfig,
    *,
    samples: int,
    random_seed: int,
) -> dict[str, Any]:
    """Compare gated selection with forced Top-K using paired calendar-month blocks."""
    if samples <= 0:
        raise ValueError("Bootstrap samples must be positive.")
    required = {"date", "y_entry", "sample_weight", "daily_rank", "advisory_status"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing bootstrap columns: {missing}")
    data = frame.copy()
    data["bootstrap_month"] = pd.to_datetime(data["date"]).dt.to_period("M").astype(str)
    forced = data.loc[data["daily_rank"].le(config.top_k_max)]
    gated = data.loc[data["advisory_status"].eq("PASS")]
    months = np.asarray(sorted(data["bootstrap_month"].unique()))
    if not len(months):
        raise ValueError("Bootstrap requires at least one calendar month.")

    def aggregate(values: pd.DataFrame) -> pd.DataFrame:
        grouped = values.groupby("bootstrap_month", sort=True).apply(
            lambda group: pd.Series(
                {
                    "positive_weight": float((group["y_entry"] * group["sample_weight"]).sum()),
                    "weight": float(group["sample_weight"].sum()),
                }
            ),
            include_groups=False,
        )
        return grouped.reindex(months, fill_value=0.0)

    base = aggregate(data).to_numpy(dtype=float)
    forced_values = aggregate(forced).to_numpy(dtype=float)
    gated_values = aggregate(gated).to_numpy(dtype=float)
    random = np.random.default_rng(random_seed)
    values: list[tuple[float, float, float]] = []
    for _ in range(samples):
        indices = random.integers(0, len(months), size=len(months))
        base_positive, base_weight = base[indices].sum(axis=0)
        forced_positive, forced_weight = forced_values[indices].sum(axis=0)
        gated_positive, gated_weight = gated_values[indices].sum(axis=0)
        if gated_weight <= 0 or base_weight <= 0 or forced_weight <= 0:
            continue
        gated_precision = gated_positive / gated_weight
        forced_precision = forced_positive / forced_weight
        values.append(
            (
                gated_precision,
                gated_precision / (base_positive / base_weight),
                gated_precision - forced_precision,
            )
        )
    if not values:
        raise RuntimeError("No valid bootstrap replications were produced.")
    matrix = np.asarray(values)

    def interval(column: int) -> dict[str, float]:
        lower, median, upper = np.quantile(matrix[:, column], [0.025, 0.5, 0.975])
        return {"lower": float(lower), "median": float(median), "upper": float(upper)}

    return {
        "method": "paired_calendar_month_block_bootstrap",
        "requested_samples": samples,
        "valid_samples": len(values),
        "gated_precision": interval(0),
        "gated_precision_lift": interval(1),
        "precision_difference_vs_forced_top_k": interval(2),
    }
