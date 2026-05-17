from __future__ import annotations

from datetime import date

from suishi_north_backtest.data import MarketBar
from suishi_north_backtest.execution import (
    EntryOrder,
    ExecutionRules,
    execute_entry_order,
)


def execution_bar(
    day: date,
    *,
    open_price: float | None,
    is_suspended: bool = False,
) -> MarketBar:
    return MarketBar(
        symbol="000001.SZ",
        date=day,
        open=open_price,
        high=open_price,
        low=open_price,
        close=open_price or 10.0,
        volume=1_000_000 if open_price else 0,
        amount=10_000_000 if open_price else 0,
        adjust_factor=1.0,
        is_suspended=is_suspended,
        has_open_price=open_price is not None,
    )


def test_executes_t1_entry_with_position_sizing_costs_and_slippage() -> None:
    order = EntryOrder(
        symbol="000001.SZ",
        signal_date=date(2024, 1, 10),
        structural_stop=9.50,
    )

    result = execute_entry_order(
        order,
        execution_bar(date(2024, 1, 11), open_price=10.00),
        account_equity=1_000_000,
        rules=ExecutionRules(
            risk_per_trade=0.01,
            commission_rate=0.0003,
            buy_slippage_rate=0.0005,
            lot_size=100,
        ),
    )

    assert result.trade is not None
    trade = result.trade
    assert trade.symbol == "000001.SZ"
    assert trade.entry_date == date(2024, 1, 11)
    assert trade.entry_price == 10.005
    assert trade.quantity == 19_800
    assert trade.structural_stop == 9.50
    assert round(trade.gross_amount, 2) == 198_099.00
    assert round(trade.commission, 2) == 59.43
    assert round(trade.slippage_cost, 2) == 99.00
    assert round(trade.total_entry_cost, 2) == 158.43
    assert result.skipped_reason is None


def test_skips_entry_when_t1_is_suspended_or_has_no_open_price() -> None:
    order = EntryOrder(
        symbol="000001.SZ",
        signal_date=date(2024, 1, 10),
        structural_stop=9.50,
    )

    suspended_result = execute_entry_order(
        order,
        execution_bar(date(2024, 1, 11), open_price=None, is_suspended=True),
        account_equity=1_000_000,
    )

    assert suspended_result.trade is None
    assert suspended_result.skipped_reason == "T+1 停牌或无开盘价"


def test_skips_entry_when_t1_is_locked_limit_up() -> None:
    order = EntryOrder(
        symbol="000001.SZ",
        signal_date=date(2024, 1, 10),
        structural_stop=9.50,
    )

    result = execute_entry_order(
        order,
        execution_bar(date(2024, 1, 11), open_price=10.00),
        account_equity=1_000_000,
        is_locked_limit_up=True,
    )

    assert result.trade is None
    assert result.skipped_reason == "T+1 一字涨停无法买入"


def test_skips_entry_when_stop_price_is_not_below_entry_price() -> None:
    order = EntryOrder(
        symbol="000001.SZ",
        signal_date=date(2024, 1, 10),
        structural_stop=10.10,
    )

    result = execute_entry_order(
        order,
        execution_bar(date(2024, 1, 11), open_price=10.00),
        account_equity=1_000_000,
    )

    assert result.trade is None
    assert result.skipped_reason == "止损价不低于买入价，无法计算仓位"


def test_skips_entry_when_position_size_rounds_to_zero_lot() -> None:
    order = EntryOrder(
        symbol="000001.SZ",
        signal_date=date(2024, 1, 10),
        structural_stop=9.50,
    )

    result = execute_entry_order(
        order,
        execution_bar(date(2024, 1, 11), open_price=10.00),
        account_equity=1_000,
    )

    assert result.trade is None
    assert result.skipped_reason == "仓位不足 1 手，跳过买入"
