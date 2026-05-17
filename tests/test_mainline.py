from __future__ import annotations

from datetime import date

from suishi_north_backtest.mainline import (
    IndustryAmountRank,
    MainlineRules,
    classify_mainlines,
)


def rank(day: date, industry: str, rank_value: int) -> IndustryAmountRank:
    return IndustryAmountRank(
        date=day,
        industry=industry,
        amount=100_000_000 / rank_value,
        rank=rank_value,
    )


def test_classifies_strong_mainline_after_three_consecutive_top5_days() -> None:
    records = [
        rank(date(2024, 1, 1), "机器人", 4),
        rank(date(2024, 1, 2), "机器人", 3),
        rank(date(2024, 1, 3), "机器人", 5),
        rank(date(2024, 1, 4), "机器人", 1),
        rank(date(2024, 1, 5), "机器人", 1),
    ]

    states = classify_mainlines(
        records,
        as_of=date(2024, 1, 3),
        rules=MainlineRules(top_n=5, strong_consecutive_days=3),
    )

    assert states["机器人"].status == "strong"
    assert states["机器人"].latest_rank == 5
    assert states["机器人"].top_n_days == 3


def test_classifies_watch_mainline_when_top5_appears_three_times_in_five_days() -> None:
    records = [
        rank(date(2024, 1, 1), "算力", 4),
        rank(date(2024, 1, 2), "算力", 8),
        rank(date(2024, 1, 3), "算力", 5),
        rank(date(2024, 1, 4), "算力", 7),
        rank(date(2024, 1, 5), "算力", 2),
    ]

    states = classify_mainlines(
        records,
        as_of=date(2024, 1, 5),
        rules=MainlineRules(
            top_n=5,
            strong_consecutive_days=3,
            watch_window_days=5,
            watch_min_top_n_days=3,
        ),
    )

    assert states["算力"].status == "watch"
    assert states["算力"].latest_rank == 2
    assert states["算力"].top_n_days == 3


def test_classifies_first_top5_day_as_started_only() -> None:
    records = [
        rank(date(2024, 1, 1), "低空经济", 9),
        rank(date(2024, 1, 2), "低空经济", 4),
    ]

    states = classify_mainlines(
        records,
        as_of=date(2024, 1, 2),
        rules=MainlineRules(top_n=5),
    )

    assert states["低空经济"].status == "started"
    assert states["低空经济"].top_n_days == 1


def test_started_status_does_not_linger_after_first_top5_day() -> None:
    records = [
        rank(date(2024, 1, 1), "低空经济", 4),
        rank(date(2024, 1, 2), "低空经济", 8),
    ]

    states = classify_mainlines(
        records,
        as_of=date(2024, 1, 2),
        rules=MainlineRules(top_n=5),
    )

    assert states["低空经济"].status == "none"
    assert states["低空经济"].top_n_days == 1


def test_ignores_future_rankings_after_as_of() -> None:
    records = [
        rank(date(2024, 1, 1), "机器人", 8),
        rank(date(2024, 1, 2), "机器人", 7),
        rank(date(2024, 1, 3), "机器人", 6),
        rank(date(2024, 1, 4), "机器人", 1),
        rank(date(2024, 1, 5), "机器人", 1),
        rank(date(2024, 1, 6), "机器人", 1),
    ]

    states = classify_mainlines(
        records,
        as_of=date(2024, 1, 3),
        rules=MainlineRules(top_n=5, strong_consecutive_days=3),
    )

    assert states["机器人"].status == "none"
    assert states["机器人"].top_n_days == 0
