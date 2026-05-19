from __future__ import annotations

import pytest

from suishi_north_backtest.exits import (
    ExitSignal,
    ExitType,
    check_exit,
)
from suishi_north_backtest.market_data import StockDaily


# ---- 辅助函数 ----


def bar(
    trade_date: str,
    close: float,
    high: float | None = None,
    low: float | None = None,
    open: float | None = None,
    is_suspended: bool = False,
    limit_down: float | None = None,
) -> StockDaily:
    return StockDaily(
        trade_date=trade_date,
        symbol="000001",
        open=open if open is not None else close,
        high=high or close * 1.01,
        low=low or close * 0.99,
        close=close,
        volume=100000.0,
        amount=1000000.0,
        is_st=False,
        limit_up=None,
        limit_down=limit_down,
        is_suspended=is_suspended,
    )


# ---- 测试 ----


def test_structure_stop_loss_below_c() -> None:
    """跌破 C 点低点触发结构止损。"""
    bars = [bar("2024-01-15", close=9.4, low=9.3)]
    signal = check_exit(
        bars=bars,
        entry_price=10.5,
        c_price=9.5,
        highest_close_since_entry=10.8,
        entry_date="2024-01-10",
        current_date="2024-01-15",
    )

    assert signal is not None
    assert signal.exit_type == ExitType.STRUCTURE_STOP


def test_emergency_stop_loss_5pct() -> None:
    """从买入价下跌 5% 触发应急止损。"""
    bars = [bar("2024-01-12", close=9.9)]
    signal = check_exit(
        bars=bars,
        entry_price=10.5,
        c_price=9.0,
        highest_close_since_entry=10.8,
        entry_date="2024-01-10",
        current_date="2024-01-12",
    )

    assert signal is not None
    assert signal.exit_type == ExitType.EMERGENCY_STOP


def test_time_stop_no_profit_in_3_days() -> None:
    """买入后 3 个交易日无浮盈触发时间止损。"""
    bars = [bar("2024-01-15", close=10.4)]  # entry_date + 3 trading days
    signal = check_exit(
        bars=bars,
        entry_price=10.5,
        c_price=9.0,
        highest_close_since_entry=10.5,
        entry_date="2024-01-10",
        current_date="2024-01-15",
        trading_days_since_entry=3,
    )

    assert signal is not None
    assert signal.exit_type == ExitType.TIME_STOP


def test_trend_exit_8pct_from_high() -> None:
    """从最高收盘价回撤 8% 触发趋势退出。"""
    bars = [bar("2024-01-20", close=10.4)]  # 11.4 * 0.92 ≈ 10.49, 10.4 < 10.49
    signal = check_exit(
        bars=bars,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=11.4,
        entry_date="2024-01-10",
        current_date="2024-01-20",
    )

    assert signal is not None
    assert signal.exit_type == ExitType.TREND_EXIT


def test_hard_max_holding_30_days() -> None:
    """硬最大持仓 30 个交易日触发。"""
    bars = [bar("2024-02-20", close=11.0)]
    signal = check_exit(
        bars=bars,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=11.5,
        entry_date="2024-01-10",
        current_date="2024-02-20",
        trading_days_since_entry=30,
    )

    assert signal is not None
    assert signal.exit_type == ExitType.MAX_HOLDING


def test_no_exit_when_profitable() -> None:
    """持仓盈利且无触发条件时不退出。"""
    bars = [bar("2024-01-15", close=11.0)]
    signal = check_exit(
        bars=bars,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=11.0,
        entry_date="2024-01-10",
        current_date="2024-01-15",
        trading_days_since_entry=2,
    )

    assert signal is None


def test_stop_loss_priority_over_trend_exit() -> None:
    """止损优先于趋势退出。"""
    bars = [bar("2024-01-15", close=9.4)]  # 触发结构止损和趋势退出
    signal = check_exit(
        bars=bars,
        entry_price=10.0,
        c_price=9.5,
        highest_close_since_entry=11.0,
        entry_date="2024-01-10",
        current_date="2024-01-15",
    )

    assert signal is not None
    assert signal.exit_type == ExitType.STRUCTURE_STOP


def test_suspended_defers_exit() -> None:
    """停牌时无法退出，应返回顺延信号。"""
    bars = [bar("2024-01-15", close=0, is_suspended=True)]
    signal = check_exit(
        bars=bars,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=10.0,
        entry_date="2024-01-10",
        current_date="2024-01-15",
        trading_days_since_entry=3,
    )

    assert signal is not None
    assert signal.deferred


def test_limit_down_defers_exit() -> None:
    """一字跌停时无法卖出，应返回顺延信号。"""
    bars = [bar("2024-01-15", close=9.5, limit_down=9.5)]
    signal = check_exit(
        bars=bars,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=10.0,
        entry_date="2024-01-10",
        current_date="2024-01-15",
        trading_days_since_entry=3,
    )

    assert signal is not None
    assert signal.deferred


def test_exit_signal_has_required_fields() -> None:
    bars = [bar("2024-01-12", close=9.9)]
    signal = check_exit(
        bars=bars,
        entry_price=10.5,
        c_price=9.0,
        highest_close_since_entry=10.8,
        entry_date="2024-01-10",
        current_date="2024-01-12",
    )

    assert signal is not None
    assert hasattr(signal, "exit_type")
    assert hasattr(signal, "exit_date")
    assert hasattr(signal, "exit_price")
    assert hasattr(signal, "reason")
    assert hasattr(signal, "deferred")
