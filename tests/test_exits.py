from __future__ import annotations

import pytest

from suishi_north_backtest.exits import (
    ExitSignal,
    ExitType,
    SellResult,
    check_exit,
    detect_exit_signal,
    execute_sell,
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


# ---- 信号检测测试 ----


def test_structure_stop_loss_below_c() -> None:
    """最低价跌破 C 点触发结构止损。"""
    current = bar("2024-01-15", close=9.6, low=9.3)
    signal = detect_exit_signal(
        current_bar=current,
        entry_price=10.5,
        c_price=9.5,
        highest_close_since_entry=10.8,
        trading_days_since_entry=3,
    )

    assert signal is not None
    assert signal.exit_type == ExitType.STRUCTURE_STOP
    assert signal.signal_date == "2024-01-15"
    assert "最低" in signal.reason


def test_emergency_stop_loss_5pct() -> None:
    """从买入价下跌 5% 触发应急止损。"""
    current = bar("2024-01-12", close=9.9)
    signal = detect_exit_signal(
        current_bar=current,
        entry_price=10.5,
        c_price=9.0,
        highest_close_since_entry=10.8,
        trading_days_since_entry=1,
    )

    assert signal is not None
    assert signal.exit_type == ExitType.EMERGENCY_STOP


def test_time_stop_no_profit_in_3_days() -> None:
    """买入后 3 个交易日无浮盈触发时间止损。"""
    current = bar("2024-01-15", close=10.4)
    signal = detect_exit_signal(
        current_bar=current,
        entry_price=10.5,
        c_price=9.0,
        highest_close_since_entry=10.5,
        trading_days_since_entry=3,
    )

    assert signal is not None
    assert signal.exit_type == ExitType.TIME_STOP


def test_trend_exit_8pct_from_high() -> None:
    """从最高收盘价回撤 8% 触发趋势退出。"""
    current = bar("2024-01-20", close=10.4)
    signal = detect_exit_signal(
        current_bar=current,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=11.4,
        trading_days_since_entry=5,
    )

    assert signal is not None
    assert signal.exit_type == ExitType.TREND_EXIT


def test_hard_max_holding_30_days() -> None:
    """硬最大持仓 30 个交易日触发。"""
    current = bar("2024-02-20", close=11.0)
    signal = detect_exit_signal(
        current_bar=current,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=11.5,
        trading_days_since_entry=30,
    )

    assert signal is not None
    assert signal.exit_type == ExitType.MAX_HOLDING


def test_no_exit_when_profitable() -> None:
    """持仓盈利且无触发条件时不退出。"""
    current = bar("2024-01-15", close=11.0)
    signal = detect_exit_signal(
        current_bar=current,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=11.0,
        trading_days_since_entry=2,
    )

    assert signal is None


def test_stop_loss_priority_over_trend_exit() -> None:
    """止损优先于趋势退出。"""
    current = bar("2024-01-15", close=9.4, low=9.3)
    signal = detect_exit_signal(
        current_bar=current,
        entry_price=10.0,
        c_price=9.5,
        highest_close_since_entry=11.0,
        trading_days_since_entry=3,
    )

    assert signal is not None
    assert signal.exit_type == ExitType.STRUCTURE_STOP


# ---- T+1 卖出执行测试 ----


def test_execute_sell_at_t_plus_1_open() -> None:
    """T+1 开盘价卖出，含滑点。"""
    signal = ExitSignal(exit_type=ExitType.EMERGENCY_STOP, signal_date="2024-01-12", reason="test")
    result = execute_sell(
        signal=signal,
        symbol="000001",
        open_price=10.0,
        cash=500000.0,
        shares=1000,
    )

    assert result.executed
    assert result.exit_price == pytest.approx(10.0 * (1 - 0.0005), abs=0.001)
    assert result.commission > 0
    assert result.cash_remaining > 500000.0  # 卖出后现金增加


def test_execute_sell_deferred_when_suspended() -> None:
    """停牌无法卖出，顺延。"""
    signal = ExitSignal(exit_type=ExitType.TIME_STOP, signal_date="2024-01-15", reason="test")
    result = execute_sell(
        signal=signal,
        symbol="000001",
        open_price=None,
        cash=500000.0,
        shares=1000,
        is_suspended=True,
    )

    assert not result.executed
    assert result.deferred


def test_execute_sell_deferred_when_limit_down() -> None:
    """一字跌停无法卖出，顺延。"""
    signal = ExitSignal(exit_type=ExitType.TIME_STOP, signal_date="2024-01-15", reason="test")
    result = execute_sell(
        signal=signal,
        symbol="000001",
        open_price=9.5,
        cash=500000.0,
        shares=1000,
        limit_down=9.5,
    )

    assert not result.executed
    assert result.deferred


def test_execute_sell_includes_stamp_tax() -> None:
    """卖出含印花税。"""
    signal = ExitSignal(exit_type=ExitType.TREND_EXIT, signal_date="2024-01-20", reason="test")
    result = execute_sell(
        signal=signal,
        symbol="000001",
        open_price=10.0,
        cash=500000.0,
        shares=1000,
    )

    assert result.executed
    assert result.commission > 0
    # total_cost should include commission + stamp_tax + slippage
    assert result.total_cost > result.commission


def test_sell_result_has_required_fields() -> None:
    signal = ExitSignal(exit_type=ExitType.EMERGENCY_STOP, signal_date="2024-01-12", reason="test")
    result = execute_sell(
        signal=signal,
        symbol="000001",
        open_price=10.0,
        cash=500000.0,
        shares=1000,
    )

    assert hasattr(result, "executed")
    assert hasattr(result, "exit_price")
    assert hasattr(result, "exit_date")
    assert hasattr(result, "commission")
    assert hasattr(result, "deferred")


# ---- 向后兼容 wrapper ----


def test_check_exit_backward_compat() -> None:
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
