from __future__ import annotations

import pytest

from suishi_north_backtest.signals import CandidateSignal
from suishi_north_backtest.portfolio import (
    PortfolioAction,
    select_candidates,
)


# ---- 辅助函数 ----


def candidate(
    signal_date: str = "2024-01-10",
    symbol: str = "000001",
    industry: str = "银行",
    ab_gain_pct: float = 30.0,
    bc_retracement_pct: float = 40.0,
    mainline_status: str = "strong",
    amount_rank: int = 1,
    distance_to_c_pct: float = 3.0,
) -> CandidateSignal:
    return CandidateSignal(
        signal_date=signal_date,
        symbol=symbol,
        a_date="2024-01-02",
        a_price=10.0,
        b_date="2024-01-05",
        b_price=13.0,
        c_date="2024-01-08",
        c_price=11.5,
        ab_gain_pct=ab_gain_pct,
        bc_retracement_pct=bc_retracement_pct,
        distance_to_c_pct=distance_to_c_pct,
    )


# ---- 测试 ----


def test_single_candidate_selected() -> None:
    candidates = [candidate(symbol="000001")]
    actions = select_candidates(candidates, current_holdings=[], opened_today=0, opened_this_week=0)

    assert len(actions) == 1
    assert actions[0].symbol == "000001"
    assert actions[0].action == "open"


def test_multiple_candidates_only_best_selected() -> None:
    """同日多个候选只选择排序最高者。"""
    candidates = [
        candidate(symbol="000001", ab_gain_pct=25.0),
        candidate(symbol="000002", ab_gain_pct=35.0),
        candidate(symbol="000003", ab_gain_pct=30.0),
    ]
    actions = select_candidates(candidates, current_holdings=[], opened_today=0, opened_this_week=0)

    open_actions = [a for a in actions if a.action == "open"]
    assert len(open_actions) == 1
    assert open_actions[0].symbol == "000002"


def test_max_holdings_reached_skips() -> None:
    """最大持仓3只时跳过新候选。"""
    candidates = [candidate(symbol="000004")]
    actions = select_candidates(
        candidates,
        current_holdings=["000001", "000002", "000003"],
        opened_today=0,
        opened_this_week=0,
    )

    assert len(actions) == 1
    assert actions[0].action == "skip"
    assert "持仓" in actions[0].reason or "满仓" in actions[0].reason


def test_daily_open_limit() -> None:
    """每日最多新开1笔。"""
    candidates = [candidate(symbol="000002")]
    actions = select_candidates(
        candidates,
        current_holdings=["000001"],
        opened_today=1,
        opened_this_week=1,
    )

    assert len(actions) == 1
    assert actions[0].action == "skip"
    assert "日" in actions[0].reason


def test_weekly_open_limit() -> None:
    """每周最多新开2笔。"""
    candidates = [candidate(symbol="000003")]
    actions = select_candidates(
        candidates,
        current_holdings=["000001"],
        opened_today=0,
        opened_this_week=2,
    )

    assert len(actions) == 1
    assert actions[0].action == "skip"
    assert "周" in actions[0].reason


def test_duplicate_holding_skipped() -> None:
    """已持仓股票重复信号跳过。"""
    candidates = [candidate(symbol="000001")]
    actions = select_candidates(
        candidates,
        current_holdings=["000001"],
        opened_today=0,
        opened_this_week=0,
    )

    assert len(actions) == 1
    assert actions[0].action == "skip"
    assert "重复" in actions[0].reason or "已持仓" in actions[0].reason


def test_empty_candidates_returns_empty() -> None:
    actions = select_candidates([], current_holdings=[], opened_today=0, opened_this_week=0)
    assert actions == []


def test_action_has_required_fields() -> None:
    candidates = [candidate(symbol="000001")]
    actions = select_candidates(candidates, current_holdings=[], opened_today=0, opened_this_week=0)

    a = actions[0]
    assert hasattr(a, "signal_date")
    assert hasattr(a, "symbol")
    assert hasattr(a, "action")
    assert hasattr(a, "reason")


def test_no_limits_allows_open() -> None:
    """无限制时正常开仓。"""
    candidates = [candidate(symbol="000001")]
    actions = select_candidates(
        candidates,
        current_holdings=[],
        opened_today=0,
        opened_this_week=0,
    )

    assert actions[0].action == "open"
