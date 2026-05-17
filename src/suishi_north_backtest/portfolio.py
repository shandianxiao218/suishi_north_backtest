from __future__ import annotations

from dataclasses import dataclass
from datetime import date


MAINLINE_PRIORITY = {
    "strong": 3,
    "watch": 2,
    "started": 1,
    "none": 0,
}


@dataclass(frozen=True)
class EntryCandidate:
    """组合开仓候选。"""

    symbol: str
    signal_date: date
    industry: str
    mainline_status: str
    industry_rank: int
    stock_amount: float
    distance_to_c_low: float
    bc_retrace: float
    weekly_strength: float


@dataclass(frozen=True)
class PortfolioRules:
    """MVP-1 组合开仓约束。"""

    max_positions: int = 3
    max_new_positions_per_day: int = 1
    max_new_positions_per_week: int = 2


@dataclass(frozen=True)
class EntrySelection:
    """候选选择结果。"""

    selected: list[EntryCandidate]
    skipped_reasons: dict[str, list[str]]


def select_entry_candidates(
    candidates: list[EntryCandidate],
    *,
    held_symbols: set[str],
    opened_this_week: int,
    rules: PortfolioRules = PortfolioRules(),
) -> EntrySelection:
    """按 MVP-1 排序和组合约束选择新开仓候选。"""

    selected: list[EntryCandidate] = []
    skipped_reasons: dict[str, list[str]] = {}
    current_positions = len(held_symbols)

    for item in sorted(candidates, key=_candidate_sort_key):
        if item.symbol in held_symbols:
            skipped_reasons[item.symbol] = ["已持仓股票重复信号"]
            continue
        if current_positions + len(selected) >= rules.max_positions:
            skipped_reasons[item.symbol] = ["最大同时持仓已达上限"]
            continue
        if opened_this_week + len(selected) >= rules.max_new_positions_per_week:
            skipped_reasons[item.symbol] = ["本周新开仓数量已达上限"]
            continue
        if len(selected) >= rules.max_new_positions_per_day:
            skipped_reasons[item.symbol] = ["当日新开仓数量已达上限"]
            continue
        selected.append(item)

    return EntrySelection(selected=selected, skipped_reasons=skipped_reasons)


def _candidate_sort_key(candidate: EntryCandidate) -> tuple[float, ...]:
    return (
        -MAINLINE_PRIORITY.get(candidate.mainline_status, 0),
        candidate.industry_rank,
        -candidate.stock_amount,
        candidate.distance_to_c_low,
        candidate.bc_retrace,
        -candidate.weekly_strength,
    )
