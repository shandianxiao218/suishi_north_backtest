from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from suishi_north_backtest.data import MarketBar
from suishi_north_backtest.signals import CandidateSignal

if TYPE_CHECKING:
    from suishi_north_backtest.parameters import StrategyParameters


@dataclass(frozen=True)
class EntryOrder:
    """T 日收盘后生成的待买入订单，保留给早期执行 API 使用。"""

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
    """买入成交结果，保留给早期执行 API 使用。"""

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
    """买入执行结果，保留给早期执行 API 使用。"""

    trade: EntryTrade | None
    skipped_reason: str | None


@dataclass
class ExecutionResult:
    executed: bool
    symbol: str
    entry_price: float | None = None
    shares: int = 0
    commission: float = 0.0
    slippage: float = 0.0
    total_cost: float = 0.0
    cash_remaining: float = 0.0
    skip_reason: str = ""


DEFAULT_RISK_PCT = 0.01
DEFAULT_STOP_LOSS_PCT = 0.05
DEFAULT_COMMISSION_RATE = 0.0003
DEFAULT_SLIPPAGE_RATE = 0.0005
LOT_SIZE = 100


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


def _is_one_word_limit_up(
    open_price: float,
    high: float,
    low: float,
    close: float,
    limit_up: float,
) -> bool:
    return (
        open_price == high == low == close == limit_up
    )


def execute_buy(
    candidate: CandidateSignal,
    open_price: float | None,
    cash: float,
    equity: float,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
    limit_up: float | None = None,
    risk_pct: float = DEFAULT_RISK_PCT,
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
    commission_rate: float = DEFAULT_COMMISSION_RATE,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
    parameters: StrategyParameters | None = None,
) -> ExecutionResult:
    if parameters is not None:
        risk_pct = parameters.risk_pct
        stop_loss_pct = parameters.stop_loss_pct
        commission_rate = parameters.commission_rate
        slippage_rate = parameters.buy_slippage_rate
        lot_size = parameters.lot_size
    else:
        lot_size = LOT_SIZE

    symbol = candidate.symbol

    if open_price is None:
        return ExecutionResult(
            executed=False,
            symbol=symbol,
            cash_remaining=cash,
            skip_reason=f"停牌，无开盘价：{symbol}",
        )

    # 一字涨停判断：open == high == low == close == limit_up
    if (
        limit_up is not None
        and high is not None
        and low is not None
        and close is not None
    ):
        if _is_one_word_limit_up(open_price, high, low, close, limit_up):
            return ExecutionResult(
                executed=False,
                symbol=symbol,
                cash_remaining=cash,
                skip_reason=(
                    f"一字涨停无法买入：{symbol}，"
                    f"开盘 {open_price} == 最高 {high} == 最低 {low} == 收盘 {close} == 涨停价 {limit_up}"
                ),
            )

    # 方案 A：成交价含滑点
    # slippage 只作为审计字段，不再额外扣现金
    entry_price = open_price * (1 + slippage_rate)
    slippage_audit = open_price * slippage_rate  # 审计用：每股滑点金额

    risk_amount = equity * risk_pct
    per_share_risk = entry_price * stop_loss_pct
    if per_share_risk == 0:
        return ExecutionResult(
            executed=False,
            symbol=symbol,
            cash_remaining=cash,
            skip_reason=f"无法计算仓位：{symbol}，entry_price 为零",
        )

    raw_shares = risk_amount / per_share_risk
    shares = int(raw_shares // lot_size) * lot_size

    if shares == 0:
        return ExecutionResult(
            executed=False,
            symbol=symbol,
            cash_remaining=cash,
            skip_reason=f"现金不足，无法买入一手：{symbol}",
        )

    # 成本 = shares * entry_price（含滑点）
    cost = shares * entry_price
    while cost > cash and shares >= lot_size:
        shares -= lot_size
        cost = shares * entry_price

    if shares == 0:
        return ExecutionResult(
            executed=False,
            symbol=symbol,
            cash_remaining=cash,
            skip_reason=f"现金不足，无法买入：{symbol}",
        )

    # 佣金基于成交金额（含滑点的成交价）
    commission = cost * commission_rate
    # 滑点审计字段
    slippage = shares * slippage_audit
    total_cost = commission  # 滑点已计入 entry_price，不重复扣

    # 现金 = cash - shares * entry_price - commission
    cash_remaining = cash - cost - total_cost

    if cash_remaining < 0:
        while cash_remaining < 0 and shares >= lot_size:
            shares -= lot_size
            cost = shares * entry_price
            commission = cost * commission_rate
            slippage = shares * slippage_audit
            total_cost = commission
            cash_remaining = cash - cost - total_cost

        if shares == 0:
            return ExecutionResult(
                executed=False,
                symbol=symbol,
                cash_remaining=cash,
                skip_reason=f"现金不足（含费用）：{symbol}",
            )

    return ExecutionResult(
        executed=True,
        symbol=symbol,
        entry_price=round(entry_price, 4),
        shares=shares,
        commission=round(commission, 2),
        slippage=round(slippage, 2),
        total_cost=round(total_cost, 2),
        cash_remaining=round(cash_remaining, 2),
    )


@dataclass
class SellResult:
    executed: bool
    symbol: str
    sell_price: float | None = None
    shares: int = 0
    commission: float = 0.0
    stamp_tax: float = 0.0
    slippage: float = 0.0
    total_cost: float = 0.0
    cash_proceeds: float = 0.0
    deferred: bool = False
    skip_reason: str = ""


DEFAULT_STAMP_TAX_RATE = 0.0005


def _is_one_word_limit_down(
    open_price: float,
    high: float,
    low: float,
    close: float,
    limit_down: float,
) -> bool:
    return (
        open_price == high == low == close == limit_down
    )


def execute_sell(
    symbol: str,
    open_price: float | None,
    shares: int,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
    limit_down: float | None = None,
    is_suspended: bool = False,
    commission_rate: float = DEFAULT_COMMISSION_RATE,
    stamp_tax_rate: float = DEFAULT_STAMP_TAX_RATE,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
    parameters: StrategyParameters | None = None,
) -> SellResult:
    if parameters is not None:
        commission_rate = parameters.commission_rate
        stamp_tax_rate = parameters.stamp_tax_rate
        slippage_rate = parameters.sell_slippage_rate

    if is_suspended or open_price is None:
        return SellResult(
            executed=False,
            symbol=symbol,
            shares=shares,
            deferred=True,
            skip_reason=f"停牌，无法卖出：{symbol}",
        )

    # 一字跌停判断：open == high == low == close == limit_down
    if (
        limit_down is not None
        and high is not None
        and low is not None
        and close is not None
    ):
        if _is_one_word_limit_down(open_price, high, low, close, limit_down):
            return SellResult(
                executed=False,
                symbol=symbol,
                shares=shares,
                deferred=True,
                skip_reason=(
                    f"一字跌停无法卖出：{symbol}，"
                    f"开盘 {open_price} == 最高 {high} == 最低 {low} == 收盘 {close} == 跌停价 {limit_down}"
                ),
            )

    # 方案 A：卖出成交价含滑点
    sell_price = open_price * (1 - slippage_rate)
    slippage_audit = open_price * slippage_rate

    gross_proceeds = shares * sell_price
    commission = gross_proceeds * commission_rate
    stamp_tax = gross_proceeds * stamp_tax_rate
    slippage = shares * slippage_audit
    total_cost = commission + stamp_tax  # 滑点已计入 sell_price

    cash_proceeds = gross_proceeds - total_cost

    return SellResult(
        executed=True,
        symbol=symbol,
        sell_price=round(sell_price, 4),
        shares=shares,
        commission=round(commission, 2),
        stamp_tax=round(stamp_tax, 2),
        slippage=round(slippage, 2),
        total_cost=round(total_cost, 2),
        cash_proceeds=round(cash_proceeds, 2),
    )
