"""Auditable evaluation for frozen wave-model artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from src.training.xgboost_pipeline import classification_metrics, regression_metrics


@dataclass(frozen=True)
class EvaluationConfig:
    evaluation_version: str
    random_seed: int
    bootstrap_samples: int
    confidence_level: float
    minimum_segment_rows: int
    calibration_bins: int
    top_fractions: tuple[float, ...]
    industry_column: str
    market_regime_feature: str
    bearish_upper: float
    bullish_lower: float
    liquidity_feature: str
    liquidity_quantiles: tuple[float, float]
    acceptance_gates: dict[str, Any]
    backtest: dict[str, Any]

    @classmethod
    def from_yaml(cls, path: Path) -> EvaluationConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        segmentation = payload["segmentation"]
        quantiles = tuple(float(value) for value in segmentation["liquidity_quantiles"])
        if len(quantiles) != 2 or not 0 < quantiles[0] < quantiles[1] < 1:
            raise ValueError("liquidity_quantiles must contain two increasing values in (0, 1).")
        fractions = tuple(float(value) for value in payload["ranking"]["top_fractions"])
        if not fractions or any(not 0 < value <= 1 for value in fractions):
            raise ValueError("All ranking top_fractions must be in (0, 1].")
        confidence = float(payload["confidence_level"])
        if not 0 < confidence < 1:
            raise ValueError("confidence_level must be in (0, 1).")
        return cls(
            evaluation_version=str(payload["evaluation_version"]),
            random_seed=int(payload["random_seed"]),
            bootstrap_samples=int(payload["bootstrap_samples"]),
            confidence_level=confidence,
            minimum_segment_rows=int(payload["minimum_segment_rows"]),
            calibration_bins=int(payload["calibration_bins"]),
            top_fractions=fractions,
            industry_column=str(segmentation["industry_column"]),
            market_regime_feature=str(segmentation["market_regime_feature"]),
            bearish_upper=float(segmentation["bearish_upper"]),
            bullish_lower=float(segmentation["bullish_lower"]),
            liquidity_feature=str(segmentation["liquidity_feature"]),
            liquidity_quantiles=(quantiles[0], quantiles[1]),
            acceptance_gates=dict(payload["acceptance_gates"]),
            backtest=dict(payload.get("backtest", {})),
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(artifact_directory: Path) -> dict[str, Any]:
    """Fail closed when a frozen artifact file is missing or changed."""
    manifest_path = artifact_directory / "artifact_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("artifact_manifest.json is missing; artifact is not frozen.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("immutable"):
        raise RuntimeError("Artifact manifest does not declare immutable=true.")
    for record in manifest.get("files", []):
        relative_path = Path(record["path"])
        path = artifact_directory / relative_path
        if not path.is_file():
            raise RuntimeError(f"Frozen artifact file is missing: {relative_path}")
        if path.stat().st_size != int(record["size_bytes"]):
            raise RuntimeError(f"Frozen artifact size mismatch: {relative_path}")
        if sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"Frozen artifact checksum mismatch: {relative_path}")
    return manifest


def add_segments(frame: pd.DataFrame, config: EvaluationConfig) -> pd.DataFrame:
    result = frame.copy()
    result["calendar_year"] = pd.to_datetime(result["date"]).dt.year.astype(str)
    regime = result[config.market_regime_feature]
    result["market_regime"] = np.select(
        [regime <= config.bearish_upper, regime >= config.bullish_lower],
        ["bearish", "bullish"],
        default="neutral",
    )
    low_quantile, high_quantile = config.liquidity_quantiles
    low = result[config.liquidity_feature].quantile(low_quantile)
    high = result[config.liquidity_feature].quantile(high_quantile)
    result["liquidity_bucket"] = np.select(
        [result[config.liquidity_feature] <= low, result[config.liquidity_feature] >= high],
        ["low", "high"],
        default="medium",
    )
    result[config.industry_column] = result[config.industry_column].fillna("UNKNOWN")
    return result


def daily_top_fraction_metrics(
    frame: pd.DataFrame,
    probability_column: str,
    top_fraction: float,
) -> dict[str, float]:
    daily_rows: list[dict[str, float]] = []
    for _, group in frame.groupby("date", sort=True):
        top_count = max(1, int(np.ceil(len(group) * top_fraction)))
        selected = group.nlargest(top_count, probability_column)
        weights = selected["sample_weight"].to_numpy(dtype=float)
        labels = selected["y_entry"].to_numpy(dtype=float)
        daily_rows.append(
            {
                "precision": float(labels.mean()),
                "weighted_precision": float(np.average(labels, weights=weights)),
                "selected": float(top_count),
                "universe": float(len(group)),
            }
        )
    daily = pd.DataFrame(daily_rows)
    return {
        "top_fraction": top_fraction,
        "trading_days": float(len(daily)),
        "mean_daily_precision": float(daily["precision"].mean()),
        "median_daily_precision": float(daily["precision"].median()),
        "mean_daily_weighted_precision": float(daily["weighted_precision"].mean()),
        "mean_daily_selected": float(daily["selected"].mean()),
        "mean_daily_universe": float(daily["universe"].mean()),
    }


def daily_top_k_metrics(
    frame: pd.DataFrame,
    probability_column: str,
    *,
    k: int = 10,
    target_column: str = "y_entry",
    weight_column: str = "sample_weight",
) -> pd.DataFrame:
    """Return one deterministic Top-K metric row for every scoring date.

    Scores are ordered descending and ties are broken by ascending symbol.  An
    unresolved target remains in the operational shortlist and is reported as
    unknown; it contributes no known hit rather than being silently removed.
    """
    if k <= 0:
        raise ValueError("k must be positive.")
    required = {"date", "symbol", probability_column, target_column, weight_column}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Daily Top-K frame is missing: {missing}")
    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"], errors="raise")
    working[probability_column] = pd.to_numeric(working[probability_column], errors="coerce")
    working[weight_column] = pd.to_numeric(working[weight_column], errors="coerce")
    working = working.loc[
        working[probability_column].notna() & working[weight_column].notna()
    ].copy()
    ordered = working.sort_values(
        ["date", probability_column, "symbol"],
        ascending=[True, False, True],
        kind="stable",
    )
    records: list[dict[str, float | int | pd.Timestamp]] = []
    for date, group in ordered.groupby("date", observed=True, sort=False):
        selected = group.head(k).copy()
        selected_target = pd.to_numeric(selected[target_column], errors="coerce")
        full_target = pd.to_numeric(group[target_column], errors="coerce")
        relevant = selected_target.fillna(0.0).to_numpy(dtype=float)
        selected_weights = selected[weight_column].to_numpy(dtype=float)
        resolved = selected_target.notna().to_numpy()
        resolved_full = full_target.notna().to_numpy()
        ranks = np.arange(1, len(selected) + 1, dtype=float)
        cumulative_hits = np.cumsum(relevant)
        precision_at_rank = cumulative_hits / ranks
        positive_in_universe = int(full_target.eq(1).sum())
        map_denominator = min(k, positive_in_universe)
        average_precision_at_k = (
            float(np.sum(precision_at_rank * relevant) / map_denominator)
            if map_denominator
            else 0.0
        )
        discounts = 1.0 / np.log2(ranks + 1.0)
        dcg = float(np.sum(relevant * discounts))
        ideal_count = min(k, positive_in_universe)
        ideal_dcg = float(np.sum(discounts[:ideal_count]))
        universe_weights = group.loc[resolved_full, weight_column].to_numpy(dtype=float)
        universe_labels = full_target.loc[resolved_full].to_numpy(dtype=float)
        base_rate = (
            float(np.average(universe_labels, weights=universe_weights))
            if universe_weights.sum() > 0
            else np.nan
        )
        weighted_precision = (
            float(np.average(relevant, weights=selected_weights))
            if selected_weights.sum() > 0
            else np.nan
        )
        precision = float(relevant.mean()) if len(relevant) else np.nan
        records.append(
            {
                "date": date,
                "k": int(k),
                "universe_rows": int(len(group)),
                "universe_resolved_rows": int(resolved_full.sum()),
                "selected_rows": int(len(selected)),
                "selected_resolved_rows": int(resolved.sum()),
                "selected_unknown_rows": int((~resolved).sum()),
                "precision_at_k": precision,
                "weighted_precision_at_k": weighted_precision,
                "map_at_k": average_precision_at_k,
                "ndcg_at_k": float(dcg / ideal_dcg) if ideal_dcg else 0.0,
                "hit_rate_at_k": float(relevant.any()),
                "base_rate": base_rate,
                "lift": float(precision / base_rate) if base_rate and base_rate > 0 else np.nan,
            }
        )
    return pd.DataFrame(records)


def paired_daily_ranking_comparison(
    champion: pd.DataFrame,
    challenger: pd.DataFrame,
    *,
    metric_columns: tuple[str, ...] = (
        "precision_at_k",
        "map_at_k",
        "ndcg_at_k",
        "hit_rate_at_k",
        "lift",
    ),
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    """Compare candidates only on their shared daily evaluation dates."""
    if champion["date"].duplicated().any() or challenger["date"].duplicated().any():
        raise ValueError("Paired daily comparison requires at most one row per date.")
    missing = sorted(
        set(metric_columns).difference(champion.columns).union(
            set(metric_columns).difference(challenger.columns)
        )
    )
    if missing:
        raise ValueError(f"Paired daily comparison is missing metrics: {missing}")
    left = champion.loc[:, ["date", *metric_columns]].rename(
        columns={column: f"champion_{column}" for column in metric_columns}
    )
    right = challenger.loc[:, ["date", *metric_columns]].rename(
        columns={column: f"challenger_{column}" for column in metric_columns}
    )
    paired = left.merge(right, on="date", how="inner", validate="one_to_one").sort_values("date")
    summary: dict[str, float | int] = {"paired_dates": int(len(paired))}
    for metric in metric_columns:
        delta = paired[f"challenger_{metric}"] - paired[f"champion_{metric}"]
        paired[f"delta_{metric}"] = delta
        summary[f"mean_delta_{metric}"] = float(delta.mean()) if len(delta) else np.nan
    return paired, summary


def moving_block_bootstrap_paired_daily(
    paired: pd.DataFrame,
    metric: str,
    *,
    samples: int,
    random_seed: int,
    block_size: int,
    confidence_level: float = 0.95,
) -> dict[str, float | int]:
    """Estimate paired uncertainty while retaining contiguous decision dates."""
    if samples <= 0:
        raise ValueError("samples must be positive.")
    if block_size <= 0:
        raise ValueError("block_size must be positive.")
    column = f"delta_{metric}"
    if column not in paired:
        raise ValueError(f"Paired daily metrics are missing {column}.")
    values = paired.sort_values("date", kind="stable")[column].dropna().to_numpy(dtype=float)
    if not len(values):
        return {"estimate": np.nan, "lower": np.nan, "upper": np.nan, "samples": 0}
    random = np.random.default_rng(random_seed)
    blocks_per_draw = int(np.ceil(len(values) / block_size))
    offsets = np.arange(block_size)
    draws = np.empty(samples, dtype=float)
    for index in range(samples):
        starts = random.integers(0, len(values), size=blocks_per_draw)
        positions = np.concatenate([(start + offsets) % len(values) for start in starts])[: len(values)]
        draws[index] = values[positions].mean()
    alpha = (1.0 - confidence_level) / 2.0
    return {
        "estimate": float(values.mean()),
        "lower": float(np.quantile(draws, alpha)),
        "upper": float(np.quantile(draws, 1.0 - alpha)),
        "samples": int(samples),
        "block_size_dates": int(block_size),
        "blocks_per_draw": blocks_per_draw,
    }


def cluster_bootstrap_daily_top_k(
    frame: pd.DataFrame,
    probability_column: str,
    *,
    k: int,
    samples: int,
    confidence_level: float,
    random_seed: int,
) -> dict[str, dict[str, float]]:
    """Bootstrap daily Top-K metrics by resampling complete date clusters."""
    if samples <= 0:
        return {}
    daily = daily_top_k_metrics(frame, probability_column, k=k)
    if daily.empty:
        return {}
    random = np.random.default_rng(random_seed)
    metrics = ("precision_at_k", "map_at_k", "ndcg_at_k", "hit_rate_at_k", "lift")
    values: dict[str, list[float]] = {metric: [] for metric in metrics}
    for _ in range(samples):
        positions = random.integers(0, len(daily), size=len(daily))
        sampled = daily.iloc[positions]
        for metric in metrics:
            values[metric].append(float(sampled[metric].mean()))
    alpha = (1.0 - confidence_level) / 2.0
    return {
        metric: {
            "estimate": float(np.mean(metric_values)),
            "lower": float(np.quantile(metric_values, alpha)),
            "upper": float(np.quantile(metric_values, 1.0 - alpha)),
        }
        for metric, metric_values in values.items()
        if metric_values
    }


def calibration_table(
    frame: pd.DataFrame,
    probability_column: str,
    bins: int,
) -> pd.DataFrame:
    result = frame[[probability_column, "y_entry", "sample_weight"]].copy()
    result["calibration_bin"] = pd.qcut(
        result[probability_column], q=bins, duplicates="drop"
    )
    records: list[dict[str, float | int | str]] = []
    for interval, group in result.groupby("calibration_bin", observed=True, sort=True):
        weights = group["sample_weight"].to_numpy(dtype=float)
        records.append(
            {
                "bin": str(interval),
                "rows": len(group),
                "weight_mass": float(weights.sum()),
                "minimum_probability": float(group[probability_column].min()),
                "maximum_probability": float(group[probability_column].max()),
                "mean_probability": float(np.average(group[probability_column], weights=weights)),
                "observed_rate": float(np.average(group["y_entry"], weights=weights)),
            }
        )
    return pd.DataFrame(records)


def calibration_diagnostics(calibration: pd.DataFrame) -> dict[str, float]:
    weights = calibration["weight_mass"].to_numpy(dtype=float)
    gap = np.abs(
        calibration["mean_probability"].to_numpy(dtype=float)
        - calibration["observed_rate"].to_numpy(dtype=float)
    )
    return {
        "expected_calibration_error": float(np.average(gap, weights=weights)),
        "maximum_calibration_error": float(gap.max()),
    }


def calibration_slope_intercept(
    frame: pd.DataFrame,
    probability_column: str,
) -> dict[str, float]:
    probability = np.clip(
        frame[probability_column].to_numpy(dtype=float), 1e-6, 1.0 - 1e-6
    )
    logit = np.log(probability / (1.0 - probability)).reshape(-1, 1)
    model = LogisticRegression(C=1e6, solver="lbfgs")
    model.fit(
        logit,
        frame["y_entry"].to_numpy(dtype=int),
        sample_weight=frame["sample_weight"].to_numpy(dtype=float),
    )
    return {
        "calibration_intercept": float(model.intercept_[0]),
        "calibration_slope": float(model.coef_[0, 0]),
    }


def rank_correlation(left: pd.Series, right: pd.Series) -> float:
    valid = left.notna() & right.notna()
    if valid.sum() < 2:
        return float("nan")
    left_rank = left.loc[valid].rank(method="average").to_numpy()
    right_rank = right.loc[valid].rank(method="average").to_numpy()
    if np.std(left_rank) == 0 or np.std(right_rank) == 0:
        return float("nan")
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def strength_diagnostics(frame: pd.DataFrame) -> tuple[dict[str, float], pd.DataFrame]:
    positive = frame["y_entry"].eq(1) & frame["p_strength"].notna()
    selected = frame.loc[positive].copy()
    metrics = regression_metrics(
        selected["y_strength"], selected["p_strength"], selected["sample_weight"]
    )
    for outcome in ("terminal_return", "excess_market_return", "mfe"):
        if outcome in selected:
            metrics[f"spearman_{outcome}"] = rank_correlation(
                selected["p_strength"], selected[outcome]
            )
    selected["strength_bin"] = pd.qcut(
        selected["p_strength"], q=5, duplicates="drop"
    )
    records: list[dict[str, Any]] = []
    for interval, group in selected.groupby("strength_bin", observed=True, sort=True):
        weights = group["sample_weight"].to_numpy(dtype=float)
        record: dict[str, Any] = {
            "bin": str(interval),
            "rows": len(group),
            "mean_predicted_strength": float(
                np.average(group["p_strength"], weights=weights)
            ),
            "mean_observed_strength": float(
                np.average(group["y_strength"], weights=weights)
            ),
        }
        for outcome in ("terminal_return", "excess_market_return", "mfe", "mae"):
            if outcome in group:
                record[f"mean_{outcome}"] = float(
                    np.average(group[outcome], weights=weights)
                )
        records.append(record)
    return metrics, pd.DataFrame(records)


def strength_ranking_comparison(
    frame: pd.DataFrame,
    probability_column: str,
    top_fractions: tuple[float, ...],
) -> pd.DataFrame:
    if frame["p_strength"].isna().any():
        return pd.DataFrame()
    ranked = frame.copy()
    ranked["wave_score"] = ranked[probability_column] * ranked["p_strength"]
    records: list[dict[str, float | str]] = []
    for fraction in top_fractions:
        for score_name, score_column in (
            ("entry_probability", probability_column),
            ("entry_x_strength", "wave_score"),
        ):
            selected_frames = []
            for _, daily in ranked.groupby("date", sort=True):
                count = max(1, int(np.ceil(len(daily) * fraction)))
                selected_frames.append(daily.nlargest(count, score_column))
            selected = pd.concat(selected_frames, ignore_index=True)
            weights = selected["sample_weight"].to_numpy(dtype=float)
            record: dict[str, float | str] = {
                "score": score_name,
                "top_fraction": fraction,
                "selected_rows": float(len(selected)),
                "event_weighted_precision": float(
                    np.average(selected["y_entry"], weights=weights)
                ),
            }
            for outcome in ("terminal_return", "excess_market_return", "mfe"):
                if outcome in selected:
                    record[f"mean_{outcome}"] = float(
                        np.average(selected[outcome], weights=weights)
                    )
            records.append(record)
    return pd.DataFrame(records)


def segment_metrics(
    frame: pd.DataFrame,
    segment_column: str,
    probability_column: str,
    threshold: float,
    top_fraction: float,
    minimum_rows: int,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for segment, group in frame.groupby(segment_column, observed=True, sort=True):
        if len(group) < minimum_rows or group["y_entry"].nunique() < 2:
            continue
        metrics = classification_metrics(
            group["y_entry"],
            group[probability_column],
            group["sample_weight"],
            threshold=threshold,
            top_fraction=top_fraction,
        )
        positive = group["y_entry"].eq(1) & group["p_strength"].notna()
        strength = (
            regression_metrics(
                group.loc[positive, "y_strength"],
                group.loc[positive, "p_strength"],
                group.loc[positive, "sample_weight"],
            )
            if positive.sum() >= 2
            else {}
        )
        records.append(
            {
                "segment_type": segment_column,
                "segment": str(segment),
                **{f"entry_{key}": value for key, value in metrics.items()},
                **{f"strength_{key}": value for key, value in strength.items()},
            }
        )
    return pd.DataFrame(records)


def cluster_bootstrap(
    frame: pd.DataFrame,
    probability_column: str,
    top_fraction: float,
    samples: int,
    confidence_level: float,
    random_seed: int,
) -> dict[str, dict[str, float]]:
    if samples <= 0:
        return {}
    groups = [group.index.to_numpy() for _, group in frame.groupby("date", sort=True)]
    random = np.random.default_rng(random_seed)
    values: dict[str, list[float]] = {
        "average_precision": [],
        "roc_auc": [],
        "weighted_precision_at_fraction": [],
    }
    for _ in range(samples):
        chosen = random.integers(0, len(groups), size=len(groups))
        indices = np.concatenate([groups[index] for index in chosen])
        sample = frame.loc[indices]
        labels = sample["y_entry"].to_numpy(dtype=int)
        probability = sample[probability_column].to_numpy(dtype=float)
        weights = sample["sample_weight"].to_numpy(dtype=float)
        if np.unique(labels).size < 2:
            continue
        top_count = max(1, int(np.ceil(len(sample) * top_fraction)))
        top_indices = np.argsort(-probability, kind="stable")[:top_count]
        values["average_precision"].append(
            float(average_precision_score(labels, probability, sample_weight=weights))
        )
        values["roc_auc"].append(
            float(roc_auc_score(labels, probability, sample_weight=weights))
        )
        values["weighted_precision_at_fraction"].append(
            float(np.average(labels[top_indices], weights=weights[top_indices]))
        )
    alpha = (1.0 - confidence_level) / 2.0
    return {
        metric: {
            "estimate": float(np.mean(metric_values)),
            "lower": float(np.quantile(metric_values, alpha)),
            "upper": float(np.quantile(metric_values, 1.0 - alpha)),
        }
        for metric, metric_values in values.items()
        if metric_values
    }


def evaluate_predictions(
    frame: pd.DataFrame,
    probability_column: str,
    threshold: float,
    config: EvaluationConfig,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    enriched = add_segments(frame, config)
    primary_fraction = 0.05 if 0.05 in config.top_fractions else config.top_fractions[-1]
    overall = classification_metrics(
        enriched["y_entry"],
        enriched[probability_column],
        enriched["sample_weight"],
        threshold=threshold,
        top_fraction=primary_fraction,
    )
    strength, strength_bins = strength_diagnostics(enriched)
    daily_ranking = pd.DataFrame(
        [
            daily_top_fraction_metrics(enriched, probability_column, fraction)
            for fraction in config.top_fractions
        ]
    )
    daily_top_k = pd.concat(
        [
            daily_top_k_metrics(enriched, probability_column, k=top_k)
            for top_k in (5, 10, 20, 50)
        ],
        ignore_index=True,
    )
    segments = pd.concat(
        [
            segment_metrics(
                enriched,
                column,
                probability_column,
                threshold,
                primary_fraction,
                config.minimum_segment_rows,
            )
            for column in (
                "fold_id",
                "calendar_year",
                "market_regime",
                "liquidity_bucket",
                config.industry_column,
            )
        ],
        ignore_index=True,
    )
    calibration = calibration_table(
        enriched, probability_column, config.calibration_bins
    )
    strength_ranking = strength_ranking_comparison(
        enriched, probability_column, config.top_fractions
    )
    primary_strength_ranking = strength_ranking.loc[
        strength_ranking["top_fraction"].eq(primary_fraction)
    ]
    if len(primary_strength_ranking) == 2:
        precision_by_score = primary_strength_ranking.set_index("score")[
            "event_weighted_precision"
        ]
        strength_ranking_summary = {
            "top_fraction": primary_fraction,
            "entry_probability_precision": float(
                precision_by_score["entry_probability"]
            ),
            "entry_x_strength_precision": float(
                precision_by_score["entry_x_strength"]
            ),
            "precision_lift": float(
                precision_by_score["entry_x_strength"]
                / max(
                    precision_by_score["entry_probability"],
                    np.finfo(float).eps,
                )
            ),
        }
    else:
        strength_ranking_summary = {}
    tables = {
        "daily_ranking": daily_ranking,
        "daily_top_k": daily_top_k,
        "calibration": calibration,
        "segments": segments,
        "strength_bins": strength_bins,
        "strength_ranking": strength_ranking,
    }
    calibration_metrics = {
        **calibration_diagnostics(calibration),
        **calibration_slope_intercept(enriched, probability_column),
    }
    null_brier = overall["positive_rate"] * (1.0 - overall["positive_rate"])
    calibration_metrics["null_brier_score"] = null_brier
    calibration_metrics["brier_skill_score"] = 1.0 - overall["brier_score"] / null_brier
    report = {
        "classification": overall,
        "strength_positive_rows_only": strength,
        "strength_ranking": strength_ranking_summary,
        "calibration": calibration_metrics,
        "cluster_bootstrap_by_date": cluster_bootstrap(
            enriched,
            probability_column,
            primary_fraction,
            config.bootstrap_samples,
            config.confidence_level,
            config.random_seed,
        ),
        "daily_top_k_bootstrap_by_date": cluster_bootstrap_daily_top_k(
            enriched,
            probability_column,
            k=10,
            samples=config.bootstrap_samples,
            confidence_level=config.confidence_level,
            random_seed=config.random_seed,
        ),
    }
    return report, tables


def evaluate_acceptance_gates(
    report: dict[str, Any],
    segments: pd.DataFrame,
    training_oof_metrics: dict[str, Any],
    artifact_manifest: dict[str, Any],
    config: EvaluationConfig,
) -> dict[str, Any]:
    policy = config.acceptance_gates
    overall = report["classification"]
    fold_rows = segments.loc[segments["segment_type"].eq("fold_id")]
    temporal = training_oof_metrics.get("temporal_calibration_audit", {}).get(
        "metrics", {}
    )
    ap_lift = overall["average_precision"] / max(
        overall["positive_rate"], np.finfo(float).eps
    )
    fold_ap_lift = fold_rows["entry_average_precision"] / fold_rows[
        "entry_positive_rate"
    ].clip(lower=np.finfo(float).eps)
    checks = [
        (
            "oof_average_precision_lift",
            ap_lift,
            float(policy["minimum_oof_average_precision_lift"]),
            ">=",
        ),
        (
            "minimum_fold_average_precision_lift",
            float(fold_ap_lift.min()),
            float(policy["minimum_fold_average_precision_lift"]),
            ">=",
        ),
        (
            "minimum_fold_roc_auc",
            float(fold_rows["entry_roc_auc"].min()),
            float(policy["minimum_fold_roc_auc"]),
            ">=",
        ),
        (
            "weighted_precision_at_5pct",
            float(overall["weighted_precision_at_fraction"]),
            float(policy["minimum_weighted_precision_at_5pct"]),
            ">=",
        ),
        (
            "temporal_threshold_f1",
            float(temporal.get("f1", float("nan"))),
            float(policy["minimum_temporal_threshold_f1"]),
            ">=",
        ),
        (
            "strength_spearman",
            float(report["strength_positive_rows_only"]["spearman"]),
            float(policy["minimum_strength_spearman"]),
            ">=",
        ),
        (
            "minimum_fold_strength_spearman",
            float(fold_rows["strength_spearman"].min()),
            float(policy["minimum_fold_strength_spearman"]),
            ">=",
        ),
        (
            "strength_terminal_return_spearman",
            float(
                report["strength_positive_rows_only"].get(
                    "spearman_terminal_return", float("nan")
                )
            ),
            float(policy["minimum_strength_terminal_return_spearman"]),
            ">=",
        ),
        (
            "strength_ranking_precision_lift",
            float(report.get("strength_ranking", {}).get("precision_lift", float("nan"))),
            float(policy["minimum_strength_ranking_precision_lift"]),
            ">=",
        ),
        (
            "brier_skill_score",
            float(report["calibration"]["brier_skill_score"]),
            float(policy["minimum_brier_skill_score"]),
            ">=",
        ),
        (
            "expected_calibration_error",
            float(report["calibration"]["expected_calibration_error"]),
            float(policy["maximum_expected_calibration_error"]),
            "<=",
        ),
        (
            "minimum_calibration_slope",
            float(report["calibration"]["calibration_slope"]),
            float(policy["minimum_calibration_slope"]),
            ">=",
        ),
        (
            "maximum_calibration_slope",
            float(report["calibration"]["calibration_slope"]),
            float(policy["maximum_calibration_slope"]),
            "<=",
        ),
    ]
    backtest = report.get("backtest", {})
    checks.extend(
        [
            (
                "backtest_sharpe_ratio",
                float(backtest.get("sharpe_ratio", float("nan"))),
                float(policy["minimum_backtest_sharpe_ratio"]),
                ">=",
            ),
            (
                "backtest_excess_cumulative_return",
                float(backtest.get("excess_cumulative_return", float("nan"))),
                float(policy["minimum_backtest_excess_cumulative_return"]),
                ">=",
            ),
            (
                "backtest_trades",
                float(backtest.get("trades", float("nan"))),
                float(policy["minimum_backtest_trades"]),
                ">=",
            ),
            (
                "backtest_maximum_drawdown",
                float(backtest.get("maximum_drawdown", float("nan"))),
                float(policy["maximum_backtest_drawdown"]),
                ">=",
            ),
        ]
    )
    results = [
        {
            "gate": name,
            "actual": actual,
            "required": required,
            "operator": operator,
            "passed": bool(
                np.isfinite(actual)
                and (
                    actual >= required
                    if operator == ">="
                    else actual <= required
                )
            ),
        }
        for name, actual, required, operator in checks
    ]
    pre_final_gates_passed = all(result["passed"] for result in results)
    if policy.get("final_test_required_for_deployment", True):
        final_test_evaluated = bool(artifact_manifest.get("final_test_evaluated"))
        results.append(
            {
                "gate": "final_test_evaluated",
                "actual": final_test_evaluated,
                "required": True,
                "operator": "==",
                "passed": final_test_evaluated,
            }
        )
    all_passed = all(result["passed"] for result in results)
    return {
        "all_gates_required": bool(policy.get("all_gates_required", True)),
        "pre_final_gates_passed": pre_final_gates_passed,
        "all_passed": all_passed,
        "deployment_eligible": all_passed and bool(artifact_manifest.get("deployment_eligible")),
        "checks": results,
    }
