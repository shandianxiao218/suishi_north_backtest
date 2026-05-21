from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from suishi_north_backtest.market_data import IndustryDailyAmount

if TYPE_CHECKING:
    from suishi_north_backtest.parameters import StrategyParameters


class MainlineStatus(str, Enum):
    NONE = "none"
    STARTUP = "startup"
    OBSERVATION = "observation"
    STRONG = "strong"


@dataclass
class IndustryMainlineEntry:
    trade_date: str
    industry_level2: str
    status: MainlineStatus
    rank: int
    amount: float


STRONG_CONSECUTIVE_DAYS = 3
TOP_N = 5
OBSERVATION_WINDOW_DAYS = 5
OBSERVATION_MIN_COUNT = 3


def compute_mainlines(
    data: list[IndustryDailyAmount],
    as_of: str | None = None,
    top_n: int = TOP_N,
    strong_days: int = STRONG_CONSECUTIVE_DAYS,
    observation_window: int = OBSERVATION_WINDOW_DAYS,
    observation_min: int = OBSERVATION_MIN_COUNT,
    parameters: StrategyParameters | None = None,
) -> list[IndustryMainlineEntry]:
    if parameters is not None:
        top_n = parameters.mainline_top_n
        strong_days = parameters.strong_mainline_days
        observation_window = parameters.observation_window_days
        observation_min = parameters.observation_min_count

    if not data:
        return []

    # Filter by as_of
    filtered = [d for d in data if as_of is None or d.trade_date <= as_of]
    if not filtered:
        return []

    # Group by date
    by_date: dict[str, list[IndustryDailyAmount]] = {}
    for d in filtered:
        by_date.setdefault(d.trade_date, []).append(d)

    sorted_dates = sorted(by_date.keys())

    # For each date, compute top-N industries
    daily_top: dict[str, set[str]] = {}
    daily_rank: dict[str, dict[str, tuple[int, float]]] = {}

    for date in sorted_dates:
        day_data = sorted(by_date[date], key=lambda x: -x.amount)
        top_set = set()
        rank_map: dict[str, tuple[int, float]] = {}
        for i, d in enumerate(day_data):
            rank_map[d.industry_level2] = (i + 1, d.amount)
            if i < top_n:
                top_set.add(d.industry_level2)
        daily_top[date] = top_set
        daily_rank[date] = rank_map

    # Compute mainline status for each industry on each date
    entries: list[IndustryMainlineEntry] = []

    for date in sorted_dates:
        rank_map = daily_rank[date]
        all_industries = {d.industry_level2 for d in by_date[date]}

        for industry in all_industries:
            rank, amount = rank_map[industry]
            status = MainlineStatus.NONE

            is_top_today = industry in daily_top[date]

            if is_top_today:
                # Check strong mainline: consecutive top-N for `strong_days`
                idx = sorted_dates.index(date)
                if idx >= strong_days - 1:
                    consecutive = all(
                        industry in daily_top.get(sorted_dates[idx - k], set())
                        for k in range(strong_days)
                    )
                    if consecutive:
                        status = MainlineStatus.STRONG

                # Check observation mainline: top-N at least observation_min in last observation_window days
                if status != MainlineStatus.STRONG:
                    window_start_idx = max(0, idx - observation_window + 1)
                    window_dates = sorted_dates[window_start_idx : idx + 1]
                    count = sum(
                        1
                        for d in window_dates
                        if industry in daily_top.get(d, set())
                    )
                    if count >= observation_min:
                        status = MainlineStatus.OBSERVATION

                # Check startup: first time entering top-N
                if status == MainlineStatus.NONE:
                    idx = sorted_dates.index(date)
                    if idx > 0:
                        was_top_before = any(
                            industry in daily_top.get(sorted_dates[k], set())
                            for k in range(idx)
                        )
                        if not was_top_before:
                            status = MainlineStatus.STARTUP
                    else:
                        status = MainlineStatus.STARTUP

            entries.append(
                IndustryMainlineEntry(
                    trade_date=date,
                    industry_level2=industry,
                    status=status,
                    rank=rank,
                    amount=amount,
                )
            )

    return entries
