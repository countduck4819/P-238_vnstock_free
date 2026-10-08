from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from flask import Flask

PYTHON_DATA_ROOT = Path(__file__).resolve().parents[2] / "python_data"
if str(PYTHON_DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_DATA_ROOT))

from routes.wave_h120 import (  # noqa: E402
    ShadowOutputError,
    _load_shadow,
    wave_h120_bp,
)


def _write_run(root: Path, *, trade_authorized: bool = False) -> Path:
    run_dir = root / "2026-08-11_20260824T000000Z"
    output = run_dir / "predictions" / "2026-08-11" / "predictions.parquet"
    output.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "date": "2026-08-11",
                "rank": 1,
                "selected_top_k": True,
                "p_h120": 0.9,
            },
            {
                "symbol": "BBB",
                "date": "2026-08-11",
                "rank": 2,
                "selected_top_k": False,
                "p_h120": 0.8,
            },
        ]
    ).to_parquet(output, index=False)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = {
        "status": "success",
        "run_id": "20260824T000000Z",
        "as_of_date": "2026-08-11",
        "deployment_status": "shadow_candidate_requires_new_holdout",
        "trade_authorized": trade_authorized,
        "predictions": {
            "output": {
                "path": str(output),
                "size_bytes": output.stat().st_size,
                "sha256": digest,
            },
            "summary": {"eligible_rows": 2, "shortlist_rows": 1},
        },
    }
    manifest_path = run_dir / "orchestration_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_load_shadow_verifies_manifest_and_returns_shortlist_first(tmp_path, monkeypatch):
    _write_run(tmp_path)
    monkeypatch.setenv("WAVE_H120_RUN_ROOT", str(tmp_path))

    payload = _load_shadow(None, 2)

    assert payload["trade_authorized"] is False
    assert [row["symbol"] for row in payload["predictions"]] == ["AAA", "BBB"]
    assert payload["advisory"]["advisory_only"] is True
    assert payload["predictions"][0]["continuation_probability_h120"] == 0.9


def test_load_shadow_rejects_trade_authorized_artifact(tmp_path, monkeypatch):
    _write_run(tmp_path, trade_authorized=True)
    monkeypatch.setenv("WAVE_H120_RUN_ROOT", str(tmp_path))

    with pytest.raises(ShadowOutputError, match="trade_authorized"):
        _load_shadow(None, 2)


def test_load_shadow_falls_back_when_newer_run_failed(tmp_path, monkeypatch):
    _write_run(tmp_path)
    failed = tmp_path / "2026-08-23_20260824T000001Z"
    failed.mkdir()
    (failed / "orchestration_manifest.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "as_of_date": "2026-08-21",
                "trade_authorized": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("WAVE_H120_RUN_ROOT", str(tmp_path))

    payload = _load_shadow(None, 1)

    assert payload["as_of_date"] == "2026-08-11"


def test_api_routes_serve_latest_and_symbol(tmp_path, monkeypatch):
    _write_run(tmp_path)
    monkeypatch.setenv("WAVE_H120_RUN_ROOT", str(tmp_path))
    app = Flask(__name__)
    app.register_blueprint(wave_h120_bp)
    client = app.test_client()

    latest = client.get("/api/wave-h120/latest?limit=1")
    symbol = client.get("/api/wave-h120/aaa")

    assert latest.status_code == 200
    assert latest.get_json()["predictions"][0]["symbol"] == "AAA"
    assert symbol.status_code == 200
    assert symbol.get_json()["predictions"][0]["symbol"] == "AAA"
