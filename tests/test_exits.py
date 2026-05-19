from __future__ import annotations

import pytest

from suishi_north_backtest.execution import execute_sell
from suishi_north_backtest.exits import (
    ExitSignal,
    ExitType,
    check_exit,
    detect_exit_signal,
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
    limit_up: float | None = None,
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
        limit_up=limit_up,
        limit_down=limit_down,
        is_suspended=is_suspended,
    )


# ---- 信号检测测试 ----


def test_structure_stop_loss_below_c() -> None:
    """跌破 C 点低点触发结构止损。"""
    bars = [bar("2024-01-15", close=9.4, low=9.3)]
    signal = detect_exit_signal(
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
    signal = detect_exit_signal(
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
    bars = [bar("2024-01-15", close=10.4)]
    signal = detect_exit_signal(
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
    bars = [bar("2024-01-20", close=10.4)]
    signal = detect_exit_signal(
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
    signal = detect_exit_signal(
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
    signal = detect_exit_signal(
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
    bars = [bar("2024-01-15", close=9.4)]
    signal = detect_exit_signal(
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
    signal = detect_exit_signal(
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


def test_one_word_limit_down_defers_exit() -> None:
    """一字跌停（open==high==low==close==limit_down）无法卖出，应返回顺延信号。"""
    bars = [
        bar(
            "2024-01-15",
            close=9.5,
            open=9.5,
            high=9.5,
            low=9.5,
            limit_down=9.5,
        )
    ]
    signal = detect_exit_signal(
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


def test_not_limit_down_when_close_above_limit_down() -> None:
    """收盘价等于跌停价但不是一字跌停（有日内波动），不应顺延。"""
    bars = [
        bar(
            "2024-01-15",
            close=9.5,
            open=9.8,
            high=10.0,
            low=9.4,
            limit_down=9.5,
        )
    ]
    signal = detect_exit_signal(
        bars=bars,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=10.0,
        entry_date="2024-01-10",
        current_date="2024-01-15",
        trading_days_since_entry=3,
    )

    assert signal is not None
    assert not signal.deferred


def test_exit_signal_has_required_fields() -> None:
    bars = [bar("2024-01-12", close=9.9)]
    signal = detect_exit_signal(
        bars=bars,
        entry_price=10.5,
        c_price=9.0,
        highest_close_since_entry=10.8,
        entry_date="2024-01-10",
        current_date="2024-01-12",
    )

    assert signal is not None
    assert hasattr(signal, "exit_type")
    assert hasattr(signal, "signal_date")
    assert hasattr(signal, "reason")
    assert hasattr(signal, "deferred")


def test_exit_signal_detected_on_t_close_but_sell_executes_on_t_plus_1_open() -> None:
    """T 日收盘检测退出信号，T+1 开盘执行卖出。

    信号检测函数不应返回实际卖出价。
    卖出执行通过 execute_sell() 在 T+1 开盘价执行。
    """
    # T 日 bar：触发结构止损
    t_bar = bar("2024-01-15", close=9.4, low=9.3)
    signal = detect_exit_signal(
        bars=[t_bar],
        entry_price=10.5,
        c_price=9.5,
        highest_close_since_entry=10.8,
        entry_date="2024-01-10",
        current_date="2024-01-15",
    )

    assert signal is not None
    assert signal.exit_type == ExitType.STRUCTURE_STOP
    assert signal.signal_date == "2024-01-15"
    # 信号对象不应包含卖出价
    assert not hasattr(signal, "exit_price") or getattr(signal, "exit_price", None) is None

    # T+1 开盘执行卖出
    sell_result = execute_sell(
        symbol="000001",
        open_price=9.3,
        shares=1000,
    )

    assert sell_result.executed
    assert sell_result.sell_price is not None
    assert sell_result.sell_price < 9.3  # 含滑点


def test_check_exit_is_alias_for_detect_exit_signal() -> None:
    """check_exit 是 detect_exit_signal 的别名。"""
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
