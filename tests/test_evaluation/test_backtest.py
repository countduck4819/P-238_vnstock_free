from __future__ import annotations

import numpy as np
import pandas as pd

from src.evaluation.backtest import BacktestConfig, run_backtest


def make_config() -> BacktestConfig:
    return BacktestConfig.from_dict(
        {
            "strategy_version": "test_backtest",
            "score_column": "wave_score",
            "top_k_per_day": 1,
            "initial_capital_vnd": 100_000_000,
            "max_positions": 1,
            "maximum_holding_sessions": 5,
            "stop_loss_fraction": 0.08,
            "take_profit_fraction": 0.15,
            "commission_fraction_per_side": 0.0015,
            "slippage_fraction_per_side": 0.0005,
            "sell_tax_fraction": 0.001,
            "maximum_volume_participation": 0.05,
            "board_lot": 100,
            "price_scale_vnd": 1000,
            "annualization_sessions": 252,
            "risk_free_rate": 0.0,
            "entry_rule": "next_market_session_open",
            "exit_rule": "stop_loss_take_profit_or_max_holding_close",
            "both_barriers_policy": "stop_first",
            "monitor_barriers_from_session_after_entry": True,
        }
    )


def test_backtest_enters_next_session_and_uses_conservative_barrier_order() -> None:
    calendar = pd.bdate_range("2024-01-02", periods=10)
    signals = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "date": [calendar[0]],
            "p_entry_calibrated_temporal": [0.8],
            "p_strength": [0.9],
            "wave_score": [0.72],
        }
    )
    stock = pd.DataFrame(
        {
            "symbol": "AAA",
            "date": calendar,
            "open": 100.0,
            "high": np.array([101.0, 102.0, 120.0, 101.0, 101.0] + [101.0] * 5),
            "low": np.array([99.0, 99.0, 90.0, 99.0, 99.0] + [99.0] * 5),
            "close": 100.0,
            "volume": 1_000_000,
        }
    )
    market = pd.DataFrame(
        {
            "date": calendar,
            "open": np.arange(10) + 1000.0,
            "high": np.arange(10) + 1001.0,
            "low": np.arange(10) + 999.0,
            "close": np.arange(10) + 1000.0,
            "volume": 1_000_000,
        }
    )

    metrics, equity, trades, skipped, yearly = run_backtest(
        signals, stock, market, make_config()
    )

    assert trades.iloc[0]["entry_date"] == calendar[1]
    assert trades.iloc[0]["exit_date"] == calendar[2]
    assert trades.iloc[0]["exit_reason"] == "stop_loss"
    assert trades.iloc[0]["net_return"] < -0.08
    assert metrics["trades"] == 1
    assert not equity.empty
    assert skipped.empty
    assert yearly["trades"].sum() == 1
