from __future__ import annotations

import pandas as pd

from scripts.generate_lstm_forecast_charts import generate_charts


def test_chart_history_is_cut_at_prediction_as_of_date(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    times = pd.date_range("2026-08-03", periods=10, freq="D")
    pd.DataFrame(
        {
            "time": times,
            "open": range(10, 20),
            "high": range(11, 21),
            "low": range(9, 19),
            "close": range(10, 20),
            "volume": [100] * 10,
        }
    ).to_csv(snapshot / "AAA.csv", index=False)
    payload = {
        "as_of_date": "2026-08-08",
        "predictions": [
            {
                "symbol": "AAA",
                "predicted_on": "2026-08-30 01:45:34",
                "forecast": [
                    {"horizon_session": 1, "predicted_close": 20.0},
                    {"horizon_session": 2, "predicted_close": 21.0},
                ],
            }
        ],
    }
    output = tmp_path / "charts"
    assert generate_charts(payload, snapshot, output, "charts") == 1
    assert (output / "AAA_20260830_014534.png").is_file()
    assert payload["predictions"][0]["chart_path"] == "charts/AAA_20260830_014534.png"
