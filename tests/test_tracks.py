from __future__ import annotations

from datetime import date

from suishi_north_backtest.portfolio import EntryCandidate
from suishi_north_backtest.tracks import (
    TrackPerformance,
    TrackDefinition,
    build_track_candidates,
    compare_track_performance,
)


def candidate(symbol: str, mainline_status: str) -> EntryCandidate:
    return EntryCandidate(
        symbol=symbol,
        signal_date=date(2024, 1, 10),
        industry="机器人",
        mainline_status=mainline_status,
        industry_rank=1,
        stock_amount=50_000_000,
        distance_to_c_low=0.02,
        bc_retrace=0.40,
        weekly_strength=0.10,
    )


def test_builds_pure_structure_and_mainline_filtered_tracks() -> None:
    candidates = [
        candidate("000001.SZ", "none"),
        candidate("300001.SZ", "watch"),
        candidate("688001.SH", "strong"),
    ]

    pure = build_track_candidates(
        candidates,
        TrackDefinition(name="纯结构组合轨", require_strong_mainline=False),
    )
    mainline = build_track_candidates(
        candidates,
        TrackDefinition(name="主线过滤组合轨", require_strong_mainline=True),
    )

    assert [item.symbol for item in pure] == [
        "000001.SZ",
        "300001.SZ",
        "688001.SH",
    ]
    assert [item.symbol for item in mainline] == ["688001.SH"]


def test_compares_pure_structure_and_mainline_track_performance() -> None:
    comparison = compare_track_performance(
        pure=TrackPerformance(
            track_name="纯结构组合轨",
            win_rate=0.45,
            average_profit_loss_ratio=1.1,
            max_drawdown=0.20,
        ),
        mainline=TrackPerformance(
            track_name="主线过滤组合轨",
            win_rate=0.52,
            average_profit_loss_ratio=1.3,
            max_drawdown=0.15,
        ),
    )

    assert comparison.win_rate_delta == 0.07
    assert comparison.average_profit_loss_ratio_delta == 0.20
    assert comparison.max_drawdown_delta == -0.05
