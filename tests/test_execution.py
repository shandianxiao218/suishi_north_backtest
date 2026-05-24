from __future__ import annotations

import pytest

from suishi_north_backtest.execution import (
    ExecutionResult,
    SellResult,
    execute_buy,
    execute_sell,
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


# ---- 买入测试 ----


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


def test_buy_skipped_when_one_word_limit_up() -> None:
    """一字涨停（open==high==low==close==limit_up）无法买入。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=11.0,
        high=11.0,
        low=11.0,
        close=11.0,
        limit_up=11.0,
        cash=1_000_000.0,
        equity=1_000_000.0,
    )

    assert not result.executed
    assert "一字涨停" in result.skip_reason


def test_buy_allowed_when_not_one_word_limit_up() -> None:
    """非一字涨停（收盘价 != 涨停价）可以买入。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=11.0,
        high=11.5,
        low=10.8,
        close=11.2,
        limit_up=11.0,
        cash=1_000_000.0,
        equity=1_000_000.0,
    )

    assert result.executed


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
    assert result.shares > 0


def test_commission_and_slippage_included() -> None:
    """佣金计入成本，滑点作为审计字段。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=10.0,
        cash=1_000_000.0,
        equity=1_000_000.0,
    )

    assert result.executed
    assert result.commission > 0
    assert result.slippage > 0  # 审计字段仍有值
    assert result.total_cost == pytest.approx(result.commission, abs=0.01)


def test_cash_insufficient_reduces_or_skips() -> None:
    """现金不足时缩小或跳过。"""
    c = candidate(c_price=10.0)
    result = execute_buy(
        candidate=c,
        open_price=10.0,
        cash=500.0,
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
    """现金扣减 = shares * entry_price + commission（滑点已含在 entry_price 中）。"""
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
    assert result.cash_remaining == pytest.approx(
        initial_cash - result.shares * result.entry_price - result.total_cost, abs=0.01
    )


def test_execution_does_not_double_count_slippage() -> None:
    """滑点不得同时计入成交价和现金扣减。

    方案 A：成交价含滑点。
    cash -= shares * adjusted_entry_price + commission
    slippage 只作为审计字段，不额外扣现金。
    """
    c = candidate(c_price=10.0)
    initial_cash = 1_000_000.0
    result = execute_buy(
        candidate=c,
        open_price=10.0,
        cash=initial_cash,
        equity=initial_cash,
    )

    assert result.executed
    # entry_price = open_price * (1 + slippage_rate)，已含滑点
    assert result.entry_price > 10.0
    # total_cost 应只含佣金，不含额外滑点扣减
    assert result.total_cost == pytest.approx(result.commission, abs=0.01)
    # 现金扣减验证：cash = initial - shares * entry_price - commission
    expected_cash = initial_cash - result.shares * result.entry_price - result.commission
    assert result.cash_remaining == pytest.approx(expected_cash, abs=0.05)


# ---- 卖出测试 ----


def test_sell_at_t_plus_1_open() -> None:
    """T+1 开盘价卖出，成交价含滑点。"""
    result = execute_sell(
        symbol="000001",
        open_price=10.5,
        shares=1000,
    )

    assert result.executed
    assert result.sell_price == pytest.approx(10.5 * (1 - 0.0005), abs=0.001)


def test_sell_deferred_when_suspended() -> None:
    """停牌时卖出顺延。"""
    result = execute_sell(
        symbol="000001",
        open_price=None,
        shares=1000,
        is_suspended=True,
    )

    assert not result.executed
    assert result.deferred


def test_sell_deferred_when_one_word_limit_down() -> None:
    """一字跌停（open==high==low==close==limit_down）无法卖出，顺延。"""
    result = execute_sell(
        symbol="000001",
        open_price=9.0,
        high=9.0,
        low=9.0,
        close=9.0,
        limit_down=9.0,
        shares=1000,
    )

    assert not result.executed
    assert result.deferred
    assert "一字跌停" in result.skip_reason


def test_sell_allowed_when_not_one_word_limit_down() -> None:
    """非一字跌停可以卖出。"""
    result = execute_sell(
        symbol="000001",
        open_price=9.0,
        high=9.5,
        low=8.8,
        close=9.2,
        limit_down=9.0,
        shares=1000,
    )

    assert result.executed


def test_sell_includes_commission_stamp_tax_and_slippage() -> None:
    """卖出成本包含佣金、印花税，滑点作为审计字段。"""
    result = execute_sell(
        symbol="000001",
        open_price=10.0,
        shares=1000,
    )

    assert result.executed
    assert result.commission > 0
    assert result.stamp_tax > 0
    assert result.slippage > 0
    assert result.total_cost == pytest.approx(
        result.commission + result.stamp_tax, abs=0.01
    )


def test_sell_cash_proceeds() -> None:
    """卖出所得 = shares * sell_price - total_cost。"""
    result = execute_sell(
        symbol="000001",
        open_price=10.0,
        shares=1000,
    )

    assert result.executed
    expected = 1000 * result.sell_price - result.total_cost
    assert result.cash_proceeds == pytest.approx(expected, abs=0.05)
