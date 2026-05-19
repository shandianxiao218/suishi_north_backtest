from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from suishi_north_backtest.market_data import StockDaily


class ExitType(str, Enum):
    STRUCTURE_STOP = "structure_stop"
    EMERGENCY_STOP = "emergency_stop"
    TIME_STOP = "time_stop"
    TREND_EXIT = "trend_exit"
    MAX_HOLDING = "max_holding"


@dataclass
class ExitSignal:
    """T 日收盘检测到的退出信号，尚未执行卖出。"""
    exit_type: ExitType
    signal_date: str
    reason: str


@dataclass
class SellResult:
    """T+1 卖出执行结果。"""
    executed: bool
    symbol: str
    exit_type: ExitType | None = None
    exit_price: float | None = None
    exit_date: str = ""
    commission: float = 0.0
    slippage: float = 0.0
    total_cost: float = 0.0
    cash_remaining: float = 0.0
    deferred: bool = False
    reason: str = ""


DEFAULT_EMERGENCY_STOP_PCT = 0.05
DEFAULT_TREND_EXIT_PCT = 0.08
DEFAULT_TIME_STOP_DAYS = 3
DEFAULT_MAX_HOLDING_DAYS = 30
DEFAULT_COMMISSION_RATE = 0.0003
DEFAULT_SLIPPAGE_RATE = 0.0005
DEFAULT_STAMP_TAX_RATE = 0.0005


def detect_exit_signal(
    current_bar: StockDaily,
    entry_price: float,
    c_price: float,
    highest_close_since_entry: float,
    trading_days_since_entry: int = 0,
    emergency_stop_pct: float = DEFAULT_EMERGENCY_STOP_PCT,
    trend_exit_pct: float = DEFAULT_TREND_EXIT_PCT,
    time_stop_days: int = DEFAULT_TIME_STOP_DAYS,
    max_holding_days: int = DEFAULT_MAX_HOLDING_DAYS,
) -> ExitSignal | None:
    """T 日收盘后检测退出信号。只用 T 日及之前数据，不含 T+1 卖出逻辑。"""
    close = current_bar.close
    low = current_bar.low

    # Priority 1: Structure stop (intraday low below C point)
    if low is not None and close is not None and low < c_price:
        return ExitSignal(
            exit_type=ExitType.STRUCTURE_STOP,
            signal_date=current_bar.trade_date,
            reason=f"结构止损：最低 {low:.2f} < C 点 {c_price:.2f}",
        )

    # Priority 2: Emergency stop (close below entry - N%)
    if close is not None:
        stop_price = entry_price * (1 - emergency_stop_pct)
        if close <= stop_price:
            return ExitSignal(
                exit_type=ExitType.EMERGENCY_STOP,
                signal_date=current_bar.trade_date,
                reason=f"应急止损：收盘 {close:.2f} <= 止损价 {stop_price:.2f}",
            )

    # Priority 3: Time stop (no profit in N trading days)
    if trading_days_since_entry >= time_stop_days:
        if close is not None and close <= entry_price:
            return ExitSignal(
                exit_type=ExitType.TIME_STOP,
                signal_date=current_bar.trade_date,
                reason=f"时间止损：{trading_days_since_entry} 日无浮盈",
            )

    # Priority 4: Trend exit (drawdown from highest close)
    if highest_close_since_entry > 0 and close is not None:
        drawdown_price = highest_close_since_entry * (1 - trend_exit_pct)
        if close <= drawdown_price:
            return ExitSignal(
                exit_type=ExitType.TREND_EXIT,
                signal_date=current_bar.trade_date,
                reason=f"趋势退出：收盘 {close:.2f} <= 回撤价 {drawdown_price:.2f}",
            )

    # Priority 5: Max holding period
    if trading_days_since_entry >= max_holding_days:
        return ExitSignal(
            exit_type=ExitType.MAX_HOLDING,
            signal_date=current_bar.trade_date,
            reason=f"硬最大持仓：{trading_days_since_entry} 个交易日",
        )

    return None


def execute_sell(
    signal: ExitSignal,
    symbol: str,
    open_price: float | None,
    cash: float,
    shares: int,
    is_suspended: bool = False,
    limit_down: float | None = None,
    commission_rate: float = DEFAULT_COMMISSION_RATE,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
    stamp_tax_rate: float = DEFAULT_STAMP_TAX_RATE,
) -> SellResult:
    """退出信号后 T+1 开盘卖出。停牌或一字跌停时顺延。"""
    if open_price is None or is_suspended:
        return SellResult(
            executed=False,
            symbol=symbol,
            exit_type=signal.exit_type,
            deferred=True,
            reason=f"停牌无法卖出，顺延：{symbol}",
        )

    # Check limit down (一字跌停)
    if limit_down is not None and open_price <= limit_down:
        return SellResult(
            executed=False,
            symbol=symbol,
            exit_type=signal.exit_type,
            deferred=True,
            reason=f"一字跌停无法卖出，顺延：{symbol}",
        )

    # Sell at open price with slippage
    exit_price = open_price * (1 - slippage_rate)
    trade_amount = shares * exit_price

    # Costs: commission (both sides) + stamp tax (sell only)
    commission = trade_amount * commission_rate
    stamp_tax = trade_amount * stamp_tax_rate
    slippage = shares * open_price * slippage_rate
    total_cost = commission + stamp_tax + slippage

    cash_remaining = cash + trade_amount - commission - stamp_tax

    return SellResult(
        executed=True,
        symbol=symbol,
        exit_type=signal.exit_type,
        exit_price=round(exit_price, 4),
        exit_date="",  # filled by caller with actual T+1 date
        commission=round(commission, 2),
        slippage=round(slippage, 2),
        total_cost=round(total_cost, 2),
        cash_remaining=round(cash_remaining, 2),
        reason=signal.reason,
    )


# Backward-compatible wrapper
def check_exit(
    bars: list[StockDaily],
    entry_price: float,
    c_price: float,
    highest_close_since_entry: float,
    entry_date: str,
    current_date: str,
    trading_days_since_entry: int = 0,
    emergency_stop_pct: float = DEFAULT_EMERGENCY_STOP_PCT,
    trend_exit_pct: float = DEFAULT_TREND_EXIT_PCT,
    time_stop_days: int = DEFAULT_TIME_STOP_DAYS,
    max_holding_days: int = DEFAULT_MAX_HOLDING_DAYS,
) -> ExitSignal | None:
    """向后兼容的检测入口。"""
    if not bars:
        return None
    return detect_exit_signal(
        current_bar=bars[-1],
        entry_price=entry_price,
        c_price=c_price,
        highest_close_since_entry=highest_close_since_entry,
        trading_days_since_entry=trading_days_since_entry,
        emergency_stop_pct=emergency_stop_pct,
        trend_exit_pct=trend_exit_pct,
        time_stop_days=time_stop_days,
        max_holding_days=max_holding_days,
    )
