"""Read-only API for the frozen V6 long-term trend advisory."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd
from flask import Blueprint, jsonify, request

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE_PATH = ROOT / "deploy" / "wave_v6_advisory" / "serving_release.json"
DEFAULT_RUN_ROOT = ROOT / "runs" / "wave_v6_daily"
DEFAULT_LSTM_POINTER_PATH = ROOT / "deploy" / "price_forecast_lstm" / "daily_release.json"
DEFAULT_LSTM_JSON_PATH = ROOT / "runs" / "lstm_notebook_replay" / "predictions" / "price_forecast_lstm" / "predict_top50_stocks.json"
MAX_LIMIT = 50
MAX_UNIVERSE = 5_000

wave_v6_bp = Blueprint("wave_v6_bp", __name__, url_prefix="/api/wave-v6")


class V6ReleaseError(RuntimeError):
    """Raised when the frozen V6 serving release is invalid."""


def _release_path() -> Path:
    configured = os.environ.get("WAVE_V6_RELEASE_PATH")
    if not configured:
        return DEFAULT_RELEASE_PATH
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def _run_root() -> Path:
    configured = os.environ.get("WAVE_V6_RUN_ROOT")
    if not configured:
        return DEFAULT_RUN_ROOT
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V6ReleaseError(f"Cannot read V6 serving release: {path}") from exc
    if not isinstance(value, dict):
        raise V6ReleaseError("V6 serving release must be a JSON object.")
    return value


def _artifact_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_artifact(record: Any, label: str) -> Path:
    if not isinstance(record, dict) or not isinstance(record.get("path"), str):
        raise V6ReleaseError(f"{label} record is absent from the serving release.")
    path = _artifact_path(record["path"])
    if not path.is_file():
        raise V6ReleaseError(f"{label} is missing.")
    return path


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _lstm_prediction_artifact() -> tuple[Path, dict[str, Any] | None]:
    """Resolve the verified LSTM artifact and its dated release pointer."""

    pointer_value = os.environ.get("LSTM_PRICE_RELEASE_POINTER_PATH")
    pointer_path = Path(pointer_value) if pointer_value else DEFAULT_LSTM_POINTER_PATH
    if not pointer_path.is_absolute():
        pointer_path = ROOT / pointer_path
    if pointer_path.is_file():
        pointer = _read_json(pointer_path)
        return (
            _verified_artifact(pointer.get("prediction_output"), "LSTM price prediction output"),
            pointer,
        )

    configured = os.environ.get("LSTM_PRICE_PREDICTION_JSON_PATH")
    path = Path(configured) if configured else DEFAULT_LSTM_JSON_PATH
    return (path if path.is_absolute() else ROOT / path), None


def _safe_chart_path(value: Any) -> str | None:
    normalized = str(value or "").strip().replace("\\", "/").lstrip("/")
    if not normalized or ".." in normalized.split("/") or not normalized.startswith("charts/"):
        return None
    return normalized


def _load_lstm_price_predictions(
    expected_as_of_date: str,
) -> tuple[dict[str, dict[str, Any]], str]:
    """Load both the direct daily schema and the notebook replay schema."""

    try:
        path, release_pointer = _lstm_prediction_artifact()
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, V6ReleaseError):
        return {}, "unavailable"

    artifact_as_of = str((release_pointer or {}).get("as_of_date", "") or expected_as_of_date)[:10]

    parsed: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict) and isinstance(payload.get("predictions"), list):
        for item in payload["predictions"]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).strip().upper()
            forecast = item.get("forecast")
            if not symbol or not isinstance(forecast, list) or not forecast:
                continue
            last = forecast[-1] if isinstance(forecast[-1], dict) else {}
            predicted = _number(last.get("predicted_close"))
            last_close = _number(item.get("last_close"))
            if predicted is None or last_close is None or last_close <= 0:
                continue
            parsed[symbol] = {
                "last_close_price": last_close,
                "predicted_price": predicted,
                "forecast": forecast,
                "predicted_on": payload.get("generated_at_utc"),
                "as_of_date": artifact_as_of,
                "chart_path": _safe_chart_path(item.get("chart_path")),
                "forecast_horizon_sessions": len(forecast),
            }
        return parsed, "direct_daily"

    if isinstance(payload, dict):
        for raw_symbol, item in payload.items():
            if not isinstance(item, dict):
                continue
            symbol = str(raw_symbol).strip().upper()
            future = item.get("future")
            if not symbol or not isinstance(future, list) or not future:
                continue
            last = future[-1] if isinstance(future[-1], dict) else {}
            predicted = _number(last.get("predicted_close"))
            last_close = _number(item.get("last_close_price"))
            if predicted is None or last_close is None or last_close <= 0:
                continue
            parsed[symbol] = {
                "last_close_price": last_close,
                "predicted_price": predicted,
                "forecast": future,
                "predicted_on": item.get("predicted_on"),
                "as_of_date": artifact_as_of,
                "chart_path": _safe_chart_path(item.get("chart_path")),
                "forecast_horizon_sessions": len(future),
            }
        return parsed, "notebook_replay"

    return {}, "unavailable"


def _public_prediction(row: dict[str, Any]) -> dict[str, Any]:
    probability = _number(row.get("p_ensemble"))
    if probability is None:
        percent = _number(row.get("p_ensemble_pct"))
        probability = percent / 100.0 if percent is not None else None
    rank = _number(row.get("rank"))
    source_rank = _number(row.get("source_model_rank"))
    public = {
        "symbol": str(row.get("ticker", "")).strip().upper(),
        "date": str(row.get("time", ""))[:10],
        "long_term_rank": int(rank) if rank is not None else None,
        "long_term_trend_probability": probability,
        "model_agreement": _number(row.get("model_agreement")),
        "active_model_agreement": _number(row.get("active_model_agreement")),
    }
    if source_rank is not None and rank is not None and int(source_rank) != int(rank):
        public["source_model_rank"] = int(source_rank)
    return public


def _serving_cohort(frame: pd.DataFrame, release: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, str] | None]:
    """Build the reviewed Top-50 cohort, applying an explicit LSTM substitution."""

    cohort = frame.head(MAX_LIMIT).copy()
    cohort["source_model_rank"] = cohort["rank"]
    record = release.get("top50_output")
    if not isinstance(record, dict):
        return cohort, None
    try:
        payload = _read_json(_verified_artifact(record, "V6 Top-50 output"))
    except V6ReleaseError:
        return cohort, None
    declared = payload.get("symbols")
    if not isinstance(declared, list):
        return cohort, None
    declared_symbols = [
        str(item.get("ticker", "")).strip().upper()
        for item in declared
        if isinstance(item, dict)
    ]
    raw_symbols = cohort["ticker"].astype(str).str.strip().str.upper().tolist()
    if declared_symbols != raw_symbols:
        return cohort, None

    substitution = payload.get("lstm_substitution")
    if not isinstance(substitution, dict):
        return cohort, None
    excluded = str(substitution.get("excluded", "")).strip().upper()
    replacement = str(substitution.get("replacement", "")).strip().upper()
    if not excluded or not replacement or excluded not in raw_symbols or replacement in raw_symbols:
        return cohort, None
    replacement_rows = frame[
        frame["ticker"].astype(str).str.strip().str.upper() == replacement
    ]
    if len(replacement_rows) != 1:
        return cohort, None
    position = raw_symbols.index(excluded)
    excluded_rank = cohort.iloc[position]["rank"]
    replacement_row = replacement_rows.iloc[[0]].copy()
    replacement_row["source_model_rank"] = replacement_row["rank"]
    replacement_row["rank"] = excluded_rank
    cohort = pd.concat(
        [cohort.iloc[:position], replacement_row, cohort.iloc[position + 1 :]],
        ignore_index=True,
    )
    return cohort, {"excluded": excluded, "replacement": replacement}


def _validate_release() -> tuple[Path, dict[str, Any]]:
    release_path = _release_path()
    release = _read_json(release_path)
    contract = release.get("contract", {})
    if (
        release.get("release_kind") != "production_serving_advisory"
        or contract.get("advisory_only") is not True
        or contract.get("trade_authorized") is not False
        or contract.get("independent_from_h120") is not True
        or contract.get("fixed_horizon_sessions", "missing") is not None
    ):
        raise V6ReleaseError("V6 advisory contract validation failed.")
    return release_path, release


def _run_candidates() -> list[Path]:
    root = _run_root()
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.glob("*/orchestration_manifest.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _select_output_record(release: dict[str, Any]) -> tuple[Path, dict[str, Any], dict[str, Any] | None]:
    """Use the latest valid dated run, otherwise the pinned release artifact."""

    expected_bundle_hash = str(release.get("model_bundle", {}).get("sha256", "")).lower()
    for manifest_path in _run_candidates():
        try:
            run = _read_json(manifest_path)
            if (
                run.get("status") != "success"
                or run.get("trade_authorized") is not False
                or run.get("independent_from_h120") is not True
                or run.get("fixed_horizon_sessions", "missing") is not None
                or str(run.get("model_bundle", {}).get("sha256", "")).lower() != expected_bundle_hash
            ):
                continue
            output_record = run.get("prediction_output")
            output_path = _verified_artifact(output_record, "V6 daily prediction output")
            return output_path, output_record, {"path": manifest_path, "value": run}
        except V6ReleaseError:
            continue
    output_record = release.get("prediction_output")
    return _verified_artifact(output_record, "V6 prediction output"), output_record, None


def _load_release(limit: int) -> dict[str, Any]:
    release_path, release = _validate_release()

    output_path, output_record, run = _select_output_record(release)
    try:
        frame = pd.read_csv(output_path)
    except Exception as exc:  # noqa: BLE001 - normalize parser failures to fail closed
        raise V6ReleaseError("Cannot read the V6 prediction output.") from exc

    required = {"time", "ticker", "rank", "p_ensemble"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise V6ReleaseError(f"V6 prediction output is missing columns: {missing}")
    expected_rows = output_record.get("rows") if isinstance(output_record, dict) else None
    if expected_rows is not None and len(frame) != int(expected_rows):
        raise V6ReleaseError("V6 prediction row count does not match the serving release.")

    dates = pd.to_datetime(frame["time"], errors="coerce").dt.strftime("%Y-%m-%d")
    as_of_date = str(run["value"].get("as_of_date", "")) if run else str(release.get("as_of_date", ""))
    if dates.isna().any() or set(dates.unique()) != {as_of_date}:
        raise V6ReleaseError("V6 prediction dates do not match the serving release.")
    frame = frame.assign(time=dates, rank=pd.to_numeric(frame["rank"], errors="coerce"))
    frame = frame.sort_values("rank", kind="stable")
    cohort, cohort_substitution = _serving_cohort(frame, release)
    raw_rows = json.loads(cohort.head(limit).to_json(orient="records"))
    predictions = [_public_prediction(row) for row in raw_rows]
    if any(
        not row["symbol"]
        or row["long_term_rank"] is None
        or row["long_term_trend_probability"] is None
        or not 0.0 <= row["long_term_trend_probability"] <= 1.0
        for row in predictions
    ):
        raise V6ReleaseError("V6 prediction output contains an invalid public row.")

    lstm_predictions, lstm_schema = _load_lstm_price_predictions(as_of_date)
    # The LSTM cohort must be exactly the frozen long-term Top 50.  Do not
    # expose a partial intersection: that would silently attach forecasts
    # trained for a different cohort to the current ranking.
    frozen_top50 = {
        str(value).strip().upper()
        for value in cohort["ticker"].tolist()
        if str(value).strip()
    }
    if len(frozen_top50) == MAX_LIMIT and set(lstm_predictions) == frozen_top50:
        for row in predictions:
            row["price_forecast"] = lstm_predictions[row["symbol"]]
    elif lstm_predictions:
        lstm_schema = f"{lstm_schema}_cohort_mismatch"

    selected_manifest_path = run["path"] if run else release_path
    selected_manifest = run["value"] if run else release
    manifest_display = (
        selected_manifest_path.relative_to(ROOT).as_posix()
        if selected_manifest_path.is_relative_to(ROOT)
        else str(selected_manifest_path)
    )
    return {
        "trend_type": "long_term",
        "as_of_date": as_of_date,
        "snapshot_date": selected_manifest.get("snapshot_date"),
        "release_id": release.get("release_id"),
        "run_id": selected_manifest.get("run_id"),
        "deployment_status": release.get("release_kind"),
        "trade_authorized": False,
        "manifest": manifest_display,
        "summary": {
            "eligible_rows": int(len(frame)),
            "shortlist_rows": min(50, int(len(frame))),
            "returned_rows": int(len(predictions)),
            "price_forecast_rows": sum(1 for row in predictions if row.get("price_forecast")),
            "cohort_substitution": cohort_substitution,
        },
        "advisory": {
            "probability_field": "long_term_trend_probability",
            "fixed_horizon_sessions": None,
            "horizon_policy": "unbounded_first_confirmed_structural_event",
            "advisory_only": True,
            "not_a_trade_instruction": True,
            "independent_from_h120": True,
            "price_forecast_schema": lstm_schema,
        },
        "predictions": predictions,
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


@wave_v6_bp.get("/latest")
def latest_v6_predictions():
    try:
        payload = _load_release(_limit())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except V6ReleaseError as exc:
        return jsonify({"error": str(exc), "trade_authorized": False}), 503
    return jsonify(payload)


@wave_v6_bp.get("/<symbol>")
def v6_prediction_for_symbol(symbol: str):
    normalized = symbol.strip().upper()
    if not normalized.isalnum() or not 1 <= len(normalized) <= 10:
        return jsonify({"error": "symbol must contain 1-10 letters or digits"}), 400
    try:
        payload = _load_release(MAX_UNIVERSE)
    except V6ReleaseError as exc:
        return jsonify({"error": str(exc), "trade_authorized": False}), 503
    matches = [row for row in payload["predictions"] if row["symbol"] == normalized]
    if not matches:
        return jsonify({"error": f"No V6 long-term prediction found for {normalized}"}), 404
    payload["predictions"] = matches[:1]
    payload["summary"]["returned_rows"] = 1
    return jsonify(payload)
