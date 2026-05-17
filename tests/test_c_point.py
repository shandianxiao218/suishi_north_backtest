from __future__ import annotations

from datetime import date

from suishi_north_backtest.c_point import (
    CPointRules,
    find_c_point_candidates,
)
from suishi_north_backtest.data import MarketBar


def bar(day: date, close: float, low: float | None = None) -> MarketBar:
    price_low = close if low is None else low
    return MarketBar(
        symbol="000001.SZ",
        date=day,
        open=close,
        high=close,
        low=price_low,
        close=close,
        volume=1_000_000,
        amount=20_000_000,
        adjust_factor=1.0,
        is_suspended=False,
        has_open_price=True,
    )


def test_finds_c_point_candidate_after_valid_ab_and_bc_structure() -> None:
    bars = [
        bar(date(2024, 1, 1), 10.0),
        bar(date(2024, 1, 2), 11.0),
        bar(date(2024, 1, 3), 12.5),
        bar(date(2024, 1, 4), 13.0),
        bar(date(2024, 1, 5), 12.2),
        bar(date(2024, 1, 6), 11.7),
        bar(date(2024, 1, 7), 11.4, low=11.2),
        bar(date(2024, 1, 8), 11.5),
        bar(date(2024, 1, 9), 11.6),
        bar(date(2024, 1, 10), 11.9),
    ]

    candidates = find_c_point_candidates(
        "000001.SZ",
        bars,
        as_of=date(2024, 1, 10),
        rules=CPointRules(
            min_ab_gain=0.20,
            max_bc_retrace=0.60,
            min_b_to_c_days=3,
            max_b_to_c_days=20,
            max_signal_distance_from_c_low=0.08,
        ),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.symbol == "000001.SZ"
    assert candidate.a_date == date(2024, 1, 1)
    assert candidate.b_date == date(2024, 1, 4)
    assert candidate.c_date == date(2024, 1, 7)
    assert candidate.signal_date == date(2024, 1, 10)
    assert round(candidate.ab_gain, 4) == 0.3000
    assert round(candidate.bc_retrace, 4) == 0.6000
    assert candidate.signal_type == "close_above_ma5"


def test_rejects_candidate_when_ab_gain_is_too_small() -> None:
    bars = [
        bar(date(2024, 1, 1), 10.0),
        bar(date(2024, 1, 2), 10.5),
        bar(date(2024, 1, 3), 11.0),
        bar(date(2024, 1, 4), 11.5),
        bar(date(2024, 1, 5), 11.0),
        bar(date(2024, 1, 6), 10.8),
        bar(date(2024, 1, 7), 10.7),
        bar(date(2024, 1, 8), 10.9),
    ]

    candidates = find_c_point_candidates(
        "000001.SZ",
        bars,
        as_of=date(2024, 1, 8),
        rules=CPointRules(min_ab_gain=0.20),
    )

    assert candidates == []


def test_rejects_candidate_when_bc_retrace_is_too_deep() -> None:
    bars = [
        bar(date(2024, 1, 1), 10.0),
        bar(date(2024, 1, 2), 11.0),
        bar(date(2024, 1, 3), 12.0),
        bar(date(2024, 1, 4), 13.0),
        bar(date(2024, 1, 5), 11.0),
        bar(date(2024, 1, 6), 10.9),
        bar(date(2024, 1, 7), 10.8, low=10.7),
        bar(date(2024, 1, 8), 10.9),
        bar(date(2024, 1, 9), 11.0),
    ]

    candidates = find_c_point_candidates(
        "000001.SZ",
        bars,
        as_of=date(2024, 1, 9),
        rules=CPointRules(max_bc_retrace=0.60),
    )

    assert candidates == []


def test_rejects_candidate_outside_b_to_c_window() -> None:
    bars = [
        bar(date(2024, 1, 1), 10.0),
        bar(date(2024, 1, 2), 11.0),
        bar(date(2024, 1, 3), 12.0),
        bar(date(2024, 1, 4), 13.0),
        bar(date(2024, 1, 5), 12.5),
        bar(date(2024, 1, 6), 12.2),
        bar(date(2024, 1, 7), 11.8, low=11.7),
        bar(date(2024, 1, 8), 11.9),
    ]

    candidates = find_c_point_candidates(
        "000001.SZ",
        bars,
        as_of=date(2024, 1, 8),
        rules=CPointRules(min_b_to_c_days=4, max_b_to_c_days=20),
    )

    assert candidates == []


def test_finds_candidate_when_two_closes_do_not_make_new_low() -> None:
    bars = [
        bar(date(2024, 1, 1), 10.0),
        bar(date(2024, 1, 2), 11.0),
        bar(date(2024, 1, 3), 12.5),
        bar(date(2024, 1, 4), 13.0),
        bar(date(2024, 1, 5), 12.2),
        bar(date(2024, 1, 6), 11.7),
        bar(date(2024, 1, 7), 11.4, low=11.2),
        bar(date(2024, 1, 8), 11.5),
        bar(date(2024, 1, 9), 11.5),
    ]

    candidates = find_c_point_candidates(
        "000001.SZ",
        bars,
        as_of=date(2024, 1, 9),
        rules=CPointRules(),
    )

    assert len(candidates) == 1
    assert candidates[0].signal_type == "two_day_no_new_low"


def test_ignores_future_signal_after_as_of() -> None:
    bars = [
        bar(date(2024, 1, 1), 10.0),
        bar(date(2024, 1, 2), 11.0),
        bar(date(2024, 1, 3), 12.5),
        bar(date(2024, 1, 4), 13.0),
        bar(date(2024, 1, 5), 12.2),
        bar(date(2024, 1, 6), 11.7),
        bar(date(2024, 1, 7), 11.4, low=11.2),
        bar(date(2024, 1, 8), 11.3),
        bar(date(2024, 1, 9), 11.2),
        bar(date(2024, 1, 10), 11.9),
    ]

    candidates = find_c_point_candidates(
        "000001.SZ",
        bars,
        as_of=date(2024, 1, 9),
        rules=CPointRules(),
    )

    assert candidates == []
