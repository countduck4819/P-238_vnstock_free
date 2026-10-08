from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
from flask import Flask

MODULE_PATH = Path(__file__).resolve().parents[2] / "python_data" / "routes" / "wave_v6.py"
SPEC = importlib.util.spec_from_file_location("wave_v6_route_test", MODULE_PATH)
assert SPEC and SPEC.loader
wave_v6 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wave_v6)


def _release(tmp_path: Path) -> Path:
    output = tmp_path / "predictions.csv"
    pd.DataFrame(
        [
            {
                "time": "2026-08-11",
                "ticker": "FPT",
                "rank": 1,
                "p_ensemble": 0.72,
                "model_agreement": 0.91,
                "active_model_agreement": 0.94,
            }
        ]
    ).to_csv(output, index=False)
    release = {
        "release_id": "test-v6",
        "release_kind": "production_serving_advisory",
        "snapshot_date": "2026-08-12",
        "as_of_date": "2026-08-11",
        "prediction_output": {
            "path": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "size_bytes": output.stat().st_size,
            "rows": 1,
        },
        "model_bundle": {"sha256": "a" * 64},
        "contract": {
            "fixed_horizon_sessions": None,
            "advisory_only": True,
            "trade_authorized": False,
            "independent_from_h120": True,
        },
    }
    path = tmp_path / "release.json"
    path.write_text(json.dumps(release), encoding="utf-8")
    return path


def _client(monkeypatch, release: Path):
    monkeypatch.setenv("WAVE_V6_RELEASE_PATH", str(release))
    monkeypatch.setenv("WAVE_V6_RUN_ROOT", str(release.parent / "runs"))
    app = Flask(__name__)
    app.register_blueprint(wave_v6.wave_v6_bp)
    return app.test_client()


def test_latest_serves_only_independent_long_term_contract(tmp_path, monkeypatch):
    response = _client(monkeypatch, _release(tmp_path)).get("/api/wave-v6/latest?limit=1")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["trade_authorized"] is False
    assert payload["advisory"]["independent_from_h120"] is True
    assert payload["advisory"]["fixed_horizon_sessions"] is None
    assert payload["predictions"] == [
        {
            "active_model_agreement": 0.94,
            "date": "2026-08-11",
            "long_term_rank": 1,
            "long_term_trend_probability": 0.72,
            "model_agreement": 0.91,
            "symbol": "FPT",
        }
    ]


def test_latest_fails_closed_after_artifact_tampering(tmp_path, monkeypatch):
    release = _release(tmp_path)
    (tmp_path / "predictions.csv").write_text("tampered", encoding="utf-8")
    response = _client(monkeypatch, release).get("/api/wave-v6/latest?limit=1")
    assert response.status_code == 503
    assert response.get_json()["trade_authorized"] is False


def test_latest_prefers_a_newer_verified_daily_run(tmp_path, monkeypatch):
    release = _release(tmp_path)
    run_dir = tmp_path / "runs" / "2026-08-25_test"
    run_dir.mkdir(parents=True)
    output = run_dir / "predictions.csv"
    pd.DataFrame([{"time": "2026-08-22", "ticker": "VCB", "rank": 1, "p_ensemble": 0.81}]).to_csv(output, index=False)
    release_payload = json.loads(release.read_text(encoding="utf-8"))
    run = {
        "status": "success",
        "run_id": "test",
        "snapshot_date": "2026-08-25",
        "as_of_date": "2026-08-22",
        "trade_authorized": False,
        "independent_from_h120": True,
        "fixed_horizon_sessions": None,
        "model_bundle": {"sha256": release_payload["model_bundle"]["sha256"]},
        "prediction_output": {
            "path": str(output), "size_bytes": output.stat().st_size,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "rows": 1,
        },
    }
    (run_dir / "orchestration_manifest.json").write_text(json.dumps(run), encoding="utf-8")
    payload = _client(monkeypatch, release).get("/api/wave-v6/latest?limit=1").get_json()
    assert payload["as_of_date"] == "2026-08-22"
    assert payload["run_id"] == "test"
    assert payload["predictions"][0]["symbol"] == "VCB"


def test_lstm_artifact_requires_same_as_of_and_keeps_safe_chart_path(tmp_path, monkeypatch):
    predictions = tmp_path / "price_predictions.json"
    predictions.write_text(
        json.dumps(
            {
                "FPT": {
                    "last_close_price": 100.0,
                    "predicted_on": "2026-08-30 08:00:00",
                    "chart_path": "charts/FPT_20260830_080000.png",
                    "future": [{"date": "2026-08-28", "predicted_close": 110.0}],
                }
            }
        ),
        encoding="utf-8",
    )
    pointer = tmp_path / "daily_release.json"
    pointer.write_text(
        json.dumps(
            {
                "as_of_date": "2026-08-27",
                "prediction_output": {
                    "path": str(predictions),
                    "sha256": hashlib.sha256(predictions.read_bytes()).hexdigest(),
                    "size_bytes": predictions.stat().st_size,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LSTM_PRICE_RELEASE_POINTER_PATH", str(pointer))

    parsed, schema = wave_v6._load_lstm_price_predictions("2026-08-27")
    assert schema == "notebook_replay"
    assert parsed["FPT"]["as_of_date"] == "2026-08-27"
    assert parsed["FPT"]["chart_path"] == "charts/FPT_20260830_080000.png"

    parsed, schema = wave_v6._load_lstm_price_predictions("2026-08-26")
    assert parsed == {}
    assert schema == "as_of_date_mismatch"


def test_reviewed_substitution_keeps_cohort_at_50(tmp_path):
    frame = pd.DataFrame(
        [
            {
                "time": "2026-08-27",
                "ticker": f"S{rank:02d}",
                "rank": rank,
                "p_ensemble": 0.5,
            }
            for rank in range(1, 52)
        ]
    )
    declared = [
        {"rank": rank, "ticker": f"S{rank:02d}"}
        for rank in range(1, 51)
    ]
    top50 = tmp_path / "top50.json"
    top50.write_text(
        json.dumps(
            {
                "symbols": declared,
                "lstm_substitution": {"excluded": "S26", "replacement": "S51"},
            }
        ),
        encoding="utf-8",
    )
    release = {
        "top50_output": {
            "path": str(top50),
            "sha256": hashlib.sha256(top50.read_bytes()).hexdigest(),
            "size_bytes": top50.stat().st_size,
        }
    }

    cohort, substitution = wave_v6._serving_cohort(frame, release)
    assert len(cohort) == 50
    assert "S26" not in set(cohort["ticker"])
    replacement = cohort[cohort["ticker"] == "S51"].iloc[0]
    assert replacement["rank"] == 26
    assert replacement["source_model_rank"] == 51
    assert substitution == {"excluded": "S26", "replacement": "S51"}
