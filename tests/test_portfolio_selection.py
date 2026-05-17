from __future__ import annotations

from datetime import date

from suishi_north_backtest.portfolio import (
    EntryCandidate,
    PortfolioRules,
    select_entry_candidates,
)


def candidate(
    symbol: str,
    *,
    mainline_status: str,
    industry_rank: int,
    stock_amount: float,
    distance_to_c_low: float,
    bc_retrace: float,
    weekly_strength: float,
) -> EntryCandidate:
    return EntryCandidate(
        symbol=symbol,
        signal_date=date(2024, 1, 10),
        industry="机器人",
        mainline_status=mainline_status,
        industry_rank=industry_rank,
        stock_amount=stock_amount,
        distance_to_c_low=distance_to_c_low,
        bc_retrace=bc_retrace,
        weekly_strength=weekly_strength,
    )


def test_selects_highest_ranked_candidate_when_daily_limit_is_one() -> None:
    candidates = [
        candidate(
            "000001.SZ",
            mainline_status="watch",
            industry_rank=1,
            stock_amount=90_000_000,
            distance_to_c_low=0.01,
            bc_retrace=0.30,
            weekly_strength=0.20,
        ),
        candidate(
            "300001.SZ",
            mainline_status="strong",
            industry_rank=4,
            stock_amount=50_000_000,
            distance_to_c_low=0.03,
            bc_retrace=0.40,
            weekly_strength=0.10,
        ),
    ]

    result = select_entry_candidates(
        candidates,
        held_symbols=set(),
        opened_this_week=0,
        rules=PortfolioRules(max_new_positions_per_day=1),
    )

    assert [item.symbol for item in result.selected] == ["300001.SZ"]
    assert result.skipped_reasons == {
        "000001.SZ": ["当日新开仓数量已达上限"]
    }


def test_skips_when_position_duplicate_or_capacity_limits_are_hit() -> None:
    candidates = [
        candidate(
            "000001.SZ",
            mainline_status="strong",
            industry_rank=1,
            stock_amount=90_000_000,
            distance_to_c_low=0.01,
            bc_retrace=0.30,
            weekly_strength=0.20,
        ),
        candidate(
            "300001.SZ",
            mainline_status="strong",
            industry_rank=2,
            stock_amount=80_000_000,
            distance_to_c_low=0.02,
            bc_retrace=0.35,
            weekly_strength=0.10,
        ),
    ]

    duplicate_result = select_entry_candidates(
        candidates,
        held_symbols={"000001.SZ"},
        opened_this_week=0,
        rules=PortfolioRules(max_positions=3, max_new_positions_per_day=2),
    )

    assert [item.symbol for item in duplicate_result.selected] == ["300001.SZ"]
    assert duplicate_result.skipped_reasons["000001.SZ"] == ["已持仓股票重复信号"]

    full_result = select_entry_candidates(
        candidates,
        held_symbols={"600000.SH", "000002.SZ", "300002.SZ"},
        opened_this_week=0,
        rules=PortfolioRules(max_positions=3),
    )

    assert full_result.selected == []
    assert full_result.skipped_reasons == {
        "000001.SZ": ["最大同时持仓已达上限"],
        "300001.SZ": ["最大同时持仓已达上限"],
    }

    weekly_result = select_entry_candidates(
        candidates,
        held_symbols=set(),
        opened_this_week=2,
        rules=PortfolioRules(max_new_positions_per_week=2),
    )

    assert weekly_result.selected == []
    assert weekly_result.skipped_reasons == {
        "000001.SZ": ["本周新开仓数量已达上限"],
        "300001.SZ": ["本周新开仓数量已达上限"],
    }
