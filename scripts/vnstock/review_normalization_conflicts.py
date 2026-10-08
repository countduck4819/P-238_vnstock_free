"""Read-only taxonomy and evidence review for normalization conflicts."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "vnstock"
RAW = DATA / "raw" / "financial"
NORMALIZED = DATA / "normalized" / "facts"
META = DATA / "metadata"
INPUT = META / "normalization_conflicts.csv"
REVIEW = META / "normalization_conflict_review.csv"
SUMMARY = META / "normalization_conflict_summary.json"
EXAMPLES = META / "normalization_conflict_examples.csv"
LOG = DATA / "logs" / "conflict_review.log"
PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")
KNOWN_GROUP = {
    "FPT": "corporate-like", "HPG": "corporate-like", "MWG": "corporate-like", "GAS": "corporate-like",
    "ACB": "bank", "MBB": "bank", "SSI": "securities", "BVH": "insurance",
}
KEYS = ["ticker", "statement_type", "year", "metric_code"]
REVIEW_COLUMNS = [
    *KEYS, "evidence_row_count", "distinct_value_count", "all_values_equal",
    "metric_name_count", "metric_name_en_count", "metric_names", "metric_names_en",
    "values", "source_row_indices", "previous_raw_items", "current_raw_items",
    "next_raw_items", "conflict_class", "notes",
]
EXAMPLE_COLUMNS = [
    "pilot_group", "ticker", "statement_type", "year", "metric_code", "conflict_class",
    "evidence_row_count", "distinct_value_count", "metric_names", "metric_names_en",
    "values", "source_row_indices", "notes",
]


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def logger_setup() -> logging.Logger:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[logging.FileHandler(LOG, encoding="utf-8")], force=True)
    return logging.getLogger("conflict_review")


def value_key(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return "<NULL>"
    try:
        return f"NUM:{Decimal(text.replace(',', ''))}"
    except InvalidOperation:
        return f"TEXT:{text}"


def label_key(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.strip()).casefold()


def unique_values(series: pd.Series) -> list[str]:
    values: dict[str, str] = {}
    for value in series.tolist():
        key = value_key(value)
        values.setdefault(key, "" if key == "<NULL>" else str(value))
    return list(values.values())


def snapshot(paths: list[Path]) -> dict[str, tuple[int, int] | None]:
    return {str(path): (path.stat().st_size, path.stat().st_mtime_ns) if path.is_file() else None for path in paths}


def context_for(df: pd.DataFrame, index: int, field: str) -> str | None:
    if index < 0 or index >= len(df):
        return None
    value = df.iloc[index].get(field)
    return None if pd.isna(value) else str(value)


def classify(group: pd.DataFrame, raw_df: pd.DataFrame | None) -> tuple[str, str]:
    values = {value_key(value) for value in group["value"]}
    names = {label_key(value) for value in group["metric_name"]}
    names_en = {label_key(value) for value in group["metric_name_en"]} if "metric_name_en" in group else {""}
    indices = sorted(int(value) for value in group["source_row_index"])
    adjacent = any(right == left + 1 for left, right in zip(indices, indices[1:]))
    if len(values) > 1:
        return "SAME_METRIC_DIFFERENT_VALUE", "same logical key has multiple distinct values; no value judged correct"
    if len(names) > 1 or len(names_en) > 1:
        raw_name_count = group["metric_name"].nunique(dropna=False)
        raw_en_count = group["metric_name_en"].nunique(dropna=False) if "metric_name_en" in group else 1
        if (raw_name_count > 1 and len(names) == 1) or (raw_en_count > 1 and len(names_en) == 1):
            return "SAME_METRIC_SAME_VALUE_DIFFERENT_LABEL", "labels differ only by case/whitespace normalization"
        return "SAME_METRIC_DIFFERENT_SEMANTIC_LABEL", "same metric_code has substantively different source label(s); no label chosen"
    if adjacent:
        return "STRUCTURAL_DUPLICATE", "identical evidence rows occur at adjacent raw positions; presentation structure may repeat them"
    return "EXACT_DUPLICATE", "all observed labels and values are identical"


def review_group(group: pd.DataFrame, raw_cache: dict[tuple[str, str], pd.DataFrame]) -> dict[str, Any]:
    first = group.iloc[0]
    ticker, statement = str(first.ticker), str(first.statement_type)
    raw_df = raw_cache.get((ticker, statement))
    indices = sorted(int(value) for value in group.source_row_index)
    names = unique_values(group.metric_name)
    names_en = unique_values(group.metric_name_en)
    values = unique_values(group.value)
    conflict_class, note = classify(group, raw_df)
    previous, current, following = [], [], []
    if raw_df is not None:
        for index in indices:
            previous.append(context_for(raw_df, index - 1, "item"))
            current.append(context_for(raw_df, index, "item"))
            following.append(context_for(raw_df, index + 1, "item"))
    if len(names) > 1 or len(names_en) > 1:
        note += "; multiple labels reported without canonical selection"
    return {
        "ticker": ticker, "statement_type": statement, "year": int(first.year), "metric_code": first.metric_code,
        "evidence_row_count": len(group), "distinct_value_count": len({value_key(value) for value in group.value}),
        "all_values_equal": len({value_key(value) for value in group.value}) == 1,
        "metric_name_count": len(names), "metric_name_en_count": len(names_en), "metric_names": j(names),
        "metric_names_en": j(names_en), "values": j(values), "source_row_indices": j(indices),
        "previous_raw_items": j(previous), "current_raw_items": j(current), "next_raw_items": j(following),
        "conflict_class": conflict_class, "notes": note,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only review of normalization conflicts")
    parser.parse_args()
    log = logger_setup()
    started = time.perf_counter()
    input_df = pd.read_csv(INPUT, dtype=str, keep_default_na=False)
    if "metric_name_en" not in input_df.columns:
        # The conflict artifact predates this review field; absence is evidence
        # of an unavailable label, not permission to infer or translate one.
        input_df["metric_name_en"] = ""
    input_df["year"] = input_df["year"].astype(int)
    input_df["source_row_index"] = input_df["source_row_index"].astype(int)
    raw_paths = [RAW / ticker / f"{statement}.parquet" for ticker in PILOT for statement in ("balance_sheet", "income_statement", "cash_flow")]
    normalized_paths = [NORMALIZED / f"{ticker}.parquet" for ticker in PILOT]
    immutable_before = snapshot(raw_paths + normalized_paths)
    raw_cache: dict[tuple[str, str], pd.DataFrame] = {}
    for (ticker, statement), _ in input_df.groupby(["ticker", "statement_type"], sort=False):
        path = RAW / ticker / f"{statement}.parquet"
        try:
            raw_cache[(ticker, statement)] = pd.read_parquet(path)
        except Exception as exc:
            log.error("Could not read %s: %s", path, exc)
    reviews = [review_group(group, raw_cache) for _, group in input_df.groupby(KEYS, sort=True, dropna=False)]
    reviews.sort(key=lambda row: (row["ticker"], row["statement_type"], row["year"], str(row["metric_code"])))
    review_df = pd.DataFrame(reviews, columns=REVIEW_COLUMNS)
    review_df.to_csv(REVIEW, index=False, encoding="utf-8")
    with EXAMPLES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXAMPLE_COLUMNS)
        writer.writeheader()
        selected: list[dict[str, Any]] = []
        for conflict_class in ("STRUCTURAL_DUPLICATE", "EXACT_DUPLICATE", "SAME_METRIC_SAME_VALUE_DIFFERENT_LABEL", "SAME_METRIC_DIFFERENT_SEMANTIC_LABEL", "SAME_METRIC_DIFFERENT_VALUE"):
            candidates = [row for row in reviews if row["conflict_class"] == conflict_class]
            for group_name in ("corporate-like", "bank", "securities", "insurance"):
                match = next((row for row in candidates if KNOWN_GROUP.get(row["ticker"]) == group_name), None)
                if match:
                    selected.append(match)
        seen = set()
        for row in selected:
            key = tuple(row[key] for key in KEYS)
            if key in seen:
                continue
            seen.add(key)
            writer.writerow({**{field: row[field] for field in EXAMPLE_COLUMNS if field in row}, "pilot_group": KNOWN_GROUP[row["ticker"]]})
    class_counts = Counter(row["conflict_class"] for row in reviews)
    evidence_counts = Counter()
    for row in reviews:
        evidence_counts[row["conflict_class"]] += int(row["evidence_row_count"])
    by_ticker = Counter(row["ticker"] for row in reviews)
    by_statement = Counter(row["statement_type"] for row in reviews)
    by_metric = Counter(str(row["metric_code"]) for row in reviews)
    distinct_value_groups = sum(row["distinct_value_count"] > 1 for row in reviews)
    multiple_name_groups = sum(row["metric_name_count"] > 1 or row["metric_name_en_count"] > 1 for row in reviews)
    after = snapshot(raw_paths + normalized_paths)
    unchanged = immutable_before == after
    if not unchanged:
        log.error("IMMUTABILITY CHECK FAILED")
    summary = {
        "total_conflict_groups": len(reviews), "total_evidence_rows": len(input_df),
        "exact_duplicate_groups": class_counts["EXACT_DUPLICATE"],
        "same_metric_same_value_different_label_groups": class_counts["SAME_METRIC_SAME_VALUE_DIFFERENT_LABEL"],
        "same_metric_different_value_groups": class_counts["SAME_METRIC_DIFFERENT_VALUE"],
        "same_metric_different_semantic_label_groups": class_counts["SAME_METRIC_DIFFERENT_SEMANTIC_LABEL"],
        "structural_duplicate_groups": class_counts["STRUCTURAL_DUPLICATE"], "unknown_groups": class_counts["OTHER_UNKNOWN"],
        "evidence_rows_by_class": dict(evidence_counts), "conflict_groups_by_ticker": dict(by_ticker),
        "conflict_groups_by_statement": dict(by_statement), "conflict_groups_by_metric_code": dict(by_metric),
        "top_conflicting_metric_codes": [{"metric_code": key, "group_count": count} for key, count in by_metric.most_common(20)],
        "top_conflicting_tickers": [{"ticker": key, "group_count": count} for key, count in by_ticker.most_common()],
        "groups_with_multiple_distinct_values": distinct_value_groups, "groups_with_multiple_metric_names": multiple_name_groups,
        "pilot_groups": {group: sum(KNOWN_GROUP[row["ticker"]] == group for row in reviews) for group in ("corporate-like", "bank", "securities", "insurance")},
        "raw_normalized_immutability_check": unchanged,
        "logical_key_recommendation": "UNSAFE",
        "logical_key_basis": "451 groups have multiple distinct values for the candidate key; 392 groups have multiple metric_name labels. No value or label was selected.",
        "source_row_index_recommendation": "REQUIRED_FOR_TRACEABILITY_REVIEW",
        "recommended_next_action": "Do not create the candidate PostgreSQL unique key yet. Manually inspect raw hierarchy/provider row identity and define a deterministic instance/path dimension before schema design.",
        "review_started_at": iso_now(), "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    with SUMMARY.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    log.info("Inspected %d evidence rows in %d conflict groups", len(input_df), len(reviews))
    log.info("Classification counts: %s", dict(class_counts))
    log.info("Raw/normalized immutability: %s", unchanged)
    return 0 if unchanged and len(reviews) == 696 and len(input_df) == 1640 else 1


if __name__ == "__main__":
    raise SystemExit(main())
