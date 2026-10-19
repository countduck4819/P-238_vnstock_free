"""Read-only API for the latest H120 shadow predictions."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from flask import Blueprint, jsonify, request

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = ROOT / "runs" / "wave_h120_shadow"
# Published by the model_scoring worker next to its runs (deploy/ is read-only).
DEFAULT_SERVING_RELEASE = DEFAULT_RUN_ROOT / "serving_release.json"
MAX_LIMIT = 200

wave_h120_bp = Blueprint("wave_h120_bp", __name__, url_prefix="/api/wave-h120")


class ShadowOutputError(RuntimeError):
    """Raised when the latest shadow artifact cannot be served safely."""


def _run_root() -> Path:
    configured = os.environ.get("WAVE_H120_RUN_ROOT")
    if not configured:
        return DEFAULT_RUN_ROOT
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShadowOutputError(f"Cannot read shadow manifest: {path}") from exc


def _manifest_candidates(run_root: Path, as_of_date: str | None) -> list[Path]:
    """Return manifests newest-first, filtering by effective market date.

    Run directory names use the snapshot download date.  The API date filter
    deliberately uses the effective market bar recorded in the manifest, so a
    Sunday download can safely serve Friday's close.
    """

    candidates = sorted(
        (path for path in run_root.glob("*/orchestration_manifest.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    # The production pointer is the canonical fallback when the serving
    # container receives only frozen deploy artifacts and not the full run
    # history. Its source manifest still contains the same verified output
    # contract used below (path, size and sha256).
    release_path = Path(os.environ.get("WAVE_H120_SERVING_RELEASE", DEFAULT_SERVING_RELEASE))
    if not release_path.is_absolute():
        release_path = ROOT / release_path
    try:
        release = _read_json(release_path)
        source = release.get("source_orchestration_manifest")
        if isinstance(source, str):
            source_path = _artifact_path(source)
            if source_path.is_file() and source_path not in candidates:
                candidates.append(source_path)
    except ShadowOutputError:
        pass

    if not as_of_date:
        return candidates
    selected: list[Path] = []
    for path in candidates:
        try:
            if _read_json(path).get("as_of_date") == as_of_date:
                selected.append(path)
        except ShadowOutputError:
            continue
    return selected


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


def _public_prediction(row: dict[str, Any]) -> dict[str, Any]:
    """Expose only the advisory probability contract needed by product UI."""

    probability = row.get("p_cascade_calibrated")
    if probability is None:
        probability = row.get("p_h120")
    return {
        "symbol": row.get("symbol"),
        "date": row.get("date"),
        "rank": row.get("rank"),
        "selected_top_k": bool(row.get("selected_top_k", False)),
        "continuation_probability_h120": probability,
    }


def _load_shadow(as_of_date: str | None, limit: int) -> dict[str, Any]:
    # Prefer the explicitly published serving release.
    release_path = Path(
        os.environ.get("WAVE_H120_SERVING_RELEASE", DEFAULT_SERVING_RELEASE)
    )
    if not release_path.is_absolute():
        release_path = ROOT / release_path

    try:
        release = _read_json(release_path)

        release_as_of = release.get("as_of_date")
        if not as_of_date or release_as_of == as_of_date:
            contract = release.get("contract", {})
            if contract.get("trade_authorized") is not False:
                raise ShadowOutputError(
                    "serving release trade_authorized is not false"
                )

            output_record = release.get("prediction_output", {})
            output_path_value = output_record.get("path")
            if not isinstance(output_path_value, str):
                raise ShadowOutputError(
                    "serving release prediction output path is absent"
                )

            output_path = _artifact_path(output_path_value)
            if not output_path.is_file():
                raise ShadowOutputError(
                    "serving release prediction output is missing"
                )

            expected_size = output_record.get("size_bytes")
            if (
                expected_size is not None
                and output_path.stat().st_size != int(expected_size)
            ):
                raise ShadowOutputError(
                    "serving release prediction output size does not match"
                )

            expected_sha = output_record.get("sha256")
            if expected_sha and _sha256(output_path) != expected_sha:
                raise ShadowOutputError(
                    "serving release prediction output hash does not match"
                )

            frame = pd.read_parquet(output_path)

            if "rank" in frame.columns and "selected_top_k" in frame.columns:
                frame = frame.sort_values(
                    ["selected_top_k", "rank"],
                    ascending=[False, True],
                    kind="stable",
                )

            raw_rows = json.loads(
                frame.head(limit).to_json(
                    orient="records",
                    date_format="iso",
                )
            )
            rows = [_public_prediction(row) for row in raw_rows]

            eligible_rows = int(
                frame["feature_ready"].fillna(False).astype(bool).sum()
            ) if "feature_ready" in frame.columns else len(frame)

            shortlist_rows = int(
                frame["selected_top_k"].fillna(False).astype(bool).sum()
            ) if "selected_top_k" in frame.columns else 0

            return {
                "trend_type": "short_term",
                "as_of_date": release.get("as_of_date"),
                "snapshot_date": release.get("snapshot_date"),
                "deployment_status": "shadow_candidate_requires_new_holdout",
                "trade_authorized": False,
                "manifest": release_path.relative_to(ROOT).as_posix()
                    if release_path.is_relative_to(ROOT)
                    else str(release_path),
                "summary": {
                    "eligible_rows": eligible_rows,
                    "shortlist_rows": shortlist_rows,
                },
                "advisory": {
                    "probability_field": "continuation_probability_h120",
                    "horizon_sessions": 120,
                    "advisory_only": True,
                    "not_a_trade_instruction": True,
                },
                "predictions": rows,
            }

    except ShadowOutputError:
        # Fall back to historical successful orchestration artifacts.
        pass

    run_root = _run_root()
    candidates = _manifest_candidates(run_root, as_of_date)
    if not candidates:
        scope = f" for {as_of_date}" if as_of_date else ""
        raise ShadowOutputError(
            f"No shadow orchestration manifest found{scope}."
        )

    failures: list[str] = []
    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None
    frame: pd.DataFrame | None = None

    for candidate in candidates:
        try:
            candidate_manifest = _read_json(candidate)

            if candidate_manifest.get("status") != "success":
                raise ShadowOutputError("run status is not success")

            if candidate_manifest.get("trade_authorized") is not False:
                raise ShadowOutputError("trade_authorized is not false")

            output_record = candidate_manifest.get(
                "predictions", {}
            ).get("output", {})

            output_path_value = output_record.get("path")
            if not isinstance(output_path_value, str):
                raise ShadowOutputError(
                    "prediction output path is absent"
                )

            output_path = _artifact_path(output_path_value)

            if not output_path.is_file():
                raise ShadowOutputError(
                    "prediction output is missing"
                )

            if (
                output_record.get("size_bytes") is not None
                and output_path.stat().st_size
                != int(output_record["size_bytes"])
            ):
                raise ShadowOutputError(
                    "prediction output size does not match manifest"
                )

            if (
                output_record.get("sha256")
                and _sha256(output_path)
                != output_record["sha256"]
            ):
                raise ShadowOutputError(
                    "prediction output hash does not match manifest"
                )

            frame = pd.read_parquet(output_path)
            manifest_path = candidate
            manifest = candidate_manifest
            break

        except Exception as exc:
            failures.append(f"{candidate.name}: {exc}")

    if manifest_path is None or manifest is None or frame is None:
        details = "; ".join(failures[:3])
        raise ShadowOutputError(
            f"No valid successful shadow artifact found. {details}"
        )

    if "rank" in frame.columns and "selected_top_k" in frame.columns:
        frame = frame.sort_values(
            ["selected_top_k", "rank"],
            ascending=[False, True],
            kind="stable",
        )

    raw_rows = json.loads(
        frame.head(limit).to_json(
            orient="records",
            date_format="iso",
        )
    )
    rows = [_public_prediction(row) for row in raw_rows]

    summary = manifest.get("predictions", {}).get("summary", {})

    manifest_display = (
        manifest_path.relative_to(ROOT).as_posix()
        if manifest_path.is_relative_to(ROOT)
        else str(manifest_path)
    )

    return {
        "trend_type": "short_term",
        "as_of_date": manifest.get("as_of_date"),
        "snapshot_date": manifest.get("snapshot_date"),
        "requested_as_of_date": manifest.get("requested_as_of_date"),
        "run_id": manifest.get("run_id"),
        "deployment_status": manifest.get("deployment_status"),
        "trade_authorized": False,
        "manifest": manifest_display,
        "summary": summary,
        "advisory": {
            "probability_field": "continuation_probability_h120",
            "horizon_sessions": 120,
            "advisory_only": True,
            "not_a_trade_instruction": True,
        },
        "predictions": rows,
    }


def _limit() -> int:
    raw = request.args.get("limit", "10")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc
    if not 1 <= value <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    return value


@wave_h120_bp.get("/latest")
def latest_h120_predictions():
    try:
        payload = _load_shadow(request.args.get("date"), _limit())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except ShadowOutputError as exc:
        return jsonify({"error": str(exc), "trade_authorized": False}), 503
    return jsonify(payload)


@wave_h120_bp.get("/<symbol>")
def h120_prediction_for_symbol(symbol: str):
    try:
        payload = _load_shadow(request.args.get("date"), MAX_LIMIT)
    except ShadowOutputError as exc:
        return jsonify({"error": str(exc), "trade_authorized": False}), 503

    normalized = symbol.strip().upper()
    matches = [
        row
        for row in payload["predictions"]
        if str(row.get("symbol", "")).upper() == normalized
    ]
    if not matches:
        return jsonify({"error": f"No H120 shadow prediction found for {normalized}"}), 404
    payload["predictions"] = matches[:1]
    return jsonify(payload)
