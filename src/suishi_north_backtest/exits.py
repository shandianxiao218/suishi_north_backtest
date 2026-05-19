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
    exit_type: ExitType
    exit_date: str
    exit_price: float | None
    reason: str
    deferred: bool = False


DEFAULT_EMERGENCY_STOP_PCT = 0.05
DEFAULT_TREND_EXIT_PCT = 0.08
DEFAULT_TIME_STOP_DAYS = 3
DEFAULT_MAX_HOLDING_DAYS = 30


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
    if not bars:
        return None

    current_bar = bars[-1]

    # Check if can sell
    can_sell = _can_sell(current_bar)

    # Priority 1: Structure stop (below C point)
    if current_bar.close is not None and current_bar.low is not None:
        if current_bar.low < c_price:
            return ExitSignal(
                exit_type=ExitType.STRUCTURE_STOP,
                exit_date=current_date,
                exit_price=current_bar.close if can_sell else None,
                reason=f"结构止损：收盘 {current_bar.close} < C 点 {c_price}",
                deferred=not can_sell,
            )

    # Priority 2: Emergency stop (entry price - 5%)
    if current_bar.close is not None:
        stop_price = entry_price * (1 - emergency_stop_pct)
        if current_bar.close <= stop_price:
            return ExitSignal(
                exit_type=ExitType.EMERGENCY_STOP,
                exit_date=current_date,
                exit_price=current_bar.close if can_sell else None,
                reason=f"应急止损：收盘 {current_bar.close} <= 止损价 {stop_price:.2f}",
                deferred=not can_sell,
            )

    # Priority 3: Time stop (no profit in N days)
    if trading_days_since_entry >= time_stop_days:
        if current_bar.close is not None and current_bar.close <= entry_price:
            return ExitSignal(
                exit_type=ExitType.TIME_STOP,
                exit_date=current_date,
                exit_price=current_bar.close if can_sell else None,
                reason=f"时间止损：{trading_days_since_entry} 日无浮盈",
                deferred=not can_sell,
            )

    # Priority 4: Trend exit (drawdown from highest close)
    if highest_close_since_entry > 0 and current_bar.close is not None:
        drawdown_price = highest_close_since_entry * (1 - trend_exit_pct)
        if current_bar.close <= drawdown_price:
            return ExitSignal(
                exit_type=ExitType.TREND_EXIT,
                exit_date=current_date,
                exit_price=current_bar.close if can_sell else None,
                reason=f"趋势退出：收盘 {current_bar.close} <= 回撤价 {drawdown_price:.2f}",
                deferred=not can_sell,
            )

    # Priority 5: Max holding period
    if trading_days_since_entry >= max_holding_days:
        return ExitSignal(
            exit_type=ExitType.MAX_HOLDING,
            exit_date=current_date,
            exit_price=current_bar.close if can_sell else None,
            reason=f"硬最大持仓：{trading_days_since_entry} 个交易日",
            deferred=not can_sell,
        )

    return None


def _can_sell(bar: StockDaily) -> bool:
    if bar.is_suspended:
        return False
    if bar.close is not None and bar.limit_down is not None:
        if bar.close <= bar.limit_down:
            return False
    return True
