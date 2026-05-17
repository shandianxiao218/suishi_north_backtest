from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class IndustryAmountRank:
    """二级行业单日成交额排名。"""

    date: date
    industry: str
    amount: float
    rank: int


@dataclass(frozen=True)
class MainlineRules:
    """MVP-1 主线代理参数。"""

    top_n: int = 5
    strong_consecutive_days: int = 3
    watch_window_days: int = 5
    watch_min_top_n_days: int = 3


@dataclass(frozen=True)
class MainlineState:
    """行业主线状态。"""

    industry: str
    status: str
    latest_rank: int
    top_n_days: int


def classify_mainlines(
    records: list[IndustryAmountRank],
    *,
    as_of: date,
    rules: MainlineRules = MainlineRules(),
) -> dict[str, MainlineState]:
    """按二级行业成交额排名识别 MVP-1 主线代理。"""

    visible_records = [record for record in records if record.date <= as_of]
    industries = sorted({record.industry for record in visible_records})

    return {
        industry: _classify_industry(industry, visible_records, rules)
        for industry in industries
    }


def _classify_industry(
    industry: str,
    records: list[IndustryAmountRank],
    rules: MainlineRules,
) -> MainlineState:
    industry_records = sorted(
        [record for record in records if record.industry == industry],
        key=lambda record: record.date,
    )
    latest = industry_records[-1]
    top_n_records = [
        record for record in industry_records if record.rank <= rules.top_n
    ]
    status = "none"
    if _has_consecutive_top_n_days(industry_records, rules):
        status = "strong"
    elif _has_watch_top_n_days(industry_records, rules):
        status = "watch"
    elif len(top_n_records) == 1 and latest.rank <= rules.top_n:
        status = "started"
    return MainlineState(
        industry=industry,
        status=status,
        latest_rank=latest.rank,
        top_n_days=len(top_n_records),
    )


def _has_consecutive_top_n_days(
    records: list[IndustryAmountRank],
    rules: MainlineRules,
) -> bool:
    recent = records[-rules.strong_consecutive_days :]
    return (
        len(recent) == rules.strong_consecutive_days
        and all(record.rank <= rules.top_n for record in recent)
    )


def _has_watch_top_n_days(
    records: list[IndustryAmountRank],
    rules: MainlineRules,
) -> bool:
    recent = records[-rules.watch_window_days :]
    top_n_count = sum(1 for record in recent if record.rank <= rules.top_n)
    return top_n_count >= rules.watch_min_top_n_days
