from __future__ import annotations

from dataclasses import dataclass

from suishi_north_backtest.signals import CandidateSignal


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


def select_candidates(
    candidates: list[CandidateSignal],
    current_holdings: list[str],
    opened_today: int,
    opened_this_week: int,
    max_holdings: int = DEFAULT_MAX_HOLDINGS,
    daily_open_limit: int = DEFAULT_DAILY_OPEN_LIMIT,
    weekly_open_limit: int = DEFAULT_WEEKLY_OPEN_LIMIT,
) -> list[PortfolioAction]:
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
