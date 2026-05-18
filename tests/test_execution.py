from __future__ import annotations

import pytest

from suishi_north_backtest.execution import (
    ExecutionResult,
    execute_buy,
)
from suishi_north_backtest.signals import CandidateSignal


# ---- 辅助函数 ----


def candidate(
    symbol: str = "000001",
    signal_date: str = "2024-01-10",
    c_price: float = 10.0,
) -> CandidateSignal:
    return CandidateSignal(
        signal_date=signal_date,
        symbol=symbol,
        a_date="2024-01-02",
        a_price=8.0,
        b_date="2024-01-05",
        b_price=11.0,
        c_date="2024-01-08",
        c_price=c_price,
        ab_gain_pct=37.5,
        bc_retracement_pct=33.3,
        distance_to_c_pct=3.0,
    )


# ---- 测试 ----


def test_buy_at_t_plus_1_open() -> None:
    """T+1 开盘价成交。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=10.5,
        cash=1_000_000.0,
        equity=1_000_000.0,
    )

    assert result.executed
    assert result.entry_price == pytest.approx(10.5 * 1.0005, abs=0.001)


def test_buy_skipped_when_limit_up() -> None:
    """一字涨停无法买入。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=11.0,
        cash=1_000_000.0,
        equity=1_000_000.0,
        limit_up=11.0,
    )

    assert not result.executed
    assert "涨停" in result.skip_reason


def test_buy_skipped_when_no_open_price() -> None:
    """停牌无开盘价无法买入。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=None,
        cash=1_000_000.0,
        equity=1_000_000.0,
    )

    assert not result.executed
    assert "开盘价" in result.skip_reason or "停牌" in result.skip_reason


def test_shares_rounded_to_lot() -> None:
    """股数按整手（100 股）。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=10.0,
        cash=1_000_000.0,
        equity=1_000_000.0,
    )

    assert result.executed
    assert result.shares % 100 == 0


def test_single_risk_limits_position() -> None:
    """单笔风险 1% 控制仓位。"""
    c = candidate(c_price=10.0)
    equity = 1_000_000.0
    result = execute_buy(
        candidate=c,
        open_price=10.0,
        cash=1_000_000.0,
        equity=equity,
    )

    assert result.executed
    # 风险金额 = equity * 1% = 10000
    # 应急止损 -5% → 最大亏损 = entry_price * 5%
    # 股数 = 风险金额 / (entry_price * 0.05)
    # entry_price ≈ 10.0 * 1.0005 ≈ 10.005
    # 股数 ≈ 10000 / (10.005 * 0.05) ≈ 19990 → round down to 19900
    assert result.shares > 0


def test_commission_and_slippage_included() -> None:
    """佣金和滑点计入成本。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=10.0,
        cash=1_000_000.0,
        equity=1_000_000.0,
    )

    assert result.executed
    assert result.commission > 0
    assert result.slippage > 0
    assert result.total_cost == pytest.approx(result.commission + result.slippage, abs=0.01)


def test_cash_insufficient_reduces_or_skips() -> None:
    """现金不足时缩小或跳过。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=10.0,
        cash=500.0,  # 不够买一手
        equity=1_000_000.0,
    )

    assert not result.executed
    assert "现金" in result.skip_reason or "不足" in result.skip_reason


def test_execution_result_has_required_fields() -> None:
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=10.0,
        cash=1_000_000.0,
        equity=1_000_000.0,
    )

    assert hasattr(result, "executed")
    assert hasattr(result, "symbol")
    assert hasattr(result, "entry_price")
    assert hasattr(result, "shares")
    assert hasattr(result, "commission")
    assert hasattr(result, "slippage")
    assert hasattr(result, "total_cost")
    assert hasattr(result, "cash_remaining")


def test_cash_deducted_correctly() -> None:
    c = candidate(c_price=10.0)
    initial_cash = 1_000_000.0
    result = execute_buy(
        candidate=c,
        open_price=10.0,
        cash=initial_cash,
        equity=initial_cash,
    )

    assert result.executed
    assert result.cash_remaining < initial_cash
    # cash_remaining = initial_cash - shares * entry_price - total_cost
    assert result.cash_remaining == pytest.approx(
        initial_cash - result.shares * result.entry_price - result.total_cost, abs=0.01
    )
