from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from suishi_north_backtest.data import MarketBar


@dataclass(frozen=True)
class CPointRules:
    """MVP-1 日线 C 点代理参数。"""

    min_ab_gain: float = 0.20
    max_bc_retrace: float = 0.60
    min_b_to_c_days: int = 3
    max_b_to_c_days: int = 20
    max_signal_distance_from_c_low: float = 0.08


@dataclass(frozen=True)
class CPointCandidate:
    """日线 C 点代理候选。"""

    symbol: str
    a_date: date
    b_date: date
    c_date: date
    signal_date: date
    a_price: float
    b_price: float
    c_low: float
    signal_close: float
    ab_gain: float
    bc_retrace: float
    signal_type: str


def find_c_point_candidates(
    symbol: str,
    bars: list[MarketBar],
    *,
    as_of: date,
    rules: CPointRules = CPointRules(),
) -> list[CPointCandidate]:
    """识别截至 as_of 可见的日线 C 点代理候选。"""

    visible_bars = sorted(
        [bar for bar in bars if bar.date <= as_of],
        key=lambda bar: bar.date,
    )
    if len(visible_bars) < 6:
        return []

    signal_bar = visible_bars[-1]
    signal_type = _signal_type(visible_bars)
    if signal_type is None:
        return []

    candidates: list[CPointCandidate] = []
    for b_index in range(1, len(visible_bars) - 1):
        a_bar = min(visible_bars[:b_index], key=lambda bar: bar.low or bar.close)
        b_bar = max([visible_bars[b_index]], key=lambda bar: bar.high or bar.close)
        a_price = a_bar.low or a_bar.close
        b_price = b_bar.high or b_bar.close
        if (b_price - a_price) / a_price < rules.min_ab_gain:
            continue

        for c_index in range(
            b_index + rules.min_b_to_c_days,
            min(b_index + rules.max_b_to_c_days, len(visible_bars) - 1) + 1,
        ):
            c_offset, c_bar = min(
                enumerate(visible_bars[b_index + 1 : c_index + 1], start=1),
                key=lambda item: item[1].low or item[1].close,
            )
            if not rules.min_b_to_c_days <= c_offset <= rules.max_b_to_c_days:
                continue
            if _has_higher_high_after_b(visible_bars, b_index, c_index, b_price):
                continue
            c_low = c_bar.low or c_bar.close
            ab_range = b_price - a_price
            bc_retrace = (b_price - c_low) / ab_range
            signal_distance = (signal_bar.close - c_low) / c_low
            if bc_retrace - rules.max_bc_retrace > 1e-9:
                continue
            if signal_distance > rules.max_signal_distance_from_c_low:
                continue
            candidates.append(
                CPointCandidate(
                    symbol=symbol,
                    a_date=a_bar.date,
                    b_date=b_bar.date,
                    c_date=c_bar.date,
                    signal_date=signal_bar.date,
                    a_price=a_price,
                    b_price=b_price,
                    c_low=c_low,
                    signal_close=signal_bar.close,
                    ab_gain=(b_price - a_price) / a_price,
                    bc_retrace=bc_retrace,
                    signal_type=signal_type,
                )
            )

    return _dedupe_candidates(candidates)


def _signal_type(bars: list[MarketBar]) -> str | None:
    signal_bar = bars[-1]
    recent = bars[-5:]
    ma5 = sum(bar.close for bar in recent) / len(recent)
    if signal_bar.close > ma5:
        return "close_above_ma5"
    if len(bars) >= 3:
        previous_bar = bars[-2]
        before_previous_bar = bars[-3]
        if (
            previous_bar.close >= before_previous_bar.close
            and signal_bar.close >= previous_bar.close
        ):
            return "two_day_no_new_low"
    return None


def _has_higher_high_after_b(
    bars: list[MarketBar],
    b_index: int,
    c_index: int,
    b_price: float,
) -> bool:
    return any(
        (bar.high or bar.close) > b_price
        for bar in bars[b_index + 1 : c_index + 1]
    )


def _dedupe_candidates(candidates: list[CPointCandidate]) -> list[CPointCandidate]:
    if not candidates:
        return []
    return [
        max(
            candidates,
            key=lambda candidate: (candidate.c_date, candidate.b_price),
        )
    ]
