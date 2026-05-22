from __future__ import annotations

from datetime import date, timedelta

from suishi_north_backtest.market_data import StockDaily
from suishi_north_backtest.signal_audit import audit_signal_candidates
from suishi_north_backtest.signals import find_candidates


def bar(trade_date: str, close: float, symbol: str = "000001") -> StockDaily:
    return StockDaily(
        trade_date=trade_date,
        symbol=symbol,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=100000.0,
        amount=1000000.0,
        is_st=False,
        limit_up=None,
        limit_down=None,
        is_suspended=False,
    )


def bars_from_prices(prices: list[float], start: str = "2024-01-02") -> list[StockDaily]:
    start_date = date.fromisoformat(start)
    return [
        bar((start_date + timedelta(days=i)).isoformat(), price)
        for i, price in enumerate(prices)
    ]


def reasons(rows):
    return [row.failure_reason for row in rows]


def local_abcd_prices(signal_close: float = 12.4) -> list[float]:
    return [11.0, 10.0, 10.5, 11.5, 13.0, 12.1, 11.8, 11.6, 11.5, 11.7, signal_close]


def test_candidate_records_failure_reason_for_low_ab_gain() -> None:
    rows = audit_signal_candidates(
        bars_from_prices([11.0, 10.0, 10.2, 10.8, 11.5, 11.2, 11.1, 11.0, 10.9, 11.0, 11.2]),
        as_of="2024-01-20",
    )

    assert any("AB 涨幅不足" in reason for reason in reasons(rows))


def test_candidate_records_failure_reason_for_deep_bc_retracement() -> None:
    rows = audit_signal_candidates(
        bars_from_prices([11.0, 10.0, 10.5, 11.5, 13.0, 12.0, 11.0, 10.8, 10.5, 10.7, 10.9]),
        as_of="2024-01-20",
    )

    assert any("BC 回撤过深" in reason for reason in reasons(rows))


def test_candidate_records_failure_reason_for_far_from_c() -> None:
    rows = audit_signal_candidates(
        bars_from_prices([11.0, 10.0, 10.5, 11.5, 13.0, 12.1, 11.8, 11.6, 11.5, 12.6, 12.7]),
        as_of="2024-01-20",
    )

    assert any("距离 C 点过远" in reason for reason in reasons(rows))


def test_weekly_filter_blocks_candidate() -> None:
    rows = audit_signal_candidates(
        bars_from_prices(local_abcd_prices(signal_close=11.8)),
        as_of="2024-01-20",
    )

    weekly_rows = [row for row in rows if row.stage == "weekly_filter"]
    assert weekly_rows
    assert weekly_rows[0].weekly_filter_passed is False
    assert "周线方向过滤未通过" in weekly_rows[0].failure_reason


def test_annual_filter_blocks_candidate() -> None:
    prices = [30.0] * 14 + local_abcd_prices(signal_close=12.4)
    rows = audit_signal_candidates(bars_from_prices(prices), as_of="2024-02-20")

    annual_rows = [row for row in rows if row.stage == "annual_filter"]
    assert annual_rows
    assert annual_rows[0].annual_filter_passed is False
    assert "年线弱结构过滤未通过" in annual_rows[0].failure_reason


def test_signal_audit_never_uses_future_data() -> None:
    bars = bars_from_prices(local_abcd_prices(signal_close=12.4) + [13.0, 13.2])

    rows = audit_signal_candidates(bars, as_of="2024-01-05")

    assert rows
    assert all(row.trade_date <= "2024-01-05" for row in rows)
    assert not any(row.passed for row in rows)


def test_find_candidates_records_signal_audit_metadata() -> None:
    candidates = find_candidates(
        bars_from_prices(local_abcd_prices(signal_close=12.4)),
        as_of="2024-01-30",
    )

    assert candidates
    candidate = candidates[0]
    assert candidate.as_of == "2024-01-30"
    assert candidate.signal_rule_version
    assert candidate.weekly_filter_passed is True
    assert candidate.annual_filter_passed is True
    assert candidate.failure_reason == ""


def test_signal_audit_uses_same_local_structure_rules_as_find_candidates() -> None:
    prices = [11.0, 10.0, 10.5, 11.5, 13.0] + [
        12.9,
        12.8,
        12.7,
        12.6,
        12.5,
        12.4,
        12.3,
        12.2,
        12.1,
        12.0,
        11.9,
        11.8,
        11.7,
        11.6,
        11.5,
        11.4,
        11.3,
        11.2,
        11.1,
        11.0,
        10.9,
    ]
    bars = bars_from_prices(prices)

    assert find_candidates(bars, as_of="2024-02-20") == []

    rows = audit_signal_candidates(bars, as_of="2024-02-20")

    assert any(row.stage == "c_window" for row in rows)
    assert not any("距离 C 点过远" in row.failure_reason for row in rows)
