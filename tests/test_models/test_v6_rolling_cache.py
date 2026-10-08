from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "wave_v6" / "v6_data_adapter.py"
SPEC = importlib.util.spec_from_file_location("v6_rolling_cache_test", MODULE_PATH)
assert SPEC and SPEC.loader
adapter_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter_module)


def _ohlcv(start: str, periods: int) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "time": dates,
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.0,
        "volume": 100.0,
    })


def test_rolling_cache_keeps_fixed_tail_and_replaces_duplicate(tmp_path: Path) -> None:
    adapter = adapter_module.VnstockDataAdapter(cache_dir=tmp_path, history_sessions=480)
    first = adapter._update_rolling_cache(
        _ohlcv("2025-01-01", 480), asset_type="equity", symbol="AAA", interval="1D"
    )
    assert len(first) == 480
    update = _ohlcv("2026-04-25", 10)
    update.loc[0, "close"] = 12.0
    update.loc[0, "high"] = 13.0
    second = adapter._update_rolling_cache(
        update, asset_type="equity", symbol="AAA", interval="1D"
    )
    assert len(second) == 480
    assert second["time"].min() == pd.Timestamp("2025-01-10")
    assert float(second.loc[second["time"].eq(pd.Timestamp("2026-04-25")), "close"].iloc[0]) == 12.0
