"""Generate web-served Hybrid forecast charts without retraining the model."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def _load_history(snapshot_dir: Path, symbol: str) -> pd.DataFrame:
    path = snapshot_dir / f"{symbol}.csv"
    frame = pd.read_csv(path, usecols=["time", "close"])
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce").dt.tz_localize(None)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna().sort_values("time").drop_duplicates("time", keep="last")


def _forecast_cutoff(
    payload: dict[str, Any], item: dict[str, Any], raw_forecast: list[dict[str, Any]], history: pd.DataFrame
) -> pd.Timestamp:
    """Resolve the observation date used by a forecast before plotting it.

    Older prediction artifacts only contain dated future rows; newer daily
    artifacts carry ``as_of_date`` at payload level.  Never plot history after
    that cutoff: doing so makes a forecast from one snapshot appear attached to
    a newer snapshot and was the source of the UI's shifted trend line.
    """
    candidates = (item.get("as_of_date"), payload.get("as_of_date"))
    for value in candidates:
        if value:
            parsed = pd.to_datetime(value, errors="coerce")
            if not pd.isna(parsed):
                parsed = parsed.tz_localize(None) if getattr(parsed, "tzinfo", None) else parsed
                # Snapshot timestamps can carry a provider wall-clock time
                # (often 07:00), while JSON contracts use a date only.  Treat
                # that date as inclusive through end-of-day.
                if isinstance(value, str) and len(value.strip()) <= 10:
                    return parsed.normalize() + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
                return parsed

    dated = [pd.to_datetime(row.get("date"), errors="coerce") for row in raw_forecast]
    dated = [value for value in dated if not pd.isna(value)]
    if dated:
        first_future = min(dated)
        prior = history.loc[history["time"] < first_future, "time"]
        if not prior.empty:
            return prior.iloc[-1]

    return history["time"].iloc[-1]


def _items(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any], list[dict[str, Any]]]]:
    if isinstance(payload.get("predictions"), list):
        result = []
        for item in payload["predictions"]:
            symbol = str(item.get("symbol", "")).strip().upper()
            forecast = item.get("forecast", [])
            if symbol and isinstance(forecast, list):
                result.append((symbol, item, forecast))
        return result
    result = []
    for raw_symbol, item in payload.items():
        if isinstance(item, dict) and isinstance(item.get("future"), list):
            result.append((str(raw_symbol).strip().upper(), item, item["future"]))
    return result


def _chart_stamp(payload: dict[str, Any], item: dict[str, Any]) -> str:
    """Return the production timestamp suffix used in chart filenames."""
    raw = item.get("predicted_on") or payload.get("predicted_on")
    parsed = pd.to_datetime(raw, errors="coerce") if raw else pd.NaT
    if pd.isna(parsed):
        # The prediction artifact normally always carries predicted_on.  Keep
        # the generator usable for older artifacts while preserving the
        # production filename contract.
        parsed = pd.Timestamp.now()
    if getattr(parsed, "tzinfo", None):
        parsed = parsed.tz_localize(None)
    return parsed.strftime("%Y%m%d_%H%M%S")


def _refresh_release_records(prediction_path: Path) -> int:
    digest = hashlib.sha256(prediction_path.read_bytes()).hexdigest()
    changed = 0
    for metadata_path in prediction_path.parent.glob("*release.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        record = metadata.get("prediction_output")
        if not isinstance(record, dict):
            continue
        recorded_path = record.get("path")
        if not isinstance(recorded_path, str) or _path(Path(recorded_path)).resolve() != prediction_path.resolve():
            continue
        record["sha256"] = digest
        record["size_bytes"] = prediction_path.stat().st_size
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed += 1
    return changed


def generate_charts(
    payload: dict[str, Any], snapshot_dir: Path, output_dir: Path, public_prefix: str
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for symbol, item, raw_forecast in _items(payload):
        full_history = _load_history(snapshot_dir, symbol)
        if full_history.empty:
            continue
        cutoff = _forecast_cutoff(payload, item, raw_forecast, full_history)
        full_history = full_history.loc[full_history["time"] <= cutoff]
        if full_history.empty:
            continue
        history = full_history.tail(250)
        values = [float(row["predicted_close"]) for row in raw_forecast]
        if not values:
            continue
        if "date" in raw_forecast[0]:
            forecast_x = pd.to_datetime([row["date"] for row in raw_forecast], errors="coerce")
            if forecast_x.isna().any() or (forecast_x <= cutoff).any():
                raise ValueError(f"{symbol}: forecast dates must be valid and after as_of cutoff {cutoff.date()}.")
        else:
            start = cutoff
            forecast_x = pd.bdate_range(start=start, periods=len(values) + 1)[1:]

        fig, ax = plt.subplots(figsize=(11, 5.5))
        ax.plot(history["time"], history["close"], color="#64748b", linewidth=1.5, label="Lịch sử")
        ax.plot(forecast_x, values, color="#2563eb", linewidth=2, label="Dự đoán Hybrid")
        ax.plot(
            [history["time"].iloc[-1], forecast_x[0]],
            [history["close"].iloc[-1], values[0]],
            color="#2563eb",
            linewidth=2,
        )
        ax.axvline(history["time"].iloc[-1], color="#94a3b8", linestyle="--", linewidth=1)
        ax.set(title=f"{symbol} — Dự đoán giá Hybrid", xlabel="Phiên", ylabel="Giá đóng cửa")
        ax.grid(alpha=0.2)
        ax.legend()
        fig.tight_layout()
        filename = f"{symbol}_{_chart_stamp(payload, item)}.png"
        fig.savefig(output_dir / filename, dpi=130, bbox_inches="tight")
        plt.close(fig)
        item["chart_path"] = f"{public_prefix.strip('/')}/{filename}"
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("web/public/charts"))
    parser.add_argument("--public-prefix", default="charts")
    parser.add_argument("--write-json", type=Path, help="Write the payload with updated chart_path values here.")
    args = parser.parse_args()

    prediction_path = _path(args.predictions)
    payload = json.loads(prediction_path.read_text(encoding="utf-8"))
    count = generate_charts(payload, _path(args.snapshot_dir), _path(args.output_dir), args.public_prefix)
    destination = _path(args.write_json) if args.write_json else prediction_path
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")
    refreshed = _refresh_release_records(destination)
    print(json.dumps({"charts_generated": count, "release_records_refreshed": refreshed, "output_dir": str(_path(args.output_dir)), "json": str(destination)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
