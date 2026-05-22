from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from suishi_north_backtest.market_data import StockDaily

if TYPE_CHECKING:
    from suishi_north_backtest.parameters import StrategyParameters


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
    if parameters is not None:
        ab_min_gain_pct = parameters.ab_min_gain_pct_for_signals
        bc_max_retracement_pct = parameters.bc_max_retracement_pct_for_signals
        c_window_min = parameters.c_window_min_days
        c_window_max = parameters.c_window_max_days
        signal_distance_max_pct = parameters.signal_distance_to_c_max_pct_for_signals
    if len(bars) < 5:
        return []

    # Filter by as_of
    if as_of:
        bars = [b for b in bars if b.trade_date <= as_of]

    if len(bars) < 5:
        return []

    # Sort by date
    bars = sorted(bars, key=lambda b: b.trade_date)

    # Remove bars with missing close (suspended)
    bars = [b for b in bars if b.close is not None]

    # Group by symbol
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
        )
        candidates.extend(symbol_candidates)

    return candidates


def _find_candidates_for_symbol(
    bars: list[StockDaily],
    symbol: str,
    ab_min_gain_pct: float,
    bc_max_retracement_pct: float,
    c_window_min: int,
    c_window_max: int,
    signal_distance_max_pct: float,
) -> list[CandidateSignal]:
    candidates: list[CandidateSignal] = []

    for b_idx in range(2, len(bars) - 2):
        b_bar = bars[b_idx]

        # B should be a local high (higher than neighbors)
        if b_bar.close <= bars[b_idx - 1].close or b_bar.close <= bars[b_idx + 1].close:
            continue

        # Look back for A point: local low before B
        a_idx, a_bar = _find_a_point(bars, b_idx)
        if a_idx is None:
            continue

        ab_gain_pct = (b_bar.close - a_bar.close) / a_bar.close * 100
        if ab_gain_pct < ab_min_gain_pct:
            continue

        # Look forward for C point within window
        for c_offset in range(c_window_min, min(c_window_max + 1, len(bars) - b_idx)):
            c_idx = b_idx + c_offset
            if c_idx >= len(bars):
                break

            c_bar = bars[c_idx]

            # C should be a local low
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

            # Look for signal day after C: check for turn-strong
            for sig_idx in range(c_idx + 1, min(c_idx + 6, len(bars))):
                sig_bar = bars[sig_idx]

                # Check turn-strong: close above 5-day MA or 2 consecutive non-new-lows
                if not _is_turn_strong(bars, sig_idx, c_idx):
                    continue

                distance_pct = (sig_bar.close - c_bar.close) / c_bar.close * 100
                if distance_pct > signal_distance_max_pct:
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
                    )
                )
                break  # Only take first signal after C

    return candidates


def _find_a_point(
    bars: list[StockDaily], b_idx: int
) -> tuple[int | None, StockDaily | None]:
    best_idx = None
    best_low = None

    for i in range(max(0, b_idx - 25), b_idx):
        if i < 1 or i >= len(bars) - 1:
            continue
        # Local low: lower than neighbors
        if bars[i].close <= bars[i - 1].close and bars[i].close <= bars[i + 1].close:
            if best_low is None or bars[i].close < best_low:
                best_low = bars[i].close
                best_idx = i

    if best_idx is not None:
        return best_idx, bars[best_idx]
    return None, None


def _is_turn_strong(
    bars: list[StockDaily], sig_idx: int, c_idx: int
) -> bool:
    # Condition 1: close above 5-day moving average
    if sig_idx >= 4:
        ma5 = sum(bars[i].close for i in range(sig_idx - 4, sig_idx + 1)) / 5
        if bars[sig_idx].close > ma5:
            return True

    # Condition 2: 2 consecutive days with close not making new lows after C
    if sig_idx >= c_idx + 2:
        last_two = bars[sig_idx - 1 : sig_idx + 1]
        c_close = bars[c_idx].close
        if all(b.close >= c_close for b in last_two):
            # Both above C low
            if bars[sig_idx].close >= bars[sig_idx - 1].close:
                return True

    return False
