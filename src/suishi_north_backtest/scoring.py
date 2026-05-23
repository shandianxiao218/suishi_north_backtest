"""候选评分与排序模块。

替代 mvp1_runner.py 中的简化 _candidate_score()，提供可解释、可复现、可测试的多因子评分。

评分因子及权重：
- 强主线状态 (mainline_status): 0-20 分
- 二级行业成交金额排名 (industry_rank): 0-10 分
- AB 涨幅 (ab_gain): 0-15 分
- BC 回撤健康度 (bc_retracement_health): 0-15 分
- 距离 C 点低点 (distance_to_c): 0-10 分
- 个股流动性 (liquidity): 0-10 分
- 周线方向 (weekly_filter): 0-5 分
- 年线过滤 (annual_filter): 0-5 分
- 行业集中度惩罚 (industry_concentration): -10-0 分

满分约 90 分（不含行业集中度惩罚时上限 100）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suishi_north_backtest.mainline import MainlineStatus


@dataclass(frozen=True)
class ScoringContext:
    """评分所需的全部上下文信息。"""

    mainline_status: str
    industry_rank: int
    industry_amount: float
    stock_amount: float
    same_industry_candidate_count: int


@dataclass(frozen=True)
class ScoreBreakdown:
    """评分各因子的明细。"""

    mainline_score: float
    industry_rank_score: float
    ab_gain_score: float
    bc_retracement_score: float
    distance_to_c_score: float
    liquidity_score: float
    weekly_filter_score: float
    annual_filter_score: float
    industry_concentration_penalty: float
    total: float

    def to_dict(self) -> dict[str, float]:
        return {
            "mainline": self.mainline_score,
            "industry_rank": self.industry_rank_score,
            "ab_gain": self.ab_gain_score,
            "bc_retracement": self.bc_retracement_score,
            "distance_to_c": self.distance_to_c_score,
            "liquidity": self.liquidity_score,
            "weekly_filter": self.weekly_filter_score,
            "annual_filter": self.annual_filter_score,
            "concentration_penalty": self.industry_concentration_penalty,
            "total": self.total,
        }

    def to_csv_string(self) -> str:
        parts = [f"{k}={v:.1f}" for k, v in self.to_dict().items()]
        return "; ".join(parts)


def score_candidate(
    ab_gain_pct: float,
    bc_retracement_pct: float,
    distance_to_c_pct: float,
    weekly_filter_passed: bool,
    annual_filter_passed: bool,
    context: ScoringContext,
) -> tuple[float, ScoreBreakdown]:
    """对单个候选进行多因子评分。

    Args:
        ab_gain_pct: AB 段涨幅百分比（如 50.0 表示 50%）。
        bc_retracement_pct: BC 回撤占 AB 涨幅的百分比（如 33.33 表示 33.33%）。
        distance_to_c_pct: 信号日收盘价距离 C 点低点的百分比。
        weekly_filter_passed: 周线方向过滤是否通过。
        annual_filter_passed: 年线弱结构过滤是否通过。
        context: 评分所需的上下文信息。

    Returns:
        (total_score, breakdown) 元组。
    """
    mainline_score = _score_mainline_status(context.mainline_status)
    industry_rank_score = _score_industry_rank(context.industry_rank)
    ab_gain_score = _score_ab_gain(ab_gain_pct)
    bc_retracement_score = _score_bc_retracement(bc_retracement_pct)
    distance_to_c_score = _score_distance_to_c(distance_to_c_pct)
    liquidity_score = _score_liquidity(context.stock_amount)
    weekly_filter_score = 5.0 if weekly_filter_passed else 0.0
    annual_filter_score = 5.0 if annual_filter_passed else 0.0
    concentration_penalty = _penalty_industry_concentration(
        context.same_industry_candidate_count
    )

    total = (
        mainline_score
        + industry_rank_score
        + ab_gain_score
        + bc_retracement_score
        + distance_to_c_score
        + liquidity_score
        + weekly_filter_score
        + annual_filter_score
        + concentration_penalty
    )

    breakdown = ScoreBreakdown(
        mainline_score=round(mainline_score, 2),
        industry_rank_score=round(industry_rank_score, 2),
        ab_gain_score=round(ab_gain_score, 2),
        bc_retracement_score=round(bc_retracement_score, 2),
        distance_to_c_score=round(distance_to_c_score, 2),
        liquidity_score=round(liquidity_score, 2),
        weekly_filter_score=round(weekly_filter_score, 2),
        annual_filter_score=round(annual_filter_score, 2),
        industry_concentration_penalty=round(concentration_penalty, 2),
        total=round(total, 2),
    )

    return total, breakdown


# -- 各因子评分函数 --


def _score_mainline_status(status: str) -> float:
    """强主线 20 分，观察 10 分，启动 5 分，无 0 分。"""
    if status == "strong":
        return 20.0
    if status == "observation":
        return 10.0
    if status == "startup":
        return 5.0
    return 0.0


def _score_industry_rank(rank: int) -> float:
    """行业成交金额排名：rank=1 得 10 分，rank=2 得 8 分，依次递减至 0。"""
    if rank <= 0:
        return 0.0
    if rank == 1:
        return 10.0
    if rank == 2:
        return 8.0
    if rank == 3:
        return 6.0
    if rank == 4:
        return 4.0
    if rank == 5:
        return 2.0
    return 0.0


def _score_ab_gain(ab_gain_pct: float) -> float:
    """AB 涨幅评分：线性映射到 0-15 分。

    ab_gain_pct >= 50% 满分 15 分，20% 为最小阈值得 0 分，中间线性插值。
    """
    if ab_gain_pct <= 20.0:
        return 0.0
    if ab_gain_pct >= 50.0:
        return 15.0
    return (ab_gain_pct - 20.0) / 30.0 * 15.0


def _score_bc_retracement(bc_retracement_pct: float) -> float:
    """BC 回撤健康度：回撤越浅得分越高。

    bc_retracement_pct=0 得 15 分（无回撤），=60% 得 0 分（最大允许回撤）。
    """
    if bc_retracement_pct <= 0.0:
        return 15.0
    if bc_retracement_pct >= 60.0:
        return 0.0
    return (60.0 - bc_retracement_pct) / 60.0 * 15.0


def _score_distance_to_c(distance_pct: float) -> float:
    """距离 C 点越近得分越高。

    distance=0 得 10 分，>=8% 得 0 分。
    """
    if distance_pct <= 0.0:
        return 10.0
    if distance_pct >= 8.0:
        return 0.0
    return (8.0 - distance_pct) / 8.0 * 10.0


def _score_liquidity(stock_amount: float) -> float:
    """个股流动性评分。

    amount >= 10 亿满分 10 分，<= 1 亿 0 分，中间线性插值。
    """
    threshold_low = 1_0000_0000.0  # 1 亿
    threshold_high = 10_0000_0000.0  # 10 亿
    if stock_amount <= threshold_low:
        return 0.0
    if stock_amount >= threshold_high:
        return 10.0
    return (stock_amount - threshold_low) / (threshold_high - threshold_low) * 10.0


def _penalty_industry_concentration(candidate_count: int) -> float:
    """行业集中度惩罚。

    同一行业候选 <= 2 不惩罚，>= 5 每个候选惩罚 2 分，中间线性。
    """
    if candidate_count <= 2:
        return 0.0
    if candidate_count >= 5:
        return -10.0
    return -(candidate_count - 2) / 3.0 * 10.0
