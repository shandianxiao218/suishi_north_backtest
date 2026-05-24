from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from suishi_north_backtest.signals import CandidateSignal

if TYPE_CHECKING:
    from suishi_north_backtest.parameters import StrategyParameters


MAINLINE_PRIORITY = {
    "strong": 3,
    "watch": 2,
    "started": 1,
    "none": 0,
}


@dataclass(frozen=True)
class EntryCandidate:
    """组合开仓候选，保留给早期组合选择测试和调用方使用。"""

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


@dataclass
class PortfolioAction:
    signal_date: str
    symbol: str
    action: str  # "open" or "skip"
    reason: str
    candidate: CandidateSignal | None = None


DEFAULT_MAX_HOLDINGS = 3
DEFAULT_DAILY_OPEN_LIMIT = 1
DEFAULT_WEEKLY_OPEN_LIMIT = 2


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


def select_candidates(
    candidates: list[CandidateSignal],
    current_holdings: list[str],
    opened_today: int,
    opened_this_week: int,
    max_holdings: int = DEFAULT_MAX_HOLDINGS,
    daily_open_limit: int = DEFAULT_DAILY_OPEN_LIMIT,
    weekly_open_limit: int = DEFAULT_WEEKLY_OPEN_LIMIT,
    parameters: StrategyParameters | None = None,
) -> list[PortfolioAction]:
    if parameters is not None:
        max_holdings = parameters.max_holdings
        daily_open_limit = parameters.daily_open_limit
        weekly_open_limit = parameters.weekly_open_limit
    if not candidates:
        return []

    actions: list[PortfolioAction] = []

    # Sort candidates by scoring: higher AB gain = better
    sorted_candidates = sorted(candidates, key=lambda c: -c.ab_gain_pct)

    for c in sorted_candidates:
        # Check duplicate holding
        if c.symbol in current_holdings:
            actions.append(
                PortfolioAction(
                    signal_date=c.signal_date,
                    symbol=c.symbol,
                    action="skip",
                    reason=f"已持仓，重复信号跳过：{c.symbol}",
                    candidate=c,
                )
            )
            continue

        # Check max holdings
        if len(current_holdings) >= max_holdings:
            actions.append(
                PortfolioAction(
                    signal_date=c.signal_date,
                    symbol=c.symbol,
                    action="skip",
                    reason=f"满仓（{len(current_holdings)}/{max_holdings}），跳过：{c.symbol}",
                    candidate=c,
                )
            )
            continue

        # Check daily limit
        if opened_today >= daily_open_limit:
            actions.append(
                PortfolioAction(
                    signal_date=c.signal_date,
                    symbol=c.symbol,
                    action="skip",
                    reason=f"日开仓上限（{opened_today}/{daily_open_limit}），跳过：{c.symbol}",
                    candidate=c,
                )
            )
            continue

        # Check weekly limit
        if opened_this_week >= weekly_open_limit:
            actions.append(
                PortfolioAction(
                    signal_date=c.signal_date,
                    symbol=c.symbol,
                    action="skip",
                    reason=f"周开仓上限（{opened_this_week}/{weekly_open_limit}），跳过：{c.symbol}",
                    candidate=c,
                )
            )
            continue

        # Open position - only the first (best) eligible candidate
        actions.append(
            PortfolioAction(
                signal_date=c.signal_date,
                symbol=c.symbol,
                action="open",
                reason=f"开仓：{c.symbol}，AB 涨幅 {c.ab_gain_pct:.1f}%",
                candidate=c,
            )
        )
        current_holdings = current_holdings + [c.symbol]
        opened_today += 1
        opened_this_week += 1

    return actions


def _candidate_sort_key(candidate: EntryCandidate) -> tuple[float, ...]:
    return (
        -MAINLINE_PRIORITY.get(candidate.mainline_status, 0),
        candidate.industry_rank,
        -candidate.stock_amount,
        candidate.distance_to_c_low,
        candidate.bc_retrace,
        -candidate.weekly_strength,
    )
