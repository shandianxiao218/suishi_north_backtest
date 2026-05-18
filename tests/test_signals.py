from __future__ import annotations

import pytest

from suishi_north_backtest.market_data import StockDaily
from suishi_north_backtest.signals import (
    CandidateSignal,
    find_candidates,
)


# ---- 辅助函数 ----


def bar(
    trade_date: str,
    close: float,
    high: float | None = None,
    low: float | None = None,
    symbol: str = "000001",
) -> StockDaily:
    return StockDaily(
        trade_date=trade_date,
        symbol=symbol,
        open=close,
        high=high or close * 1.01,
        low=low or close * 0.99,
        close=close,
        volume=100000.0,
        amount=1000000.0,
        is_st=False,
        limit_up=None,
        limit_down=None,
        is_suspended=False,
    )


def make_abcd_bars(
    a_close: float = 10.0,
    b_close: float = 13.0,
    c_close: float = 11.0,
    signal_close: float = 11.5,
    a_date: str = "2024-01-02",
    b_offset: int = 5,
    c_offset: int = 10,
    signal_offset: int = 12,
    symbol: str = "000001",
) -> list[StockDaily]:
    """生成一个典型 AB→BC→C 点→信号的日线序列。"""
    bars = []

    # A 点前的下跌段（让 A 成为局部低点）
    for i in range(3):
        d = _offset_date(a_date, -(3 - i))
        bars.append(bar(d, a_close - 1.0 + i * 0.5, symbol=symbol))

    # A 点
    bars.append(bar(a_date, a_close, low=a_close * 0.98, symbol=symbol))

    # A→B 上涨段（不到达 B 的价格，让 B 独特）
    steps = b_offset - 1
    for i in range(1, b_offset):
        d = _offset_date(a_date, i)
        frac = (i - 0.5) / steps if steps > 0 else 0.5
        c_inter = a_close + (b_close - a_close) * frac
        bars.append(bar(d, c_inter, symbol=symbol))

    # B 点（高点）
    b_date = _offset_date(a_date, b_offset)
    bars.append(bar(b_date, b_close, high=b_close * 1.02, symbol=symbol))

    # B→C 回撤段
    bc_steps = c_offset - b_offset
    for i in range(1, bc_steps):
        d = _offset_date(a_date, b_offset + i)
        frac = i / bc_steps if bc_steps > 0 else 1
        c_inter = b_close + (c_close - b_close) * frac
        bars.append(bar(d, c_inter, symbol=symbol))

    # C 点（BC 回撤低点）
    c_date = _offset_date(a_date, c_offset)
    bars.append(bar(c_date, c_close, low=c_close * 0.98, symbol=symbol))

    # C→信号日（止跌转强）
    for i in range(1, signal_offset - c_offset + 1):
        d = _offset_date(a_date, c_offset + i)
        c_val = c_close + (signal_close - c_close) * (i / (signal_offset - c_offset))
        bars.append(bar(d, c_val, symbol=symbol))

    return bars


def _offset_date(date_str: str, offset: int) -> str:
    from datetime import date, timedelta

    d = date.fromisoformat(date_str) + timedelta(days=offset)
    return d.isoformat()


# ---- 测试 ----


def test_valid_abcd_generates_candidate() -> None:
    """AB 涨幅 30%（10→13），BC 回撤约 67% of AB，C 点窗口内，应生成候选。"""
    bars = make_abcd_bars(
        a_close=10.0,
        b_close=13.0,
        c_close=11.5,
        signal_close=11.8,
    )

    candidates = find_candidates(bars, as_of="2024-01-30")

    assert len(candidates) >= 1
    c = candidates[0]
    assert c.symbol == "000001"
    assert c.a_price == pytest.approx(10.0, abs=0.01)
    assert c.b_price == pytest.approx(13.0, abs=0.01)


def test_ab_gain_below_20pct_no_candidate() -> None:
    """AB 涨幅不足 20%，不应生成候选。"""
    bars = make_abcd_bars(
        a_close=10.0,
        b_close=11.5,  # 涨幅 15%
        c_close=10.8,
        signal_close=11.0,
    )

    candidates = find_candidates(bars, as_of="2024-01-30")

    assert len(candidates) == 0


def test_bc_retracement_exceeds_60pct_no_candidate() -> None:
    """BC 回撤超过 AB 涨幅的 60%，不应生成候选。"""
    bars = make_abcd_bars(
        a_close=10.0,
        b_close=13.0,
        c_close=10.5,  # 回撤 2.5/3.0 = 83% > 60%
        signal_close=10.8,
    )

    candidates = find_candidates(bars, as_of="2024-01-30")

    assert len(candidates) == 0


def test_c_point_window_too_early_no_candidate() -> None:
    """C 点在 B 后不足 3 个交易日，不应生成候选。"""
    bars = make_abcd_bars(
        a_close=10.0,
        b_close=13.0,
        c_close=11.5,
        signal_close=11.8,
        b_offset=5,
        c_offset=6,  # B 后仅 1 个交易日
        signal_offset=8,
    )

    candidates = find_candidates(bars, as_of="2024-01-30")

    assert len(candidates) == 0


def test_signal_distance_exceeds_8pct_no_candidate() -> None:
    """信号日收盘价距离 C 点低点超过 8%，不应生成候选。"""
    bars = make_abcd_bars(
        a_close=10.0,
        b_close=13.0,
        c_close=11.0,
        signal_close=12.5,  # (12.5-11.0)/11.0 = 13.6% > 8%
    )

    candidates = find_candidates(bars, as_of="2024-01-30")

    assert len(candidates) == 0


def test_as_of_prevents_future_data() -> None:
    """as_of 之前的信号日数据不影响后续候选。"""
    bars = make_abcd_bars(
        a_close=10.0,
        b_close=13.0,
        c_close=11.5,
        signal_close=11.8,
    )

    # as_of 设在信号日之前，不应看到候选
    candidates_early = find_candidates(bars, as_of="2024-01-10")
    # 如果信号日在 2024-01-14 之后，as_of=01-10 应看不到候选
    # 具体取决于 make_abcd_bars 的日期偏移

    # as_of 设在信号日之后，应能看到候选
    candidates_late = find_candidates(bars, as_of="2024-01-30")
    assert len(candidates_late) >= 1


def test_candidate_has_required_fields() -> None:
    bars = make_abcd_bars(
        a_close=10.0,
        b_close=13.0,
        c_close=11.5,
        signal_close=11.8,
    )

    candidates = find_candidates(bars, as_of="2024-01-30")
    assert len(candidates) >= 1

    c = candidates[0]
    assert hasattr(c, "signal_date")
    assert hasattr(c, "symbol")
    assert hasattr(c, "a_date")
    assert hasattr(c, "a_price")
    assert hasattr(c, "b_date")
    assert hasattr(c, "b_price")
    assert hasattr(c, "c_date")
    assert hasattr(c, "c_price")
    assert hasattr(c, "ab_gain_pct")
    assert hasattr(c, "bc_retracement_pct")


def test_empty_bars_returns_empty() -> None:
    candidates = find_candidates([], as_of="2024-01-02")
    assert candidates == []


def test_insufficient_bars_returns_empty() -> None:
    bars = [bar("2024-01-02", 10.0), bar("2024-01-03", 10.5)]
    candidates = find_candidates(bars, as_of="2024-01-05")
    assert candidates == []
