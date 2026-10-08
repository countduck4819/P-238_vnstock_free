"""Second-stage, risk-aware ranking for Wave V6 probabilities.

The functions only reorder already-calibrated probabilities; they never alter
model fitting, labels, or calibration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PortfolioRankingConfig:
    probability_weight: float = 0.65
    quality_weight: float = 0.35
    max_per_industry: int = 6
    low_liquidity_cutoff: float = 20.0
    low_liquidity_penalty: float = 15.0
    max_pump_penalty: float = 15.0


def _number(frame: pd.DataFrame, name: str, default: float = 0.0) -> pd.Series:
    if name not in frame:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[name], errors="coerce").fillna(default)


def _percentile_score(values: pd.Series) -> pd.Series:
    values = pd.to_numeric(values, errors="coerce")
    if values.notna().sum() < 2:
        return pd.Series(50.0, index=values.index)
    return values.rank(pct=True, method="average").fillna(0.5).mul(100.0)


def add_portfolio_quality_scores(
    frame: pd.DataFrame, config: PortfolioRankingConfig | None = None
) -> pd.DataFrame:
    config = config or PortfolioRankingConfig()
    out = frame.copy()
    probability = _number(out, "p_ensemble", np.nan)
    if probability.isna().all():
        probability = _number(out, "p_ensemble_pct") / 100.0
    out["wave_probability"] = probability.clip(0, 1).fillna(0.0).mul(100.0)

    base = (0.35 * _number(out, "base_stability_120", 0.5).clip(0, 1) +
            0.25 * (1.0 - _number(out, "volatility_contraction_20_120", 0.0).abs().clip(0, 1)) +
            0.20 * (1.0 - _number(out, "range_contraction_20_120", 1.0).clip(0, 1)) +
            0.20 * _number(out, "volume_persistence_20", 0.5).clip(0, 1))
    out["accumulation_score"] = (base * 100.0).clip(0, 100)
    trend = (0.40 * _number(out, "trend_r2_60", 0.0).clip(0, 1) +
             0.35 * _number(out, "rs_rank_market_60", 0.5).clip(0, 1) +
             0.25 * _number(out, "sector_rank_60", 0.5).clip(0, 1))
    out["trend_quality_score"] = (trend * 100.0).clip(0, 100)
    liquidity = _number(out, "liquidity_percentile", np.nan)
    if liquidity.isna().all():
        liquidity = _percentile_score(_number(out, "avg_value_traded_20", 0.0)) / 100.0
    out["liquidity_score"] = (liquidity.clip(0, 1).fillna(0.0) * 100.0)

    market_cap = _number(out, "market_cap", np.nan)
    has_market_cap = market_cap.notna() & market_cap.gt(0)
    out["size_basis"] = np.where(has_market_cap, "MARKET_CAP", "LIQUIDITY_PROXY")
    out["size_score"] = np.where(has_market_cap, _percentile_score(market_cap), out["liquidity_score"])
    out["market_cap_bucket"] = pd.cut(
        market_cap, [-np.inf, 0, 1e12, 1e13, np.inf], labels=["UNAVAILABLE", "SMALL", "MID", "LARGE"]
    ).astype("string").fillna("UNAVAILABLE")
    out["portfolio_bucket"] = pd.cut(
        out["size_score"], [-np.inf, 33.33, 66.67, np.inf], labels=["SMALL", "MID", "LARGE"]
    ).astype("string").fillna("SMALL")

    extension = _number(out, "atr_extension_20", 0.0).abs().clip(0, 8) / 8.0
    abnormal_volume = _number(out, "abnormal_volume_ratio_60", 0.0).clip(0, 1)
    high_distance = _number(out, "distance_from_high_252", 0.0).clip(-1, 0).abs()
    out["pump_risk_score"] = (100.0 * (0.55 * extension + 0.30 * abnormal_volume + 0.15 * high_distance)).clip(0, 100)
    out["pump_risk_penalty"] = (config.max_pump_penalty * out["pump_risk_score"] / 100.0).clip(0, config.max_pump_penalty)
    out["liquidity_penalty"] = np.where(out["liquidity_score"] < config.low_liquidity_cutoff, config.low_liquidity_penalty, 0.0)
    out["base_duration_sessions_estimate"] = (_number(out, "base_stability_120", 0.0).clip(0, 1) * 120).round()
    out["base_duration_score"] = out["accumulation_score"]
    out["volatility_contraction_score"] = (100.0 * (1.0 - _number(out, "volatility_contraction_20_120", 0.0).abs().clip(0, 1)))
    out["tight_range_score"] = (100.0 * (1.0 - _number(out, "range_contraction_20_120", 1.0).clip(0, 1)))
    out["volume_accumulation_score"] = (100.0 * _number(out, "volume_persistence_20", 0.5).clip(0, 1))
    out["early_strength_score"] = (100.0 * _number(out, "rs_rank_market_60", 0.5).clip(0, 1))
    out["stability_score"] = out["accumulation_score"]
    out["momentum_quality_score"] = out["trend_quality_score"]
    out["quality_score"] = (0.40 * out["accumulation_score"] + 0.35 * out["trend_quality_score"] + 0.25 * out["liquidity_score"])
    out["final_score_pre_penalty"] = config.probability_weight * out["wave_probability"] + config.quality_weight * out["quality_score"]
    out["final_score"] = out["final_score_pre_penalty"] - out["pump_risk_penalty"] - out["liquidity_penalty"]
    return out


def select_diversified_top_k(frame: pd.DataFrame, k: int, config: PortfolioRankingConfig | None = None) -> pd.DataFrame:
    config = config or PortfolioRankingConfig()
    scored = add_portfolio_quality_scores(frame, config).sort_values(
        ["final_score", "wave_probability"], ascending=False, kind="stable"
    )
    selected: list[int] = []
    counts: dict[str, int] = {}
    industries = scored.get("industry", pd.Series("UNKNOWN", index=scored.index)).fillna("UNKNOWN").astype(str)
    for index, industry in industries.items():
        if counts.get(industry, 0) >= config.max_per_industry:
            continue
        selected.append(index)
        counts[industry] = counts.get(industry, 0) + 1
        if len(selected) == k:
            break
    if len(selected) < k:
        selected.extend(index for index in scored.index if index not in selected)
    result = scored.loc[selected[:k]].copy().reset_index(drop=True)
    result.insert(0, "portfolio_rank", np.arange(1, len(result) + 1))
    return result


def ranking_profile(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": int(len(frame)),
        "mean_wave_probability": float(_number(frame, "wave_probability", _number(frame, "p_ensemble", 0.0) * 100.0).mean()),
        "mean_final_score": float(_number(frame, "final_score", 0.0).mean()),
        "industry_count": int(frame.get("industry", pd.Series(dtype=str)).nunique()),
    }


def compare_holdout_rankings(frame: pd.DataFrame, k: int, config: PortfolioRankingConfig | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    config = config or PortfolioRankingConfig()
    scored = add_portfolio_quality_scores(frame, config)
    date_column = "time" if "time" in scored else "date"
    details: list[pd.DataFrame] = []
    for _, group in scored.groupby(date_column, sort=True):
        before = group.sort_values(["p_ensemble", "model_agreement"], ascending=False).head(k).copy()
        before["ranking_method"] = "wave_probability_only"
        after = select_diversified_top_k(group, k, config)
        after["ranking_method"] = "risk_aware_diversified"
        details.extend((before, after))
    detail = pd.concat(details, ignore_index=True) if details else scored.iloc[0:0].copy()
    label = "wave_entry" if "wave_entry" in detail else "label"
    summary: dict[str, Any] = {"top_k": int(k), "methods": {}}
    for method, group in detail.groupby("ranking_method"):
        positives = _number(group, label, 0.0)
        summary["methods"][str(method)] = {
            "rows": int(len(group)),
            "positive_rate": float(positives.mean()) if len(group) else None,
            "industry_count": int(group.get("industry", pd.Series(dtype=str)).nunique()),
        }
    return detail, summary
