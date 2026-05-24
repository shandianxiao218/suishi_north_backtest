"""双轨组合回测测试。

验证 pure_structure 和 mainline_filtered 两条独立轨道的行为：
- pure_structure：接受所有结构候选，不使用主线过滤
- mainline_filtered：只接受强主线行业候选
- 两条轨道共享相同的执行成本参数
- 两条轨道独立维护现金、持仓、交易和净值
"""
from __future__ import annotations

import pytest

from suishi_north_backtest.execution import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_STAMP_TAX_RATE,
)
from suishi_north_backtest.mainline import MainlineStatus
from suishi_north_backtest.market_data import IndustryDailyAmount
from suishi_north_backtest.signals import CandidateSignal
from suishi_north_backtest.tracks import (
    Track,
    run_dual_tracks,
)


# ---- 辅助函数 ----


def candidate(
    symbol: str = "000001",
    signal_date: str = "2024-01-10",
    industry_level2: str = "电子",
    c_price: float = 10.0,
) -> CandidateSignal:
    return CandidateSignal(
        signal_date=signal_date,
        symbol=symbol,
        a_date="2024-01-02",
        a_price=8.0,
        b_date="2024-01-05",
        b_price=11.0,
        c_date="2024-01-08",
        c_price=c_price,
        ab_gain_pct=37.5,
        bc_retracement_pct=33.3,
        distance_to_c_pct=3.0,
    )


def make_mainline_data(
    industry: str = "电子",
    dates: list[str] | None = None,
    status: str = "strong",
) -> dict[str, dict[str, tuple[MainlineStatus, int, float]]]:
    """构造主线数据，返回 date -> {industry: (status, rank, amount)} 映射。"""
    if dates is None:
        dates = ["2024-01-10"]
    result: dict[str, dict[str, tuple[MainlineStatus, int, float]]] = {}
    for d in dates:
        result[d] = {
            industry: (MainlineStatus(status), 1, 5_000_000_000.0),
            "其他行业": (MainlineStatus.NONE, 10, 100_000_000.0),
        }
    return result


# ---- 测试 ----


def test_pure_structure_track_accepts_non_mainline_candidate() -> None:
    """pure_structure 轨道接受非强主线候选。

    即使候选所属行业不在强主线列表中，pure_structure 也应该接受该候选。
    """
    cands = [candidate(industry_level2="冷门行业")]
    mainline_map = make_mainline_data(industry="电子")
    industry_map = {"000001": "冷门行业"}

    track = Track(name="pure_structure", initial_cash=1_000_000.0)
    accepted = track.filter_candidates(
        cands, mainline_map, signal_date="2024-01-10",
        industry_map=industry_map,
    )

    assert len(accepted) == 1
    assert accepted[0].symbol == "000001"


def test_mainline_filtered_track_skips_non_strong_mainline_candidate() -> None:
    """mainline_filtered 轨道跳过非强主线候选。

    只有强主线行业的候选才能通过过滤。
    """
    cands = [candidate(industry_level2="冷门行业")]
    mainline_map = make_mainline_data(industry="电子")
    industry_map = {"000001": "冷门行业"}

    track = Track(name="mainline_filtered", initial_cash=1_000_000.0)
    accepted = track.filter_candidates(
        cands, mainline_map, signal_date="2024-01-10",
        industry_map=industry_map,
    )

    assert len(accepted) == 0


def test_mainline_filtered_track_accepts_strong_mainline_candidate() -> None:
    """mainline_filtered 轨道接受强主线行业候选。"""
    cands = [candidate(industry_level2="电子")]
    mainline_map = make_mainline_data(industry="电子")
    industry_map = {"000001": "电子"}

    track = Track(name="mainline_filtered", initial_cash=1_000_000.0)
    accepted = track.filter_candidates(
        cands, mainline_map, signal_date="2024-01-10",
        industry_map=industry_map,
    )

    assert len(accepted) == 1


def test_tracks_use_same_execution_costs() -> None:
    """两条轨道使用相同的执行成本参数。

    佣金、滑点、印花税等成本参数必须一致。
    """
    track_a = Track(name="pure_structure", initial_cash=1_000_000.0)
    track_b = Track(name="mainline_filtered", initial_cash=1_000_000.0)

    assert track_a.commission_rate == track_b.commission_rate
    assert track_a.slippage_rate == track_b.slippage_rate
    assert track_a.stamp_tax_rate == track_b.stamp_tax_rate

    # 默认值与 execution 模块一致
    assert track_a.commission_rate == DEFAULT_COMMISSION_RATE
    assert track_a.slippage_rate == DEFAULT_SLIPPAGE_RATE
    assert track_a.stamp_tax_rate == DEFAULT_STAMP_TAX_RATE


def test_tracks_have_independent_cash_and_positions() -> None:
    """两条轨道独立维护现金和持仓。

    一条轨道的买入不影响另一条轨道的现金和持仓。
    """
    cands = [candidate()]
    mainline_map = make_mainline_data(industry="电子")
    industry_map = {"000001": "电子"}

    track_a = Track(name="pure_structure", initial_cash=1_000_000.0)
    track_b = Track(name="mainline_filtered", initial_cash=1_000_000.0)

    # track_a 买入
    accepted_a = track_a.filter_candidates(
        cands, mainline_map, signal_date="2024-01-10",
        industry_map=industry_map,
    )
    buy_result = track_a.execute_buy(
        candidate=accepted_a[0],
        open_price=10.5,
    )

    assert buy_result.executed
    assert track_a.cash < 1_000_000.0
    assert len(track_a.positions) > 0

    # track_b 未受影响
    assert track_b.cash == 1_000_000.0
    assert len(track_b.positions) == 0


def test_track_comparison_uses_real_track_metrics() -> None:
    """track_comparison 输出使用真实轨道指标，不是镜像数据。

    两条轨道的指标必须从各自独立的交易结果计算，
    不能是同一条轨道的结果复制到两个 track。
    """
    cands_a = [candidate(symbol="000001", industry_level2="电子")]
    cands_b = [candidate(symbol="000002", industry_level2="银行")]

    mainline_map = make_mainline_data(industry="电子")
    industry_map = {"000001": "电子", "000002": "银行"}

    track_a = Track(name="pure_structure", initial_cash=1_000_000.0)
    track_b = Track(name="mainline_filtered", initial_cash=1_000_000.0)

    # track_a 接受所有候选
    accepted_a = track_a.filter_candidates(
        cands_a, mainline_map, signal_date="2024-01-10",
        industry_map=industry_map,
    )
    assert len(accepted_a) == 1
    buy_a = track_a.execute_buy(candidate=accepted_a[0], open_price=10.5)
    assert buy_a.executed

    # track_b 只接受强主线（电子是强主线，但候选 000002 属于银行）
    accepted_b = track_b.filter_candidates(
        cands_b, mainline_map, signal_date="2024-01-10",
        industry_map=industry_map,
    )
    # 银行不是强主线，所以 track_b 不接受
    assert len(accepted_b) == 0

    # 指标必须反映真实差异
    metrics_a = track_a.compute_metrics()
    metrics_b = track_b.compute_metrics()

    # track_a 有持仓，track_b 没有，指标应该不同
    assert metrics_a["trade_count"] != metrics_b["trade_count"]
    assert metrics_a["trade_count"] == 1
    assert metrics_b["trade_count"] == 0

    # track_comparison 不能是简单的镜像
    comparison = run_dual_tracks._build_comparison(
        metrics_a, metrics_b,
    )
    assert comparison is not None
    assert len(comparison) > 0
    # trade_count 行必须反映真实差异
    tc_row = [r for r in comparison if r["metric"] == "trade_count"]
    assert len(tc_row) == 1
    assert tc_row[0]["pure_structure_track"] != tc_row[0]["mainline_filtered_track"]
