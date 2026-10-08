"""Join causal base-head predictions into the cascade meta-model schema.

The H120 table is the anchor population.  Other heads may be incomplete; the
meta model receives an explicit missing indicator rather than a value derived
from final-test rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h120-oof", type=Path, required=True)
    parser.add_argument("--h20-oof", type=Path)
    parser.add_argument("--h60-oof", type=Path)
    parser.add_argument(
        "--v6-trend-oof",
        "--surge-oof",
        dest="v6_trend_oof",
        type=Path,
        help=(
            "OOF probability from the original V6 unbounded early-major-wave "
            "versus structural-breakdown model. --surge-oof is retained as a "
            "legacy alias."
        ),
    )
    parser.add_argument("--break-h60-oof", type=Path)
    parser.add_argument("--break-h120-oof", type=Path)
    parser.add_argument(
        "--break-h60-labels",
        type=Path,
        help="Canonical H60 breakdown labels. Labels are joined independently of OOF predictions.",
    )
    parser.add_argument(
        "--break-h120-labels",
        type=Path,
        help="Canonical H120 breakdown labels. Labels are joined independently of OOF predictions.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--mode", choices=("oof", "final"), default="oof")
    parser.add_argument(
        "--target-mode",
        choices=("continuation", "legacy_actionable"),
        default="continuation",
        help=(
            "Cascade target contract. 'continuation' uses y_cont_h120 and keeps "
            "breakdown labels for offline audit; 'legacy_actionable' retains the "
            "historical breakdown-conditioned target."
        ),
    )
    parser.add_argument(
        "--alignment-mode",
        choices=("exact", "asof"),
        default="asof",
        help=(
            "Prediction alignment policy. 'asof' carries the latest prediction "
            "from the same symbol at or before the anchor date."
        ),
    )
    parser.add_argument(
        "--max-lag-days",
        type=int,
        default=5,
        help="Maximum calendar age allowed for an as-of prediction.",
    )
    parser.add_argument(
        "--require-candidate-coverage",
        action="store_true",
        help="Fail when the H20 onset candidate head is below the declared minimums.",
    )
    parser.add_argument(
        "--minimum-candidate-day-coverage",
        type=float,
        default=0.95,
        help="Required fraction of anchor days with an aligned H20 onset prediction.",
    )
    parser.add_argument(
        "--minimum-candidate-row-coverage",
        type=float,
        default=0.80,
        help="Required fraction of anchor rows with an aligned H20 onset prediction.",
    )
    parser.add_argument(
        "--require-actionable-label-coverage",
        action="store_true",
        help="Fail when both canonical breakdown labels are not available for the required anchor fraction.",
    )
    parser.add_argument(
        "--minimum-actionable-label-coverage",
        type=float,
        default=0.95,
        help="Required fraction of anchor rows with complete H60/H120 labels.",
    )
    return parser.parse_args()


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def normalize_base(path: Path, name: str) -> pd.DataFrame:
    frame = read_table(path).copy()
    # Accept the canonical schema as well as the legacy V6 export schema.  The
    # latter has ticker/time and one raw probability per ensemble member.
    if "symbol" not in frame and "ticker" in frame:
        frame = frame.rename(columns={"ticker": "symbol"})
    if "date" not in frame and "time" in frame:
        frame = frame.rename(columns={"time": "date"})
    required = {"symbol", "date"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} prediction table is missing {missing}")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    if "fold_id" in frame.columns:
        frame["fold_id"] = frame["fold_id"].astype(str)
    probability = next(
        (
            column
            for column in (
                "p_entry_calibrated",
                "p_entry_calibrated_temporal",
                "p_calibrated",
                "probability",
                "p_v6_trend",
                "p_surge",
                "p_entry",
                f"p_{name}",
            )
            if column in frame
        ),
        None,
    )
    if probability is None and name == "v6_trend":
        # Legacy V6 writes raw xgb/lgb/cat columns.  Use the admitted V6
        # weights as a provisional raw surge score; the cascade still learns
        # the mapping from that score using prior-fold data only.
        member_columns = ("xgb", "lgb", "cat")
        if all(column in frame for column in member_columns):
            frame["_p_v6_trend_raw"] = (
                0.15 * pd.to_numeric(frame["xgb"], errors="coerce")
                + 0.45 * pd.to_numeric(frame["lgb"], errors="coerce")
                + 0.40 * pd.to_numeric(frame["cat"], errors="coerce")
            )
            probability = "_p_v6_trend_raw"
    if probability is None:
        raise ValueError(f"{name} has no calibrated probability column")
    # Fold IDs belong to the H120 anchor only.  Other heads use their own
    # calendars, so carrying their fold_id into a point-in-time merge would
    # create conflicting *_x/*_y columns.
    keep = ["symbol", "date", probability]
    result = frame.loc[:, keep].rename(columns={probability: f"p_{name}"})
    if result.duplicated(["symbol", "date"]).any():
        raise ValueError(f"{name} has duplicate prediction keys")
    return result


def normalize_strength(path: Path, name: str) -> pd.DataFrame:
    frame = read_table(path).copy()
    if "symbol" not in frame and "ticker" in frame:
        frame = frame.rename(columns={"ticker": "symbol"})
    if "date" not in frame and "time" in frame:
        frame = frame.rename(columns={"time": "date"})
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    strength = next(
        (column for column in ("p_strength", "p_strength_conditional", "strength") if column in frame),
        None,
    )
    if strength is None:
        return pd.DataFrame()
    keep = ["symbol", "date", strength]
    return frame.loc[:, keep].rename(columns={strength: f"strength_{name}"})


def normalize_breakdown_labels(path: Path, name: str) -> pd.DataFrame:
    frame = read_table(path).copy()
    if "symbol" not in frame and "ticker" in frame:
        frame = frame.rename(columns={"ticker": "symbol"})
    if "date" not in frame and "time" in frame:
        frame = frame.rename(columns={"time": "date"})
    label = next(
        (column for column in ("y_breakdown", "breakdown_label") if column in frame),
        None,
    )
    if label is None:
        raise ValueError(f"{name} label table has no y_breakdown column")
    required = {"symbol", "date", label}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} label table is missing {missing}")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    result = frame[["symbol", "date", label]].rename(
        columns={label: f"y_break_{name}"}
    )
    if result.duplicated(["symbol", "date"]).any():
        raise ValueError(f"{name} label table has duplicate symbol/date keys")
    return result


def join_keys(left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    # Base heads are trained with different fold calendars (V6 uses custom
    # windows, while continuation uses fold_2020...fold_2024).  Matching a
    # fold_id would silently drop valid rows, so the causal contract is the
    # shared point-in-time key.  Fold IDs remain on the H120 anchor for the
    # meta-model's temporal split.
    return ["symbol", "date"]


def _asof_align(
    base: pd.DataFrame,
    source: pd.DataFrame,
    *,
    value_column: str,
    name: str,
    max_lag_days: int,
) -> pd.DataFrame:
    """Align a prediction to the latest causal source row for each symbol.

    ``merge_asof`` is deliberately not used here: pandas requires a fragile
    global sort order when ``by`` is combined with a timestamp key.  The
    per-symbol ``searchsorted`` implementation makes the causal direction
    explicit and lets us retain an audit trail for the source date and lag.
    """
    if max_lag_days < 0:
        raise ValueError("max_lag_days must be non-negative")
    if source.duplicated(["symbol", "date"]).any():
        raise ValueError(f"{name} prediction table has duplicate symbol/date keys")

    result = base.copy()
    result[f"{value_column}_source_date"] = pd.NaT
    result[f"{value_column}_lag_days"] = np.nan
    result[value_column] = np.nan
    source = source.sort_values(["symbol", "date"], kind="stable")
    source_groups = {
        str(symbol): group.reset_index(drop=True)
        for symbol, group in source.groupby("symbol", sort=False)
    }
    for symbol, left_index in result.groupby("symbol", sort=False).groups.items():
        right = source_groups.get(str(symbol))
        if right is None or right.empty:
            continue
        left_dates = pd.to_datetime(result.loc[left_index, "date"]).to_numpy(dtype="datetime64[ns]")
        right_dates = pd.to_datetime(right["date"]).to_numpy(dtype="datetime64[ns]")
        positions = np.searchsorted(right_dates, left_dates, side="right") - 1
        candidate = positions >= 0
        if not candidate.any():
            continue
        candidate_left = np.flatnonzero(candidate)
        valid_positions = positions[candidate]
        source_dates = right_dates[valid_positions]
        lag_days = (left_dates[candidate] - source_dates) / np.timedelta64(1, "D")
        accepted = lag_days <= max_lag_days
        if not accepted.any():
            continue
        selected_index = result.loc[left_index].index.to_numpy()[candidate_left[accepted]]
        selected_source = right.iloc[valid_positions[accepted]]
        result.loc[selected_index, value_column] = selected_source[value_column].to_numpy()
        result.loc[selected_index, f"{value_column}_source_date"] = pd.to_datetime(
            selected_source["date"].to_numpy()
        ).to_numpy()
        result.loc[selected_index, f"{value_column}_lag_days"] = lag_days[accepted]
    return result


def align_prediction(
    base: pd.DataFrame,
    source: pd.DataFrame,
    *,
    value_column: str,
    name: str,
    mode: str,
    max_lag_days: int,
) -> pd.DataFrame:
    """Join one prediction head with an explicit exact/as-of policy."""
    if mode == "exact":
        if source.duplicated(["symbol", "date"]).any():
            raise ValueError(f"{name} prediction table has duplicate symbol/date keys")
        merged = base.merge(
            source[["symbol", "date", value_column]],
            on=["symbol", "date"],
            how="left",
            validate="one_to_one",
        )
        merged[f"{value_column}_source_date"] = merged["date"].where(
            merged[value_column].notna()
        )
        merged[f"{value_column}_lag_days"] = 0.0
        return merged
    if mode != "asof":
        raise ValueError(f"Unsupported alignment mode: {mode}")
    return _asof_align(
        base,
        source,
        value_column=value_column,
        name=name,
        max_lag_days=max_lag_days,
    )


def add_optional(
    base: pd.DataFrame,
    path: Path | None,
    name: str,
    *,
    alignment_mode: str,
    max_lag_days: int,
) -> pd.DataFrame:
    if path is None:
        base[f"p_{name}"] = np.nan
        base[f"p_{name}_source_date"] = pd.NaT
        base[f"p_{name}_lag_days"] = np.nan
        return base
    source = normalize_base(path, name)
    base = base.drop(columns=[f"p_{name}"], errors="ignore")
    base = base.drop(
        columns=[f"p_{name}_source_date", f"p_{name}_lag_days"], errors="ignore"
    )
    return align_prediction(
        base,
        source,
        value_column=f"p_{name}",
        name=name,
        mode=alignment_mode,
        max_lag_days=max_lag_days,
    )


def add_breakdown(
    base: pd.DataFrame,
    path: Path | None,
    name: str,
    *,
    label_path: Path | None,
    alignment_mode: str,
    max_lag_days: int,
) -> pd.DataFrame:
    if path is None:
        base[f"p_break_{name}"] = np.nan
    result = base
    if path is not None:
        source = read_table(path).copy()
        if "symbol" not in source and "ticker" in source:
            source = source.rename(columns={"ticker": "symbol"})
        if "date" not in source and "time" in source:
            source = source.rename(columns={"time": "date"})
        source["date"] = pd.to_datetime(source["date"], errors="raise").dt.normalize()
        probability = next(
            (column for column in ("p_entry_calibrated", "p_breakdown", "probability") if column in source),
            None,
        )
        if probability is None:
            raise ValueError(f"{name} breakdown table has no probability column")
        keep = ["symbol", "date", probability]
        probability_source = source.loc[:, keep].rename(columns={probability: f"p_break_{name}"})
        result = align_prediction(
            result,
            probability_source,
            value_column=f"p_break_{name}",
            name=f"break_{name}",
            mode=alignment_mode,
            max_lag_days=max_lag_days,
        )
    # Labels are targets for the anchor date, not predictions.  They must stay
    # exact even when their corresponding prediction is carried as-of.  A
    # canonical label path is preferred so prediction OOF coverage cannot
    # censor the target population.
    if label_path is not None:
        labels = normalize_breakdown_labels(label_path, name)
        result = result.merge(labels, on=["symbol", "date"], how="left", validate="one_to_one")
    elif path is not None:
        source = read_table(path).copy()
        if "symbol" not in source and "ticker" in source:
            source = source.rename(columns={"ticker": "symbol"})
        if "date" not in source and "time" in source:
            source = source.rename(columns={"time": "date"})
        source["date"] = pd.to_datetime(source["date"], errors="raise").dt.normalize()
        label = next((column for column in ("y_breakdown", "breakdown_label") if column in source), None)
        if label is not None:
            labels = source[["symbol", "date", label]].rename(columns={label: f"y_break_{name}"})
            result = result.merge(labels, on=["symbol", "date"], how="left", validate="one_to_one")
    return result


def main() -> None:
    args = parse_args()
    anchor = read_table(args.h120_oof).copy()
    anchor = anchor.rename(
        columns={
            "y_entry_h120": "y_entry",
            "sample_weight_h120": "sample_weight",
        }
    )
    required = {"symbol", "date", "y_entry", "sample_weight"}
    missing = sorted(required - set(anchor.columns))
    if missing:
        raise ValueError(f"H120 anchor is missing {missing}")
    anchor["date"] = pd.to_datetime(anchor["date"], errors="raise").dt.normalize()
    if args.mode == "oof" and "fold_id" not in anchor.columns:
        raise ValueError("H120 anchor must contain fold_id for causal meta training")
    if "fold_id" in anchor.columns:
        anchor["fold_id"] = anchor["fold_id"].astype(str)
    probability = normalize_base(args.h120_oof, "h120")
    keys = ["symbol", "date"]
    anchor_columns = [*keys, "y_entry", "sample_weight"]
    if "fold_id" in anchor.columns:
        anchor_columns.insert(0, "fold_id")
    frame = anchor.loc[:, anchor_columns].rename(
        columns={"y_entry": "y_cont_h120"}
    ).merge(probability, on=keys, how="inner", validate="one_to_one")
    frame["p_h120"] = frame.pop("p_h120")
    strength = normalize_strength(args.h120_oof, "h120")
    if not strength.empty:
        frame = frame.merge(strength, on=keys, how="left", validate="one_to_one")
    else:
        frame["strength_h120"] = np.nan
    for path, name in ((args.h20_oof, "h20"), (args.h60_oof, "h60")):
        if path is None:
            frame[f"p_{name}"] = np.nan
            frame[f"strength_{name}"] = np.nan
            continue
        frame = add_optional(
            frame,
            path,
            name,
            alignment_mode=args.alignment_mode,
            max_lag_days=args.max_lag_days,
        )
        extra = normalize_strength(path, name)
        if extra.empty:
            frame[f"strength_{name}"] = np.nan
        else:
            frame = frame.merge(extra, on=join_keys(frame, extra), how="left", validate="one_to_one")
    frame = add_optional(
        frame,
        args.v6_trend_oof,
        "v6_trend",
        alignment_mode=args.alignment_mode,
        max_lag_days=args.max_lag_days,
    )
    frame = add_breakdown(
        frame,
        args.break_h60_oof,
        "h60",
        label_path=args.break_h60_labels,
        alignment_mode=args.alignment_mode,
        max_lag_days=args.max_lag_days,
    )
    frame = add_breakdown(
        frame,
        args.break_h120_oof,
        "h120",
        label_path=args.break_h120_labels,
        alignment_mode=args.alignment_mode,
        max_lag_days=args.max_lag_days,
    )
    breakdown_columns = [
        column for column in ("y_break_h60", "y_break_h120")
        if column in frame and frame[column].notna().any()
    ]
    if not breakdown_columns:
        frame["y_actionable"] = frame["y_cont_h120"].astype("int8")
        frame["breakdown_labels_available"] = False
        legacy_target_description = "y_cont_h120 (breakdown labels unavailable)"
    else:
        breakdown = frame[breakdown_columns].apply(pd.to_numeric, errors="coerce")
        labels_complete = breakdown.notna().all(axis=1) & frame["y_cont_h120"].notna()
        frame["breakdown_labels_available"] = labels_complete
        no_breakdown = breakdown.eq(0).all(axis=1)
        # Known breakdown is a resolved negative. Only missing/censored labels
        # remain unknown and are excluded from cascade fitting.
        actionable = pd.Series(pd.NA, index=frame.index, dtype="Float64")
        actionable.loc[labels_complete] = (
            frame.loc[labels_complete, "y_cont_h120"].astype(int)
            .where(no_breakdown.loc[labels_complete], 0)
            .astype("int8")
        )
        frame["y_actionable"] = actionable
        legacy_target_description = (
            "y_cont_h120 AND " + " AND ".join(f"{column}=0" for column in breakdown_columns)
        )
    target_column = "y_cont_h120" if args.target_mode == "continuation" else "y_actionable"
    target_description = (
        "y_cont_h120 (breakdown labels offline audit only)"
        if args.target_mode == "continuation"
        else legacy_target_description
    )
    frame = frame.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    alignment = {}
    for name in ("v6_trend", "h20", "h60", "break_h60", "break_h120"):
        column = f"p_{name}" if name in ("v6_trend", "h20", "h60") else f"p_break_{name.removeprefix('break_')}"
        if column not in frame:
            continue
        available = frame[column].notna()
        days = frame.loc[available, "date"].nunique()
        alignment[name] = {
            "rows_aligned": int(available.sum()),
            "anchor_days_with_prediction": int(days),
            "anchor_days_total": int(frame["date"].nunique()),
            "row_coverage": float(available.mean()),
            "day_coverage": float(days / frame["date"].nunique()) if frame["date"].nunique() else 0.0,
            "alignment_mode": args.alignment_mode,
            "max_lag_days": args.max_lag_days,
        }
    if args.require_candidate_coverage and args.h20_oof is not None:
        candidate = alignment.get("h20", {})
        if (
            candidate.get("day_coverage", 0.0) < args.minimum_candidate_day_coverage
            or candidate.get("row_coverage", 0.0) < args.minimum_candidate_row_coverage
        ):
            raise RuntimeError(
                "H20 onset coverage is below the cascade contract: "
                f"day={candidate.get('day_coverage', 0.0):.3f} "
                f"(required {args.minimum_candidate_day_coverage:.3f}), "
                f"row={candidate.get('row_coverage', 0.0):.3f} "
                f"(required {args.minimum_candidate_row_coverage:.3f}). "
                "Align the onset/continuation calendars and populations before training cascade."
            )
    label_coverage = float(frame["breakdown_labels_available"].mean())
    if (
        args.target_mode == "legacy_actionable"
        and args.require_actionable_label_coverage
        and label_coverage < args.minimum_actionable_label_coverage
    ):
        raise RuntimeError(
            "Canonical actionable-label coverage is below the cascade contract: "
            f"coverage={label_coverage:.3f} "
            f"(required {args.minimum_actionable_label_coverage:.3f})."
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output, index=False)
    manifest = {
        "anchor": str(args.h120_oof.resolve()),
        "inputs": {
            name: str(path.resolve()) if path else None
            for name, path in {
                "h20": args.h20_oof,
                "h60": args.h60_oof,
                "v6_trend": args.v6_trend_oof,
                "break_h60": args.break_h60_oof,
                "break_h120": args.break_h120_oof,
                "break_h60_labels": args.break_h60_labels,
                "break_h120_labels": args.break_h120_labels,
            }.items()
        },
        "target": target_description,
        "target_mode": args.target_mode,
        "target_column": target_column,
        "rows": int(len(frame)),
        "folds": sorted(frame["fold_id"].unique().tolist()) if "fold_id" in frame else [],
        "alignment": alignment,
        "alignment_policy": {
            "mode": args.alignment_mode,
            "max_lag_days": args.max_lag_days,
            "causal_direction": "source_date <= anchor_date",
            "minimum_candidate_day_coverage": args.minimum_candidate_day_coverage,
            "minimum_candidate_row_coverage": args.minimum_candidate_row_coverage,
        },
        "target_quality": {
            "target_rows_resolved": int(frame[target_column].notna().sum()),
            "target_rows_positive": int((frame[target_column] == 1).sum()),
            "breakdown_label_coverage": label_coverage,
            "rows_resolved_y_actionable": int(frame["y_actionable"].notna().sum()),
            "rows_positive_y_actionable": int((frame["y_actionable"] == 1).sum()),
            "rows_known_breakdown_negative": int(
                (frame["breakdown_labels_available"] & frame["y_actionable"].eq(0)).sum()
            ),
        },
        "warning": "Only prior-fold OOF predictions may be used for cascade training; final/holdout tables are evaluation-only.",
    }
    manifest_path = args.manifest_output or args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
