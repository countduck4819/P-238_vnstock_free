"""Compare V6 candidate runs against the original three-model ensemble.

The final-holdout values are descriptive replays because that holdout was
already observed by the original ensemble.  This script never promotes a
winner from final-holdout metrics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_BASELINE = Path("eval/runs/wave_v6_local")
DEFAULT_CANDIDATES = Path("eval/runs/v6_model_benchmark")


def _markdown_table(frame: pd.DataFrame) -> str:
    """Render a compact Markdown table without the optional tabulate package."""
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = []
    for values in frame.itertuples(index=False, name=None):
        rendered = []
        for value in values:
            if isinstance(value, float):
                rendered.append(f"{value:.6f}")
            elif pd.isna(value):
                rendered.append("")
            else:
                rendered.append(str(value))
        rows.append("| " + " | ".join(rendered) + " |")
    return "\n".join([header, divider, *rows])


def _read_row(path: Path, model: str) -> dict[str, Any]:
    table = pd.read_csv(path)
    matched = table.loc[table["model"].eq(model)]
    if matched.empty:
        raise ValueError(f"{path} has no '{model}' row")
    return matched.iloc[0].to_dict()


def _candidate_row(
    name: str, directory: Path, walk_forward_model: str | None
) -> dict[str, Any]:
    final = _read_row(directory / "model_metrics_final_holdout.csv", "ensemble")
    row: dict[str, Any] = {
        "candidate": name,
        "report_directory": str(directory),
        **{f"final_{key}": value for key, value in final.items() if key != "model"},
    }
    summary_path = directory / "model_metrics_walk_forward_summary.csv"
    if walk_forward_model is not None and summary_path.is_file():
        summary = _read_row(summary_path, walk_forward_model)
        row.update({f"walk_forward_{key}": value for key, value in summary.items() if key != "model"})
    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--candidate-root", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_CANDIDATES / "comparison")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = [_candidate_row("original_xgb_lgb_cat_ensemble", args.baseline_dir, None)]
    missing: dict[str, str] = {}
    for name, walk_forward_model in (
        ("xgboost", "xgb"),
        ("catboost", "cat"),
        ("lightgbm", "lgb"),
        ("xgb_cat_ensemble", None),
    ):
        try:
            rows.append(_candidate_row(name, args.candidate_root / name, walk_forward_model))
        except (FileNotFoundError, ValueError) as exc:
            missing[name] = str(exc)

    result = pd.DataFrame(rows)
    preferred = [
        "candidate", "final_event_weighted_pr_auc", "final_weighted_lift_at_k",
        "final_weighted_precision_at_k", "final_event_weighted_brier", "final_pr_auc",
        "final_roc_auc", "final_brier", "final_ece_10_bins", "final_f1",
        "walk_forward_pr_lift_mean", "walk_forward_lift_at_50_mean",
        "walk_forward_pr_auc_mean", "walk_forward_roc_auc_mean", "walk_forward_brier_mean",
    ]
    result = result[[column for column in preferred if column in result.columns]]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output_dir / "candidate_comparison.csv", index=False)
    payload = {
        "selection_status": "diagnostic_only_final_holdout_previously_observed",
        "candidates_completed": result["candidate"].tolist(),
        "candidates_missing": missing,
        "selection_policy": (
            "Future winner selection must use causal walk-forward/OOF metrics; "
            "the final-holdout replay is descriptive only."
        ),
    }
    (args.output_dir / "candidate_comparison.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = "# V6 candidate comparison\n\n"
    markdown += "Final-holdout values are descriptive replays, not promotion evidence.\n\n"
    markdown += _markdown_table(result) + "\n"
    (args.output_dir / "candidate_comparison.md").write_text(markdown, encoding="utf-8")
    print(result.to_string(index=False))
    if missing:
        print("Pending candidates:", ", ".join(sorted(missing)))


if __name__ == "__main__":
    main()
