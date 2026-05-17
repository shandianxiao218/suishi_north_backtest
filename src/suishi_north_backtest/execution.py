from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from suishi_north_backtest.data import MarketBar


@dataclass(frozen=True)
class EntryOrder:
    """T 日收盘后生成的待买入订单。"""

    symbol: str
    signal_date: date
    structural_stop: float


@dataclass(frozen=True)
class ExecutionRules:
    """MVP-1 成交、仓位和成本参数。"""

    risk_per_trade: float = 0.01
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.0005
    buy_slippage_rate: float = 0.0005
    sell_slippage_rate: float = 0.0005
    lot_size: int = 100


@dataclass(frozen=True)
class EntryTrade:
    """买入成交结果。"""

    symbol: str
    signal_date: date
    entry_date: date
    entry_price: float
    quantity: int
    structural_stop: float
    gross_amount: float
    commission: float
    slippage_cost: float
    total_entry_cost: float


@dataclass(frozen=True)
class EntryExecutionResult:
    """买入执行结果。"""

    trade: EntryTrade | None
    skipped_reason: str | None


def execute_entry_order(
    order: EntryOrder,
    execution_bar: MarketBar,
    *,
    account_equity: float,
    is_locked_limit_up: bool = False,
    rules: ExecutionRules = ExecutionRules(),
) -> EntryExecutionResult:
    """按 T+1 开盘规则执行买入订单。"""

    if execution_bar.is_suspended or not execution_bar.has_open_price:
        return EntryExecutionResult(trade=None, skipped_reason="T+1 停牌或无开盘价")
    if is_locked_limit_up:
        return EntryExecutionResult(trade=None, skipped_reason="T+1 一字涨停无法买入")

    open_price = execution_bar.open
    if open_price is None:
        return EntryExecutionResult(trade=None, skipped_reason="T+1 停牌或无开盘价")

    entry_price = round(open_price * (1 + rules.buy_slippage_rate), 6)
    if order.structural_stop >= entry_price:
        return EntryExecutionResult(
            trade=None,
            skipped_reason="止损价不低于买入价，无法计算仓位",
        )
    quantity = _position_size(
        account_equity=account_equity,
        entry_price=entry_price,
        stop_price=order.structural_stop,
        rules=rules,
    )
    if quantity <= 0:
        return EntryExecutionResult(trade=None, skipped_reason="仓位不足 1 手，跳过买入")
    gross_amount = entry_price * quantity
    commission = gross_amount * rules.commission_rate
    slippage_cost = open_price * rules.buy_slippage_rate * quantity
    return EntryExecutionResult(
        trade=EntryTrade(
            symbol=order.symbol,
            signal_date=order.signal_date,
            entry_date=execution_bar.date,
            entry_price=entry_price,
            quantity=quantity,
            structural_stop=order.structural_stop,
            gross_amount=gross_amount,
            commission=commission,
            slippage_cost=slippage_cost,
            total_entry_cost=commission + slippage_cost,
        ),
        skipped_reason=None,
    )


def _position_size(
    *,
    account_equity: float,
    entry_price: float,
    stop_price: float,
    rules: ExecutionRules,
) -> int:
    risk_budget = account_equity * rules.risk_per_trade
    per_share_risk = entry_price - stop_price
    raw_quantity = int(risk_budget / per_share_risk)
    return raw_quantity // rules.lot_size * rules.lot_size
