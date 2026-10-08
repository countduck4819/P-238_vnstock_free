from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "wave_v6" / "v6_data_adapter.py"
SPEC = importlib.util.spec_from_file_location("v6_data_adapter_cutoff_test", MODULE_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def _frame(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.to_datetime(dates),
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
            "volume": 100.0,
        }
    )


def test_cutoff_keeps_end_date_and_removes_future_provider_rows() -> None:
    result = adapter._clip_ohlcv(
        _frame(["2026-08-10 07:00", "2026-08-11 07:00", "2026-08-14 07:00"]),
        "2026-08-10",
        "2026-08-11",
        "test",
    )
    assert result["time"].dt.strftime("%Y-%m-%d").tolist() == ["2026-08-10", "2026-08-11"]


def test_cutoff_rejects_data_entirely_outside_requested_range() -> None:
    with pytest.raises(adapter.VnstockDataContractError, match="no rows"):
        adapter._clip_ohlcv(
            _frame(["2026-08-14 07:00"]),
            "2026-08-10",
            "2026-08-11",
            "test",
        )


def test_daily_equity_provider_end_is_exclusive() -> None:
    assert adapter._provider_query_end("equity", "2026-08-28", "1D") == "2026-08-29"
    assert adapter._provider_query_end("index", "2026-08-28", "1D") == "2026-08-28"
    assert adapter._provider_query_end("equity", "2026-08-28", "1h") == "2026-08-28"
