from __future__ import annotations

from dataclasses import dataclass

from suishi_north_backtest.portfolio import EntryCandidate


@dataclass(frozen=True)
class TrackDefinition:
    """组合回测轨道定义。"""

    name: str
    require_strong_mainline: bool


@dataclass(frozen=True)
class TrackPerformance:
    """组合轨道绩效摘要。"""

    track_name: str
    win_rate: float
    average_profit_loss_ratio: float
    max_drawdown: float


@dataclass(frozen=True)
class TrackPerformanceComparison:
    """主线过滤轨相对纯结构轨的绩效差异。"""

    win_rate_delta: float
    average_profit_loss_ratio_delta: float
    max_drawdown_delta: float


def build_track_candidates(
    candidates: list[EntryCandidate],
    track: TrackDefinition,
) -> list[EntryCandidate]:
    """按轨道定义过滤候选。"""

    if not track.require_strong_mainline:
        return candidates
    return [
        candidate
        for candidate in candidates
        if candidate.mainline_status == "strong"
    ]


def compare_track_performance(
    *,
    pure: TrackPerformance,
    mainline: TrackPerformance,
) -> TrackPerformanceComparison:
    """比较主线过滤组合轨相对纯结构组合轨的变化。"""

    return TrackPerformanceComparison(
        win_rate_delta=round(mainline.win_rate - pure.win_rate, 10),
        average_profit_loss_ratio_delta=round(
            mainline.average_profit_loss_ratio - pure.average_profit_loss_ratio,
            10,
        ),
        max_drawdown_delta=round(mainline.max_drawdown - pure.max_drawdown, 10),
    )
