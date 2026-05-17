from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from suishi_north_backtest.data import MarketBar
from suishi_north_backtest.execution import ExecutionRules


@dataclass(frozen=True)
class Position:
    """持仓状态。"""

    symbol: str
    entry_date: date
    entry_price: float
    quantity: int
    structural_stop: float
    highest_close: float
    holding_days: int
    has_floating_profit: bool


@dataclass(frozen=True)
class ExitRules:
    """MVP-1 退出规则参数。"""

    emergency_stop_pct: float = 0.05
    trend_drawdown_pct: float = 0.08
    time_stop_days: int = 3
    max_holding_days: int = 30


@dataclass(frozen=True)
class ExitSignal:
    """退出信号。"""

    symbol: str
    signal_date: date
    reason: str


@dataclass(frozen=True)
class ExitTrade:
    """卖出成交结果。"""

    symbol: str
    signal_date: date
    exit_date: date
    exit_price: float
    quantity: int
    reason: str
    gross_amount: float
    commission: float
    stamp_tax: float
    slippage_cost: float
    total_exit_cost: float


@dataclass(frozen=True)
class ExitExecutionResult:
    """卖出执行结果。"""

    trade: ExitTrade | None
    deferred_reason: str | None


def evaluate_exit_signal(
    position: Position,
    bar: MarketBar,
    *,
    rules: ExitRules = ExitRules(),
) -> ExitSignal | None:
    """按保守优先级评估退出信号。"""

    reason = _exit_reason(position, bar, rules)
    if reason is None:
        return None
    return ExitSignal(symbol=position.symbol, signal_date=bar.date, reason=reason)


def execute_exit_signal(
    signal: ExitSignal,
    position: Position,
    execution_bar: MarketBar,
    *,
    is_locked_limit_down: bool = False,
    rules: ExecutionRules = ExecutionRules(),
) -> ExitExecutionResult:
    """按退出信号后的下一交易日开盘卖出。"""

    if (
        execution_bar.is_suspended
        or not execution_bar.has_open_price
        or is_locked_limit_down
    ):
        return ExitExecutionResult(
            trade=None,
            deferred_reason="T+1 停牌或一字跌停无法卖出，顺延",
        )
    if execution_bar.open is None:
        return ExitExecutionResult(
            trade=None,
            deferred_reason="T+1 停牌或一字跌停无法卖出，顺延",
        )

    exit_price = round(execution_bar.open * (1 - rules.sell_slippage_rate), 6)
    gross_amount = exit_price * position.quantity
    commission = gross_amount * rules.commission_rate
    stamp_tax = gross_amount * rules.stamp_tax_rate
    slippage_cost = execution_bar.open * rules.sell_slippage_rate * position.quantity
    return ExitExecutionResult(
        trade=ExitTrade(
            symbol=position.symbol,
            signal_date=signal.signal_date,
            exit_date=execution_bar.date,
            exit_price=exit_price,
            quantity=position.quantity,
            reason=signal.reason,
            gross_amount=gross_amount,
            commission=commission,
            stamp_tax=stamp_tax,
            slippage_cost=slippage_cost,
            total_exit_cost=commission + stamp_tax + slippage_cost,
        ),
        deferred_reason=None,
    )


def _exit_reason(
    position: Position,
    bar: MarketBar,
    rules: ExitRules,
) -> str | None:
    if bar.close < position.structural_stop:
        return "结构止损"
    if bar.close <= position.entry_price * (1 - rules.emergency_stop_pct):
        return "应急止损"
    if (
        position.holding_days >= rules.time_stop_days
        and not position.has_floating_profit
    ):
        return "时间止损"
    if bar.close <= position.highest_close * (1 - rules.trend_drawdown_pct):
        return "趋势退出"
    if position.holding_days >= rules.max_holding_days:
        return "硬最大持仓"
    return None
