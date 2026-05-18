from __future__ import annotations

from dataclasses import dataclass

from suishi_north_backtest.signals import CandidateSignal


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


def execute_buy(
    candidate: CandidateSignal,
    open_price: float | None,
    cash: float,
    equity: float,
    limit_up: float | None = None,
    risk_pct: float = DEFAULT_RISK_PCT,
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
    commission_rate: float = DEFAULT_COMMISSION_RATE,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
) -> ExecutionResult:
    symbol = candidate.symbol

    # Check if can trade
    if open_price is None:
        return ExecutionResult(
            executed=False,
            symbol=symbol,
            cash_remaining=cash,
            skip_reason=f"停牌，无开盘价：{symbol}",
        )

    if limit_up is not None and open_price >= limit_up:
        return ExecutionResult(
            executed=False,
            symbol=symbol,
            cash_remaining=cash,
            skip_reason=f"一字涨停无法买入：{symbol}，开盘价 {open_price} >= 涨停价 {limit_up}",
        )

    # Calculate entry price with slippage
    entry_price = open_price * (1 + slippage_rate)

    # Position sizing based on risk
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
    shares = int(raw_shares // LOT_SIZE) * LOT_SIZE

    if shares == 0:
        return ExecutionResult(
            executed=False,
            symbol=symbol,
            cash_remaining=cash,
            skip_reason=f"现金不足，无法买入一手：{symbol}",
        )

    # Check if cash is sufficient, reduce if needed
    cost = shares * entry_price
    while cost > cash and shares >= LOT_SIZE:
        shares -= LOT_SIZE
        cost = shares * entry_price

    if shares == 0:
        return ExecutionResult(
            executed=False,
            symbol=symbol,
            cash_remaining=cash,
            skip_reason=f"现金不足，无法买入：{symbol}",
        )

    # Calculate costs
    commission = cost * commission_rate
    slippage = shares * open_price * slippage_rate
    total_cost = commission + slippage

    cash_remaining = cash - cost - total_cost

    if cash_remaining < 0:
        # Try reducing shares
        while cash_remaining < 0 and shares >= LOT_SIZE:
            shares -= LOT_SIZE
            cost = shares * entry_price
            commission = cost * commission_rate
            slippage = shares * open_price * slippage_rate
            total_cost = commission + slippage
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
