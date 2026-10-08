"""Causal long-only portfolio simulation for OOF wave predictions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    strategy_version: str
    score_column: str
    top_k_per_day: int
    initial_capital_vnd: float
    max_positions: int
    maximum_holding_sessions: int
    stop_loss_fraction: float
    take_profit_fraction: float
    commission_fraction_per_side: float
    slippage_fraction_per_side: float
    sell_tax_fraction: float
    maximum_volume_participation: float
    board_lot: int
    price_scale_vnd: float
    annualization_sessions: int
    risk_free_rate: float
    entry_rule: str
    exit_rule: str
    both_barriers_policy: str
    monitor_barriers_from_session_after_entry: bool

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BacktestConfig:
        if payload.get("entry_rule") != "next_market_session_open":
            raise ValueError("Backtest V1 requires next-market-session open entry.")
        if payload.get("both_barriers_policy") != "stop_first":
            raise ValueError("Backtest V1 supports only conservative stop-first ordering.")
        config = cls(
            strategy_version=str(payload["strategy_version"]),
            score_column=str(payload["score_column"]),
            top_k_per_day=int(payload["top_k_per_day"]),
            initial_capital_vnd=float(payload["initial_capital_vnd"]),
            max_positions=int(payload["max_positions"]),
            maximum_holding_sessions=int(payload["maximum_holding_sessions"]),
            stop_loss_fraction=float(payload["stop_loss_fraction"]),
            take_profit_fraction=float(payload["take_profit_fraction"]),
            commission_fraction_per_side=float(payload["commission_fraction_per_side"]),
            slippage_fraction_per_side=float(payload["slippage_fraction_per_side"]),
            sell_tax_fraction=float(payload["sell_tax_fraction"]),
            maximum_volume_participation=float(payload["maximum_volume_participation"]),
            board_lot=int(payload["board_lot"]),
            price_scale_vnd=float(payload["price_scale_vnd"]),
            annualization_sessions=int(payload["annualization_sessions"]),
            risk_free_rate=float(payload["risk_free_rate"]),
            entry_rule=str(payload["entry_rule"]),
            exit_rule=str(payload["exit_rule"]),
            both_barriers_policy=str(payload["both_barriers_policy"]),
            monitor_barriers_from_session_after_entry=bool(
                payload["monitor_barriers_from_session_after_entry"]
            ),
        )
        if config.top_k_per_day <= 0 or config.max_positions <= 0:
            raise ValueError("top_k_per_day and max_positions must be positive.")
        if not 0 < config.maximum_volume_participation <= 1:
            raise ValueError("maximum_volume_participation must be in (0, 1].")
        return config


def _maximum_drawdown(equity: pd.Series) -> float:
    running_peak = equity.cummax()
    drawdown = equity / running_peak - 1.0
    return float(drawdown.min())


def _next_session_map(calendar: pd.DatetimeIndex) -> dict[pd.Timestamp, pd.Timestamp]:
    return {
        pd.Timestamp(calendar[index]): pd.Timestamp(calendar[index + 1])
        for index in range(len(calendar) - 1)
    }


def _prepare_entries(
    signals: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    config: BacktestConfig,
) -> dict[pd.Timestamp, list[dict[str, Any]]]:
    next_session = _next_session_map(calendar)
    ranked = signals.dropna(subset=[config.score_column]).copy()
    ranked["date"] = pd.to_datetime(ranked["date"], errors="raise")
    selected = (
        ranked.sort_values(
            ["date", config.score_column, "symbol"],
            ascending=[True, False, True],
            kind="stable",
        )
        .groupby("date", sort=True, group_keys=False)
        .head(config.top_k_per_day)
        .copy()
    )
    selected["entry_date"] = selected["date"].map(next_session)
    selected.dropna(subset=["entry_date"], inplace=True)
    schedule: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    for entry_date, group in selected.groupby("entry_date", sort=True):
        schedule[pd.Timestamp(entry_date)] = group.to_dict("records")
    return schedule


def run_backtest(
    signals: pd.DataFrame,
    stock_ohlcv: pd.DataFrame,
    vnindex_ohlcv: pd.DataFrame,
    config: BacktestConfig,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run a causal simulation; signals at t can only enter at the next open."""
    stock = stock_ohlcv.copy()
    market = vnindex_ohlcv.copy()
    stock["date"] = pd.to_datetime(stock["date"], errors="raise")
    market["date"] = pd.to_datetime(market["date"], errors="raise")
    calendar = pd.DatetimeIndex(market["date"].sort_values().unique())
    if len(calendar) < 2:
        raise ValueError("Backtest requires at least two market sessions.")
    calendar_position = {pd.Timestamp(date): index for index, date in enumerate(calendar)}
    price_lookup = stock.set_index(["symbol", "date"]).sort_index()
    schedule = _prepare_entries(signals, calendar, config)
    if not schedule:
        raise RuntimeError("No executable backtest signals remain after scheduling.")
    first_entry = min(schedule)
    last_signal = pd.to_datetime(signals["date"]).max()
    final_position = min(
        len(calendar) - 1,
        calendar_position.get(pd.Timestamp(last_signal), len(calendar) - 1)
        + config.maximum_holding_sessions
        + 1,
    )
    simulation_calendar = calendar[
        calendar_position[first_entry] : final_position + 1
    ]

    cash = config.initial_capital_vnd
    positions: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    daily_records: list[dict[str, Any]] = []
    traded_gross = 0.0

    def stock_row(symbol: str, date: pd.Timestamp) -> pd.Series | None:
        try:
            row = price_lookup.loc[(symbol, date)]
        except KeyError:
            return None
        if isinstance(row, pd.DataFrame):
            raise RuntimeError(f"Duplicate OHLCV row for {symbol} on {date.date()}")
        return row

    def close_position(
        symbol: str,
        date: pd.Timestamp,
        base_price: float,
        reason: str,
    ) -> None:
        nonlocal cash, traded_gross
        position = positions.pop(symbol)
        fill_price = base_price * (1.0 - config.slippage_fraction_per_side)
        gross = position["shares"] * fill_price * config.price_scale_vnd
        commission = gross * config.commission_fraction_per_side
        sell_tax = gross * config.sell_tax_fraction
        proceeds = gross - commission - sell_tax
        cash += proceeds
        traded_gross += gross
        net_pnl = proceeds - position["entry_cash_outlay"]
        trades.append(
            {
                "symbol": symbol,
                "signal_date": position["signal_date"],
                "entry_date": position["entry_date"],
                "exit_date": date,
                "entry_price": position["entry_price"],
                "exit_price": fill_price,
                "shares": position["shares"],
                "entry_cash_outlay": position["entry_cash_outlay"],
                "exit_proceeds": proceeds,
                "net_pnl_vnd": net_pnl,
                "net_return": net_pnl / position["entry_cash_outlay"],
                "holding_sessions": calendar_position[date]
                - position["entry_calendar_position"]
                + 1,
                "exit_reason": reason,
                "entry_probability": position["entry_probability"],
                "predicted_strength": position["predicted_strength"],
                "ranking_score": position["ranking_score"],
            }
        )

    for date in simulation_calendar:
        date = pd.Timestamp(date)
        for symbol in list(positions):
            row = stock_row(symbol, date)
            if row is None:
                continue
            position = positions[symbol]
            position["last_close"] = float(row["close"])
            sessions_held = (
                calendar_position[date] - position["entry_calendar_position"] + 1
            )
            monitor = not (
                config.monitor_barriers_from_session_after_entry
                and date == position["entry_date"]
            )
            stop_hit = monitor and float(row["low"]) <= position["stop_price"]
            take_hit = monitor and float(row["high"]) >= position["take_price"]
            if stop_hit:
                close_position(symbol, date, position["stop_price"], "stop_loss")
            elif take_hit:
                close_position(symbol, date, position["take_price"], "take_profit")
            elif sessions_held >= config.maximum_holding_sessions:
                close_position(symbol, date, float(row["close"]), "maximum_holding")

        candidates = schedule.get(date, [])
        if candidates and len(positions) < config.max_positions:
            marked_value = sum(
                position["shares"]
                * position["last_close"]
                * config.price_scale_vnd
                for position in positions.values()
            )
            equity_before_entry = cash + marked_value
            target_value = equity_before_entry / config.max_positions
            for signal in candidates:
                if len(positions) >= config.max_positions:
                    break
                symbol = str(signal["symbol"])
                if symbol in positions:
                    skipped.append(
                        {
                            "symbol": symbol,
                            "signal_date": signal["date"],
                            "entry_date": date,
                            "reason": "already_in_portfolio",
                        }
                    )
                    continue
                row = stock_row(symbol, date)
                if row is None or float(row["open"]) <= 0 or float(row["volume"]) <= 0:
                    skipped.append(
                        {
                            "symbol": symbol,
                            "signal_date": signal["date"],
                            "entry_date": date,
                            "reason": "missing_or_invalid_entry_ohlcv",
                        }
                    )
                    continue
                fill_price = float(row["open"]) * (
                    1.0 + config.slippage_fraction_per_side
                )
                per_share_cost = fill_price * config.price_scale_vnd
                affordable_value = min(target_value, cash)
                desired_shares = int(
                    affordable_value
                    / (per_share_cost * (1.0 + config.commission_fraction_per_side))
                    / config.board_lot
                ) * config.board_lot
                capacity_shares = int(
                    float(row["volume"])
                    * config.maximum_volume_participation
                    / config.board_lot
                ) * config.board_lot
                shares = min(desired_shares, capacity_shares)
                if shares <= 0:
                    skipped.append(
                        {
                            "symbol": symbol,
                            "signal_date": signal["date"],
                            "entry_date": date,
                            "reason": "board_lot_or_liquidity_constraint",
                        }
                    )
                    continue
                gross = shares * per_share_cost
                commission = gross * config.commission_fraction_per_side
                cash_outlay = gross + commission
                if cash_outlay > cash:
                    continue
                cash -= cash_outlay
                traded_gross += gross
                positions[symbol] = {
                    "signal_date": pd.Timestamp(signal["date"]),
                    "entry_date": date,
                    "entry_calendar_position": calendar_position[date],
                    "entry_price": fill_price,
                    "shares": shares,
                    "entry_cash_outlay": cash_outlay,
                    "stop_price": fill_price * (1.0 - config.stop_loss_fraction),
                    "take_price": fill_price * (1.0 + config.take_profit_fraction),
                    "last_close": float(row["close"]),
                    "entry_probability": float(signal["p_entry_calibrated_temporal"]),
                    "predicted_strength": float(signal["p_strength"]),
                    "ranking_score": float(signal[config.score_column]),
                }

        if date == simulation_calendar[-1]:
            for symbol in list(positions):
                row = stock_row(symbol, date)
                price = (
                    float(row["close"])
                    if row is not None
                    else float(positions[symbol]["last_close"])
                )
                close_position(symbol, date, price, "end_of_backtest")

        invested = sum(
            position["shares"] * position["last_close"] * config.price_scale_vnd
            for position in positions.values()
        )
        equity = cash + invested
        daily_records.append(
            {
                "date": date,
                "cash_vnd": cash,
                "invested_value_vnd": invested,
                "equity_vnd": equity,
                "open_positions": len(positions),
                "exposure": invested / equity if equity > 0 else 0.0,
            }
        )

    equity_curve = pd.DataFrame(daily_records)
    trade_log = pd.DataFrame(trades)
    skipped_log = pd.DataFrame(skipped)
    if trade_log.empty:
        raise RuntimeError("Backtest produced no completed trades.")
    returns = equity_curve["equity_vnd"].pct_change().fillna(0.0)
    equity_curve["daily_return"] = returns
    excess_daily = returns - config.risk_free_rate / config.annualization_sessions
    annualized_volatility = float(returns.std(ddof=0) * np.sqrt(config.annualization_sessions))
    sharpe = (
        float(excess_daily.mean() / returns.std(ddof=0) * np.sqrt(config.annualization_sessions))
        if returns.std(ddof=0) > 0
        else float("nan")
    )
    years = max(len(equity_curve) / config.annualization_sessions, 1 / config.annualization_sessions)
    cumulative_return = float(
        equity_curve["equity_vnd"].iloc[-1] / config.initial_capital_vnd - 1.0
    )
    annualized_return = float((1.0 + cumulative_return) ** (1.0 / years) - 1.0)
    market_window = market.loc[
        market["date"].between(equity_curve["date"].min(), equity_curve["date"].max())
    ].sort_values("date")
    benchmark_return = float(
        market_window["close"].iloc[-1] / market_window["close"].iloc[0] - 1.0
    )
    positive_pnl = trade_log.loc[trade_log["net_pnl_vnd"] > 0, "net_pnl_vnd"].sum()
    negative_pnl = trade_log.loc[trade_log["net_pnl_vnd"] < 0, "net_pnl_vnd"].sum()
    metrics = {
        "strategy_version": config.strategy_version,
        "first_date": equity_curve["date"].min(),
        "last_date": equity_curve["date"].max(),
        "sessions": len(equity_curve),
        "initial_capital_vnd": config.initial_capital_vnd,
        "final_equity_vnd": float(equity_curve["equity_vnd"].iloc[-1]),
        "cumulative_return": cumulative_return,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": sharpe,
        "maximum_drawdown": _maximum_drawdown(equity_curve["equity_vnd"]),
        "benchmark_cumulative_return": benchmark_return,
        "excess_cumulative_return": cumulative_return - benchmark_return,
        "trades": len(trade_log),
        "win_rate": float((trade_log["net_pnl_vnd"] > 0).mean()),
        "profit_factor": (
            float(positive_pnl / abs(negative_pnl))
            if negative_pnl < 0
            else float("nan")
        ),
        "mean_trade_return": float(trade_log["net_return"].mean()),
        "median_trade_return": float(trade_log["net_return"].median()),
        "mean_holding_sessions": float(trade_log["holding_sessions"].mean()),
        "turnover_ratio": float(traded_gross / equity_curve["equity_vnd"].mean()),
        "mean_exposure": float(equity_curve["exposure"].mean()),
        "skipped_signals": len(skipped_log),
    }
    yearly_records: list[dict[str, Any]] = []
    for year, group in equity_curve.groupby(equity_curve["date"].dt.year, sort=True):
        yearly_trades = trade_log.loc[
            pd.to_datetime(trade_log["exit_date"]).dt.year.eq(year)
        ]
        yearly_records.append(
            {
                "year": int(year),
                "sessions": len(group),
                "return": float((1.0 + group["daily_return"]).prod() - 1.0),
                "maximum_drawdown": _maximum_drawdown(group["equity_vnd"]),
                "mean_exposure": float(group["exposure"].mean()),
                "trades": len(yearly_trades),
                "win_rate": (
                    float((yearly_trades["net_pnl_vnd"] > 0).mean())
                    if len(yearly_trades)
                    else float("nan")
                ),
            }
        )
    return metrics, equity_curve, trade_log, skipped_log, pd.DataFrame(yearly_records)
