"""Create the reproducible Phase-1 H120 data-lineage and selection-bias audit."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed/wave_ignition_v6_snapshot"
FEATURE_RUN = ROOT / "data/features/wave_ignition_snapshot/wave_ignition_v2/runs/20260823T050008Z"
DATASET_RUN = ROOT / "data/training/wave_ignition_snapshot/wave_dataset_continuation_h120/runs/20260823T050830Z"
OUTPUT = ROOT / "reports/h120_improvement/data_audit"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def file_lineage(path: Path) -> dict[str, str | int]:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(path.relative_to(ROOT).as_posix()),
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
        "modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
    }


def stock_spans() -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for path in sorted((PROCESSED / "stock_ohlcv").glob("*.csv")):
        dates = pd.read_csv(path, usecols=["date"], parse_dates=["date"])["date"]
        records.append(
            {
                "symbol": path.stem,
                "first_observed_date": dates.min(),
                "last_observed_date": dates.max(),
                "observed_sessions": int(len(dates)),
            }
        )
    return pd.DataFrame(records)


def enrich_missing_sessions(missing: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    spans = stock_spans()
    liquidity = features.loc[:, ["symbol", "date", "log_turnover"]].copy()
    liquidity.sort_values(["symbol", "date"], inplace=True, kind="stable")
    liquidity["prior_log_turnover"] = liquidity.groupby("symbol", observed=True)[
        "log_turnover"
    ].transform(lambda values: values.ffill().shift())
    enriched = missing.merge(spans, on="symbol", how="left", validate="many_to_one")
    enriched = enriched.merge(
        liquidity.loc[:, ["symbol", "date", "prior_log_turnover"]],
        on=["symbol", "date"],
        how="left",
        validate="many_to_one",
    )
    liquidity_percentile = enriched["prior_log_turnover"].rank(pct=True, method="average")
    enriched["liquidity_bucket_prior"] = np.select(
        [liquidity_percentile.le(1 / 3), liquidity_percentile.le(2 / 3)],
        ["low", "medium"],
        default="high",
    )
    enriched.loc[
        enriched["prior_log_turnover"].isna(), "liquidity_bucket_prior"
    ] = "unknown_no_prior_turnover"
    enriched["listing_status_proxy"] = "within_observed_span_unresolved"
    enriched.loc[enriched["date"].lt(enriched["first_observed_date"]), "listing_status_proxy"] = (
        "pre_first_observation"
    )
    enriched.loc[enriched["date"].gt(enriched["last_observed_date"]), "listing_status_proxy"] = (
        "post_last_observation"
    )
    return enriched


def read_feature_rows() -> pd.DataFrame:
    columns = [
        "symbol", "date", "icb_level_2_code", "feature_ready", "coverage_60", "coverage_120",
        "log_turnover", "market_regime_score", "corporate_action_jump", "corporate_action_recent",
    ]
    frames = [pd.read_parquet(path, columns=columns) for path in sorted((FEATURE_RUN / "stock_features").glob("year=*/features.parquet"))]
    frame = pd.concat(frames, ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["year"] = frame["date"].dt.year
    return frame


def read_dataset_rows() -> pd.DataFrame:
    columns = ["symbol", "date", "y_entry", "label_end_date", "sample_weight"]
    frames = [pd.read_parquet(path, columns=columns) for path in sorted((DATASET_RUN / "dataset").glob("year=*/dataset.parquet"))]
    frame = pd.concat(frames, ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["label_end_date"] = pd.to_datetime(frame["label_end_date"])
    frame["year"] = frame["date"].dt.year
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    expected = [
        output / "corporate_action_audit.parquet",
        output / "missing_session_breakdown.csv",
        output / "feature_ready_selection_bias.csv",
        output / "universe_funnel_by_year.csv",
        output / "industry_lineage_report.json",
        output / "source_lineage.json",
        output / "missing_session_enriched.csv",
        output / "data_audit_summary.md",
    ]
    if any(path.exists() for path in expected) and not args.overwrite:
        raise FileExistsError("Refusing to overwrite an existing Phase-1 audit; use --overwrite.")
    output.mkdir(parents=True, exist_ok=True)

    quality = json.loads((PROCESSED / "audit/quality_summary.json").read_text(encoding="utf-8"))
    feature_quality = json.loads((FEATURE_RUN / "audit/feature_quality_report.json").read_text(encoding="utf-8"))
    dataset_quality = json.loads((DATASET_RUN / "audit/dataset_quality_report.json").read_text(encoding="utf-8"))
    features = read_feature_rows()
    dataset = read_dataset_rows()
    unavailable = pd.read_parquet(FEATURE_RUN / "audit/unavailable_rows.parquet")
    unavailable["date"] = pd.to_datetime(unavailable["date"])
    unavailable["year"] = unavailable["date"].dt.year
    missing = pd.read_csv(PROCESSED / "audit/missing_sessions.csv", parse_dates=["date"])
    missing["year"] = missing["date"].dt.year
    industry_map = pd.read_csv(PROCESSED / "industry_map_icb.csv")

    corporate = features.loc[
        features["corporate_action_jump"].fillna(False).astype(bool)
        | features["corporate_action_recent"].fillna(False).astype(bool)
    ].copy()
    corporate["adjustment_policy"] = quality["price_adjustment_policy"]
    corporate["verification_status"] = "requires_external_point_in_time_corporate_action_source"
    corporate.to_parquet(output / "corporate_action_audit.parquet", index=False)

    enriched_missing = enrich_missing_sessions(missing, features)
    missing_breakdown = (
        enriched_missing.groupby(
            ["year", "symbol", "reason", "liquidity_bucket_prior", "listing_status_proxy"],
            observed=True,
        )
        .size().rename("missing_sessions").reset_index()
        .sort_values(["missing_sessions", "symbol"], ascending=[False, True])
    )
    missing_breakdown.to_csv(output / "missing_session_breakdown.csv", index=False)
    enriched_missing.to_csv(output / "missing_session_enriched.csv", index=False)

    unavailable_flags = [
        "low_quality", "market_unavailable", "sector_unavailable", "stock_score_unavailable", "leader_unavailable",
    ]
    selection = unavailable.groupby("year", observed=True).agg(
        unavailable_rows=("symbol", "size"), unavailable_symbols=("symbol", "nunique"),
        median_coverage_60=("coverage_60", "median"), median_coverage_120=("coverage_120", "median"),
    ).reset_index()
    for flag in unavailable_flags:
        selection[flag] = unavailable.groupby("year", observed=True)[flag].sum().to_numpy(dtype=int)
    selection.to_csv(output / "feature_ready_selection_bias.csv", index=False)

    availability = features.groupby("year", observed=True).agg(
        feature_rows=("symbol", "size"), feature_symbols=("symbol", "nunique"),
        ready_rows=("feature_ready", "sum"),
    ).reset_index()
    availability["ready_rate"] = availability["ready_rows"] / availability["feature_rows"]
    labeled = dataset.groupby("year", observed=True).agg(
        labeled_rows=("symbol", "size"), labeled_symbols=("symbol", "nunique"),
        positive_rate=("y_entry", "mean"),
    ).reset_index()
    funnel = availability.merge(labeled, on="year", how="left").fillna({"labeled_rows": 0, "labeled_symbols": 0, "positive_rate": 0.0})
    funnel["ready_to_labeled_rate"] = funnel["labeled_rows"] / funnel["ready_rows"].where(funnel["ready_rows"] > 0)
    funnel.to_csv(output / "universe_funnel_by_year.csv", index=False)

    industry_report = {
        "mapping_path": str((PROCESSED / "industry_map_icb.csv").relative_to(ROOT).as_posix()),
        "symbols": int(industry_map["symbol"].nunique()),
        "fields": industry_map.columns.tolist(),
        "effective_date_column_present": any("date" in column.lower() for column in industry_map.columns),
        "point_in_time_available": False,
        "production_policy": "sector features are lineage_risk_open; exclude them from the first stock-only ranker.",
    }
    write_json(output / "industry_lineage_report.json", industry_report)
    source_lineage = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "price_adjustment_policy": quality["price_adjustment_policy"],
        "missing_session_policy": quality["missing_session_policy"],
        "sources": {
            "quality_summary": file_lineage(PROCESSED / "audit/quality_summary.json"),
            "missing_sessions": file_lineage(PROCESSED / "audit/missing_sessions.csv"),
            "industry_map": file_lineage(PROCESSED / "industry_map_icb.csv"),
            "feature_manifest": file_lineage(FEATURE_RUN / "feature_manifest.json"),
            "dataset_manifest": file_lineage(DATASET_RUN / "dataset_manifest.json"),
        },
        "unavailable_external_sources": {
            "corporate_actions": "No split/dividend/rights point-in-time source is present.",
            "listing_status": "No historical listing/suspension/delisting source is present.",
            "industry_history": "The current ICB map has no effective-date history.",
        },
    }
    write_json(output / "source_lineage.json", source_lineage)

    summary = f"""# H120 Phase-1 data lineage audit

## Mechanical quality

- Processed stock rows: {quality['output_stock_rows']:,}; excluded rows: {quality['excluded_row_audit_records']:,}.
- Invalid OHLCV reasons after cleaning: {sum(value for key, value in quality['reason_counts'].items() if key != 'date_not_in_vnindex_calendar'):,}.
- Missing sessions are audit-only and not imputed: {quality['missing_session_records']:,}.
- Missing-session enrichment uses prior turnover and observation-span proxies only; it cannot label suspension/delisting without an external listing-status source.

## Selection funnel

- Feature-ready rows reported by feature audit: {feature_quality['ready_rows']:,} / {feature_quality['rows']:,} ({feature_quality['ready_rows'] / feature_quality['rows']:.2%}).
- Labeled H120 rows: {dataset_quality['rows']:,}; symbols: {dataset_quality['symbols']:,}.
- Per-year funnel and unavailable reasons are in `universe_funnel_by_year.csv` and `feature_ready_selection_bias.csv`.

## Corporate actions and industry lineage

- Price policy is `{quality['price_adjustment_policy']}`. Flagged jump/cooldown rows are exported to `corporate_action_audit.parquet`.
- Internal source policy, timestamps and SHA-256 checksums are in `source_lineage.json`.
- No external, point-in-time split/dividend/rights event source is present in this snapshot. Corporate-action verification remains **lineage_risk_open**.
- Industry map is a static current ICB snapshot with no effective-date column. Sector features remain **lineage_risk_open** and are excluded from the first stock-only challenger.

## Decision

Mechanical data quality is sufficient for research. Production lineage is not fully closed until an external point-in-time corporate-action and industry-history source is recorded.
"""
    (output / "data_audit_summary.md").write_text(summary, encoding="utf-8")
    print(json.dumps({"status": "phase_1_audit_complete_with_lineage_risks", "output": str(output), "corporate_rows": len(corporate)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
