from __future__ import annotations

from datetime import date

from suishi_north_backtest.data import MarketBar
from suishi_north_backtest.exit import (
    ExitRules,
    ExitSignal,
    Position,
    execute_exit_signal,
    evaluate_exit_signal,
)


def bar(day: date, close: float) -> MarketBar:
    return MarketBar(
        symbol="000001.SZ",
        date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000_000,
        amount=10_000_000,
        adjust_factor=1.0,
        is_suspended=False,
        has_open_price=True,
    )


def position() -> Position:
    return Position(
        symbol="000001.SZ",
        entry_date=date(2024, 1, 1),
        entry_price=10.0,
        quantity=10_000,
        structural_stop=9.2,
        highest_close=11.0,
        holding_days=4,
        has_floating_profit=False,
    )


def test_exit_signal_uses_conservative_priority_when_multiple_rules_trigger() -> None:
    signal = evaluate_exit_signal(
        position(),
        bar(date(2024, 1, 5), close=9.0),
        rules=ExitRules(
            emergency_stop_pct=0.05,
            trend_drawdown_pct=0.08,
            time_stop_days=3,
            max_holding_days=30,
        ),
    )

    assert signal is not None
    assert signal.reason == "结构止损"
    assert signal.signal_date == date(2024, 1, 5)


def test_exit_signal_supports_time_trend_and_max_holding_rules() -> None:
    time_signal = evaluate_exit_signal(
        position(),
        bar(date(2024, 1, 5), close=10.0),
        rules=ExitRules(time_stop_days=3),
    )
    assert time_signal is not None
    assert time_signal.reason == "时间止损"

    trend_signal = evaluate_exit_signal(
        Position(
            symbol="000001.SZ",
            entry_date=date(2024, 1, 1),
            entry_price=10.0,
            quantity=10_000,
            structural_stop=8.0,
            highest_close=12.0,
            holding_days=10,
            has_floating_profit=True,
        ),
        bar(date(2024, 1, 11), close=11.0),
        rules=ExitRules(trend_drawdown_pct=0.08),
    )
    assert trend_signal is not None
    assert trend_signal.reason == "趋势退出"

    max_holding_signal = evaluate_exit_signal(
        Position(
            symbol="000001.SZ",
            entry_date=date(2024, 1, 1),
            entry_price=10.0,
            quantity=10_000,
            structural_stop=8.0,
            highest_close=10.5,
            holding_days=30,
            has_floating_profit=True,
        ),
        bar(date(2024, 2, 15), close=10.4),
        rules=ExitRules(max_holding_days=30),
    )
    assert max_holding_signal is not None
    assert max_holding_signal.reason == "硬最大持仓"


def test_executes_exit_on_next_open_with_sell_costs_and_slippage() -> None:
    result = execute_exit_signal(
        ExitSignal(
            symbol="000001.SZ",
            signal_date=date(2024, 1, 5),
            reason="趋势退出",
        ),
        position(),
        bar(date(2024, 1, 6), close=10.0),
    )

    assert result.trade is not None
    trade = result.trade
    assert trade.exit_date == date(2024, 1, 6)
    assert trade.exit_price == 9.995
    assert trade.reason == "趋势退出"
    assert round(trade.gross_amount, 2) == 99_950.00
    assert round(trade.commission, 2) == 29.98
    assert round(trade.stamp_tax, 2) == 49.97
    assert round(trade.slippage_cost, 2) == 50.00
    assert round(trade.total_exit_cost, 2) == 129.96
    assert result.deferred_reason is None


def test_defers_exit_when_next_open_is_not_executable() -> None:
    result = execute_exit_signal(
        ExitSignal(
            symbol="000001.SZ",
            signal_date=date(2024, 1, 5),
            reason="结构止损",
        ),
        position(),
        bar(date(2024, 1, 6), close=10.0),
        is_locked_limit_down=True,
    )

    assert result.trade is None
    assert result.deferred_reason == "T+1 停牌或一字跌停无法卖出，顺延"
