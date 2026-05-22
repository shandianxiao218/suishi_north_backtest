from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from suishi_north_backtest.market_data import StockDaily

if TYPE_CHECKING:
    from suishi_north_backtest.parameters import StrategyParameters


SIGNAL_RULE_VERSION = "MVP1-SIGNAL-AUDIT-v1"


@dataclass
class CandidateSignal:
    signal_date: str
    symbol: str
    a_date: str
    a_price: float
    b_date: str
    b_price: float
    c_date: str
    c_price: float
    ab_gain_pct: float
    bc_retracement_pct: float
    distance_to_c_pct: float
    weekly_filter_passed: bool = True
    annual_filter_passed: bool = True
    failure_reason: str = ""
    as_of: str = ""
    signal_rule_version: str = SIGNAL_RULE_VERSION
    audit_note: str = "candidate passed MVP-1 signal audit"


DEFAULT_AB_MIN_GAIN_PCT = 20.0
DEFAULT_BC_MAX_RETRACEMENT_PCT = 60.0
DEFAULT_C_WINDOW_MIN = 3
DEFAULT_C_WINDOW_MAX = 20
DEFAULT_SIGNAL_DISTANCE_MAX_PCT = 8.0


def find_candidates(
    bars: list[StockDaily],
    as_of: str | None = None,
    ab_min_gain_pct: float = DEFAULT_AB_MIN_GAIN_PCT,
    bc_max_retracement_pct: float = DEFAULT_BC_MAX_RETRACEMENT_PCT,
    c_window_min: int = DEFAULT_C_WINDOW_MIN,
    c_window_max: int = DEFAULT_C_WINDOW_MAX,
    signal_distance_max_pct: float = DEFAULT_SIGNAL_DISTANCE_MAX_PCT,
    parameters: StrategyParameters | None = None,
) -> list[CandidateSignal]:
    (
        ab_min_gain_pct,
        bc_max_retracement_pct,
        c_window_min,
        c_window_max,
        signal_distance_max_pct,
    ) = _resolve_signal_parameters(
        ab_min_gain_pct,
        bc_max_retracement_pct,
        c_window_min,
        c_window_max,
        signal_distance_max_pct,
        parameters,
    )

    if len(bars) < 5:
        return []

    if as_of:
        bars = [b for b in bars if b.trade_date <= as_of]

    if len(bars) < 5:
        return []

    bars = sorted(bars, key=lambda b: b.trade_date)
    bars = [b for b in bars if b.close is not None]

    by_symbol: dict[str, list[StockDaily]] = {}
    for b in bars:
        by_symbol.setdefault(b.symbol, []).append(b)

    candidates: list[CandidateSignal] = []

    for symbol, symbol_bars in by_symbol.items():
        symbol_candidates = _find_candidates_for_symbol(
            symbol_bars,
            symbol,
            ab_min_gain_pct,
            bc_max_retracement_pct,
            c_window_min,
            c_window_max,
            signal_distance_max_pct,
            as_of=as_of,
        )
        candidates.extend(symbol_candidates)

    return candidates


def _resolve_signal_parameters(
    ab_min_gain_pct: float = DEFAULT_AB_MIN_GAIN_PCT,
    bc_max_retracement_pct: float = DEFAULT_BC_MAX_RETRACEMENT_PCT,
    c_window_min: int = DEFAULT_C_WINDOW_MIN,
    c_window_max: int = DEFAULT_C_WINDOW_MAX,
    signal_distance_max_pct: float = DEFAULT_SIGNAL_DISTANCE_MAX_PCT,
    parameters: StrategyParameters | None = None,
) -> tuple[float, float, int, int, float]:
    if parameters is not None:
        return (
            parameters.ab_min_gain_pct_for_signals,
            parameters.bc_max_retracement_pct_for_signals,
            parameters.c_window_min_days,
            parameters.c_window_max_days,
            parameters.signal_distance_to_c_max_pct_for_signals,
        )
    return (
        ab_min_gain_pct,
        bc_max_retracement_pct,
        c_window_min,
        c_window_max,
        signal_distance_max_pct,
    )


def _find_candidates_for_symbol(
    bars: list[StockDaily],
    symbol: str,
    ab_min_gain_pct: float,
    bc_max_retracement_pct: float,
    c_window_min: int,
    c_window_max: int,
    signal_distance_max_pct: float,
    as_of: str | None = None,
) -> list[CandidateSignal]:
    candidates: list[CandidateSignal] = []

    for b_idx in range(2, len(bars) - 2):
        b_bar = bars[b_idx]

        if b_bar.close <= bars[b_idx - 1].close or b_bar.close <= bars[b_idx + 1].close:
            continue

        a_idx, a_bar = _find_a_point(bars, b_idx)
        if a_idx is None or a_bar is None:
            continue

        ab_gain_pct = (b_bar.close - a_bar.close) / a_bar.close * 100
        if ab_gain_pct < ab_min_gain_pct:
            continue

        for c_offset in range(c_window_min, min(c_window_max + 1, len(bars) - b_idx)):
            c_idx = b_idx + c_offset
            if c_idx >= len(bars):
                break

            c_bar = bars[c_idx]

            if c_idx > 0 and c_idx < len(bars) - 1:
                if c_bar.close > bars[c_idx - 1].close or c_bar.close > bars[c_idx + 1].close:
                    continue

            bc_drop = b_bar.close - c_bar.close
            ab_gain = b_bar.close - a_bar.close
            if ab_gain == 0:
                continue

            bc_retracement_pct = bc_drop / ab_gain * 100
            if bc_retracement_pct > bc_max_retracement_pct:
                continue

            for sig_idx in range(c_idx + 1, min(c_idx + 6, len(bars))):
                sig_bar = bars[sig_idx]

                if not _is_turn_strong(bars, sig_idx, c_idx):
                    continue

                distance_pct = (sig_bar.close - c_bar.close) / c_bar.close * 100
                if distance_pct > signal_distance_max_pct:
                    continue

                weekly_passed = _is_weekly_filter_passed(bars, sig_idx)
                annual_passed = _is_annual_filter_passed(bars, sig_idx)
                if not weekly_passed or not annual_passed:
                    continue

                candidates.append(
                    CandidateSignal(
                        signal_date=sig_bar.trade_date,
                        symbol=symbol,
                        a_date=a_bar.trade_date,
                        a_price=a_bar.close,
                        b_date=b_bar.trade_date,
                        b_price=b_bar.close,
                        c_date=c_bar.trade_date,
                        c_price=c_bar.close,
                        ab_gain_pct=round(ab_gain_pct, 2),
                        bc_retracement_pct=round(bc_retracement_pct, 2),
                        distance_to_c_pct=round(distance_pct, 2),
                        weekly_filter_passed=weekly_passed,
                        annual_filter_passed=annual_passed,
                        failure_reason="",
                        as_of=as_of or sig_bar.trade_date,
                        signal_rule_version=SIGNAL_RULE_VERSION,
                        audit_note=(
                            "passed AB gain, BC retracement, C window, turn-strong, "
                            "weekly direction and annual structure filters without future data"
                        ),
                    )
                )
                break

    return candidates


def _find_a_point(
    bars: list[StockDaily], b_idx: int
) -> tuple[int | None, StockDaily | None]:
    best_idx = None
    best_low = None

    for i in range(max(0, b_idx - 25), b_idx):
        if i < 1 or i >= len(bars) - 1:
            continue
        if bars[i].close <= bars[i - 1].close and bars[i].close <= bars[i + 1].close:
            if best_low is None or bars[i].close < best_low:
                best_low = bars[i].close
                best_idx = i

    if best_idx is not None:
        return best_idx, bars[best_idx]
    return None, None


def _is_turn_strong(bars: list[StockDaily], sig_idx: int, c_idx: int) -> bool:
    if sig_idx >= 4:
        ma5 = sum(bars[i].close for i in range(sig_idx - 4, sig_idx + 1)) / 5
        if bars[sig_idx].close > ma5:
            return True

    if sig_idx >= c_idx + 2:
        last_two = bars[sig_idx - 1 : sig_idx + 1]
        c_close = bars[c_idx].close
        if all(b.close >= c_close for b in last_two):
            if bars[sig_idx].close >= bars[sig_idx - 1].close:
                return True

    return False


def _is_weekly_filter_passed(bars: list[StockDaily], sig_idx: int) -> bool:
    """日线代理的周线方向过滤。

    MVP-1 仍是日线代理系统；这里用最近约 5 个交易日方向做保守代理。
    数据不足 5 个交易日时不阻断，避免对短 fixture 过拟合。
    """
    if sig_idx < 5:
        return True
    current = bars[sig_idx].close
    five_days_ago = bars[sig_idx - 5].close
    recent_lows = [b.close for b in bars[max(0, sig_idx - 4) : sig_idx + 1]]
    return current >= five_days_ago and current >= min(recent_lows)


def _is_annual_filter_passed(bars: list[StockDaily], sig_idx: int) -> bool:
    """日线代理的年线弱结构过滤。

    真实年线需要更长历史。MVP-1 先在可用窗口超过 20 个交易日时启用弱结构过滤：
    若信号日收盘显著低于可用长期均线，视为年线弱结构。
    """
    if sig_idx < 20:
        return True
    window = bars[max(0, sig_idx - 249) : sig_idx + 1]
    avg_close = sum(b.close for b in window) / len(window)
    return bars[sig_idx].close >= avg_close * 0.90
