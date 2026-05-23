"""测试 scoring.py 候选评分与排序模块。

覆盖 Issue #34 要求的 5 个测试：
- test_strong_mainline_candidate_scores_higher
- test_closer_to_c_scores_higher
- test_healthier_bc_retracement_scores_higher
- test_low_liquidity_penalty
- test_scoring_is_deterministic
"""
from __future__ import annotations

from suishi_north_backtest.scoring import ScoringContext, score_candidate


def _default_context(**overrides) -> ScoringContext:
    defaults = {
        "mainline_status": "strong",
        "industry_rank": 1,
        "industry_amount": 5_0000_0000.0,
        "stock_amount": 5_0000_0000.0,
        "same_industry_candidate_count": 1,
    }
    defaults.update(overrides)
    return ScoringContext(**defaults)


class TestStrongMainlineCandidateScoresHigher:
    """强主线候选的评分应高于非强主线候选。"""

    def test_strong_vs_none(self) -> None:
        ctx_strong = _default_context(mainline_status="strong")
        ctx_none = _default_context(mainline_status="none")
        score_strong, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx_strong,
        )
        score_none, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx_none,
        )
        assert score_strong > score_none, (
            f"强主线评分 {score_strong} 应高于无主线评分 {score_none}"
        )

    def test_strong_vs_observation(self) -> None:
        ctx_strong = _default_context(mainline_status="strong")
        ctx_obs = _default_context(mainline_status="observation")
        score_strong, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx_strong,
        )
        score_obs, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx_obs,
        )
        assert score_strong > score_obs

    def test_mainline_status_ordering(self) -> None:
        """评分顺序：strong > observation > startup > none。"""
        scores = {}
        for status in ("strong", "observation", "startup", "none"):
            ctx = _default_context(mainline_status=status)
            s, _ = score_candidate(
                ab_gain_pct=30.0,
                bc_retracement_pct=30.0,
                distance_to_c_pct=4.0,
                weekly_filter_passed=True,
                annual_filter_passed=True,
                context=ctx,
            )
            scores[status] = s
        assert scores["strong"] > scores["observation"] > scores["startup"] > scores["none"]


class TestCloserToCScoresHigher:
    """距离 C 点越近，评分越高。"""

    def test_zero_distance_scores_highest(self) -> None:
        ctx = _default_context()
        score_close, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=0.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        score_far, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=7.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert score_close > score_far

    def test_at_threshold_scores_zero(self) -> None:
        """distance >= 8% 时，distance 因子得 0 分。"""
        ctx = _default_context()
        _, bd_at = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=8.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        _, bd_below = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=0.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert bd_at.distance_to_c_score == 0.0
        assert bd_below.distance_to_c_score == 10.0

    def test_monotonic_decrease(self) -> None:
        """距离越大，distance 因子得分单调递减。"""
        ctx = _default_context()
        prev_score = 10.0
        for dist in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]:
            _, bd = score_candidate(
                ab_gain_pct=30.0,
                bc_retracement_pct=30.0,
                distance_to_c_pct=dist,
                weekly_filter_passed=True,
                annual_filter_passed=True,
                context=ctx,
            )
            assert bd.distance_to_c_score <= prev_score, (
                f"distance={dist} 得分 {bd.distance_to_c_score} 应 <= 前一个 {prev_score}"
            )
            prev_score = bd.distance_to_c_score


class TestHealthierBcRetracementScoresHigher:
    """BC 回撤越浅（越健康），评分越高。"""

    def test_shallow_retracement_scores_higher(self) -> None:
        ctx = _default_context()
        score_healthy, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=10.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        score_deep, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=50.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert score_healthy > score_deep

    def test_zero_retracement_is_best(self) -> None:
        ctx = _default_context()
        _, bd = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=0.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert bd.bc_retracement_score == 15.0

    def test_max_retracement_is_zero(self) -> None:
        ctx = _default_context()
        _, bd = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=60.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert bd.bc_retracement_score == 0.0

    def test_monotonic_decrease(self) -> None:
        ctx = _default_context()
        prev_score = 15.0
        for retracement in [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]:
            _, bd = score_candidate(
                ab_gain_pct=30.0,
                bc_retracement_pct=retracement,
                distance_to_c_pct=4.0,
                weekly_filter_passed=True,
                annual_filter_passed=True,
                context=ctx,
            )
            assert bd.bc_retracement_score <= prev_score
            prev_score = bd.bc_retracement_score


class TestLowLiquidityPenalty:
    """低流动性候选应受到惩罚。"""

    def test_low_liquidity_scores_lower(self) -> None:
        ctx_high = _default_context(stock_amount=10_0000_0000.0)
        ctx_low = _default_context(stock_amount=5000_0000.0)
        score_high, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx_high,
        )
        score_low, _ = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx_low,
        )
        assert score_high > score_low

    def test_below_threshold_liquidity_score_is_zero(self) -> None:
        ctx = _default_context(stock_amount=5000_0000.0)
        _, bd = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert bd.liquidity_score == 0.0

    def test_at_threshold_liquidity_score_is_zero(self) -> None:
        ctx = _default_context(stock_amount=1_0000_0000.0)
        _, bd = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert bd.liquidity_score == 0.0

    def test_high_liquidity_score_is_max(self) -> None:
        ctx = _default_context(stock_amount=10_0000_0000.0)
        _, bd = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert bd.liquidity_score == 10.0


class TestScoringIsDeterministic:
    """评分必须是确定性的：相同输入必须得到相同输出。"""

    def test_same_inputs_same_score(self) -> None:
        ctx = _default_context()
        kwargs = dict(
            ab_gain_pct=35.0,
            bc_retracement_pct=25.0,
            distance_to_c_pct=3.5,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        score1, bd1 = score_candidate(**kwargs)
        score2, bd2 = score_candidate(**kwargs)
        assert score1 == score2
        assert bd1 == bd2

    def test_repeated_calls_stable(self) -> None:
        ctx = _default_context()
        kwargs = dict(
            ab_gain_pct=42.0,
            bc_retracement_pct=18.0,
            distance_to_c_pct=2.1,
            weekly_filter_passed=False,
            annual_filter_passed=True,
            context=ctx,
        )
        scores = [score_candidate(**kwargs)[0] for _ in range(100)]
        assert len(set(scores)) == 1, f"评分不稳定：{set(scores)}"

    def test_breakdown_to_csv_string_roundtrip(self) -> None:
        ctx = _default_context()
        _, bd = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        csv_str = bd.to_csv_string()
        assert "mainline=" in csv_str
        assert "total=" in csv_str
        # 解析回来验证
        parts = csv_str.split("; ")
        parsed = {}
        for part in parts:
            k, v = part.split("=")
            parsed[k] = float(v)
        assert abs(parsed["total"] - bd.total) < 0.1


class TestIndustryConcentrationPenalty:
    """行业集中度惩罚测试。"""

    def test_no_penalty_for_few_candidates(self) -> None:
        ctx = _default_context(same_industry_candidate_count=1)
        _, bd = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert bd.industry_concentration_penalty == 0.0

    def test_penalty_for_many_candidates(self) -> None:
        ctx = _default_context(same_industry_candidate_count=5)
        _, bd = score_candidate(
            ab_gain_pct=30.0,
            bc_retracement_pct=30.0,
            distance_to_c_pct=4.0,
            weekly_filter_passed=True,
            annual_filter_passed=True,
            context=ctx,
        )
        assert bd.industry_concentration_penalty == -10.0

    def test_penalty_increases_with_count(self) -> None:
        prev_penalty = 0.0
        for count in [2, 3, 4, 5]:
            ctx = _default_context(same_industry_candidate_count=count)
            _, bd = score_candidate(
                ab_gain_pct=30.0,
                bc_retracement_pct=30.0,
                distance_to_c_pct=4.0,
                weekly_filter_passed=True,
                annual_filter_passed=True,
                context=ctx,
            )
            assert bd.industry_concentration_penalty <= prev_penalty
            prev_penalty = bd.industry_concentration_penalty
