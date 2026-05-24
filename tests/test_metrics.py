"""测试 metrics.py 指标计算模块。

覆盖 Issue #36 要求的测试：
- test_total_return
- test_max_drawdown
- test_annualized_return
- test_volatility
- test_benchmark_excess_return
- test_sample_windows_are_split_correctly
- test_missing_benchmark_is_reported

额外测试：
- test_build_benchmark_comparison_rows_not_copies
- test_equity_curve_in_window_filters_correctly
- test_benchmark_return_in_window_filters_correctly
"""
from __future__ import annotations

from datetime import date

from suishi_north_backtest.market_data import IndexDaily
from suishi_north_backtest.metrics import (
    EquityPoint,
    EquityMetrics,
    annualized_return,
    benchmark_return_in_window,
    build_benchmark_comparison_rows,
    compare_with_benchmarks,
    equity_curve_in_window,
    evaluate_equity_curve,
    evaluate_sample_windows,
    excess_return,
    max_drawdown,
    return_drawdown_ratio,
    sample_windows,
    total_return,
    trade_count,
    volatility,
    win_rate,
)


# --- 旧接口测试（保留） ---


def _ep(d: str, equity: float) -> dict[str, object]:
    """快捷构造 dict-based equity point。"""
    return {"date": d, "equity": equity}


class TestLegacyEquityPointAPI:
    """旧 EquityPoint / EquityMetrics 接口测试。"""

    def test_evaluates_equity_curve_return_drawdown_and_ratio(self) -> None:
        metrics = evaluate_equity_curve(
            [
                EquityPoint(date(2024, 1, 1), 1_000_000),
                EquityPoint(date(2024, 1, 2), 1_100_000),
                EquityPoint(date(2024, 1, 3), 1_000_000),
                EquityPoint(date(2024, 1, 4), 1_200_000),
            ]
        )
        assert round(metrics.cumulative_return, 4) == 0.2000
        assert round(metrics.max_drawdown, 4) == 0.0909
        assert round(metrics.return_drawdown_ratio, 4) == 2.2000

    def test_compares_strategy_equity_curve_with_required_benchmarks(self) -> None:
        strategy = [
            EquityPoint(date(2024, 1, 1), 1_000_000),
            EquityPoint(date(2024, 1, 2), 1_200_000),
        ]
        benchmarks = {
            "沪深300": [
                EquityPoint(date(2024, 1, 1), 1000),
                EquityPoint(date(2024, 1, 2), 1100),
            ],
            "中证500": [
                EquityPoint(date(2024, 1, 1), 1000),
                EquityPoint(date(2024, 1, 2), 900),
            ],
            "中证1000": [
                EquityPoint(date(2024, 1, 1), 1000),
                EquityPoint(date(2024, 1, 2), 1000),
            ],
        }
        comparisons = compare_with_benchmarks(strategy, benchmarks)
        assert set(comparisons) == {"沪深300", "中证500", "中证1000"}
        assert round(comparisons["沪深300"].excess_return, 4) == 0.1000
        assert round(comparisons["中证500"].excess_return, 4) == 0.3000
        assert round(comparisons["中证1000"].excess_return, 4) == 0.2000

    def test_evaluates_in_sample_out_of_sample_and_recent_windows(self) -> None:
        points = [
            EquityPoint(date(2022, 12, 30), 1_000_000),
            EquityPoint(date(2022, 12, 31), 1_100_000),
            EquityPoint(date(2023, 1, 1), 1_100_000),
            EquityPoint(date(2023, 12, 31), 1_210_000),
            EquityPoint(date(2024, 1, 1), 1_210_000),
            EquityPoint(date(2024, 12, 31), 1_331_000),
        ]
        windows = evaluate_sample_windows(points)
        assert round(windows["样本内"].cumulative_return, 4) == 0.1000
        assert round(windows["样本外"].cumulative_return, 4) == 0.2100
        assert round(windows["近期窗口"].cumulative_return, 4) == 0.1000


# --- Issue #36 新接口测试 ---


class TestTotalReturn:
    """test_total_return"""

    def test_positive_return(self) -> None:
        curve = [_ep("2024-01-01", 100), _ep("2024-01-02", 110), _ep("2024-01-03", 120)]
        assert total_return(curve) == 0.2

    def test_negative_return(self) -> None:
        curve = [_ep("2024-01-01", 100), _ep("2024-01-02", 90)]
        assert total_return(curve) == -0.1

    def test_empty_curve(self) -> None:
        assert total_return([]) == 0.0

    def test_single_point(self) -> None:
        assert total_return([_ep("2024-01-01", 100)]) == 0.0

    def test_zero_start_equity(self) -> None:
        curve = [_ep("2024-01-01", 0), _ep("2024-01-02", 100)]
        assert total_return(curve) == 0.0


class TestMaxDrawdown:
    """test_max_drawdown"""

    def test_with_drawdown(self) -> None:
        # peak=120, trough=110 -> dd = 10/120 = 0.0833...
        curve = [_ep("2024-01-01", 100), _ep("2024-01-02", 120), _ep("2024-01-03", 110), _ep("2024-01-04", 130)]
        dd = max_drawdown(curve)
        assert abs(dd - 10 / 120) < 1e-6

    def test_monotonically_increasing(self) -> None:
        curve = [_ep("2024-01-01", 100), _ep("2024-01-02", 110), _ep("2024-01-03", 120)]
        assert max_drawdown(curve) == 0.0

    def test_empty_curve(self) -> None:
        assert max_drawdown([]) == 0.0

    def test_flat_curve(self) -> None:
        curve = [_ep("2024-01-01", 100), _ep("2024-01-02", 100)]
        assert max_drawdown(curve) == 0.0


class TestAnnualizedReturn:
    """test_annualized_return"""

    def test_one_year_exact(self) -> None:
        # 242 trading days ~ 1 calendar year, 10% return
        curve = [_ep("2023-01-01", 100), _ep("2023-12-31", 110)]
        ar = annualized_return(curve, trading_days_per_year=242)
        assert abs(ar - 0.1) < 0.02  # approximately 10%

    def test_two_years(self) -> None:
        # 2 calendar years, 21% total -> ~10% annualized
        curve = [_ep("2022-01-01", 100), _ep("2023-12-31", 121)]
        ar = annualized_return(curve, trading_days_per_year=242)
        assert abs(ar - 0.1) < 0.02

    def test_empty_curve(self) -> None:
        assert annualized_return([]) == 0.0

    def test_single_point(self) -> None:
        assert annualized_return([_ep("2024-01-01", 100)]) == 0.0


class TestVolatility:
    """test_volatility"""

    def test_constant_curve(self) -> None:
        curve = [_ep("2024-01-01", 100), _ep("2024-01-02", 100), _ep("2024-01-03", 100)]
        assert volatility(curve) == 0.0

    def test_normal_curve(self) -> None:
        curve = [_ep("2024-01-01", 100), _ep("2024-01-02", 105), _ep("2024-01-03", 100)]
        vol = volatility(curve)
        assert vol > 0.0

    def test_empty_curve(self) -> None:
        assert volatility([]) == 0.0

    def test_single_point(self) -> None:
        assert volatility([_ep("2024-01-01", 100)]) == 0.0

    def test_two_points(self) -> None:
        curve = [_ep("2024-01-01", 100), _ep("2024-01-02", 110)]
        assert volatility(curve) == 0.0  # only 1 return, need >=2 for std


class TestBenchmarkExcessReturn:
    """test_benchmark_excess_return"""

    def test_positive_excess(self) -> None:
        assert excess_return(0.10, 0.05) == 0.05

    def test_negative_excess(self) -> None:
        assert excess_return(-0.05, 0.02) == -0.07

    def test_both_zero(self) -> None:
        assert excess_return(0.0, 0.0) == 0.0


class TestSampleWindowsSplitCorrectly:
    """test_sample_windows_are_split_correctly"""

    def test_window_dates(self) -> None:
        windows = sample_windows("2024-06-30")
        assert windows["sample_in"] == ("2018-01-01", "2022-12-31")
        assert windows["sample_out"] == ("2023-01-01", "2024-06-30")
        assert windows["recent"] == ("2024-01-01", "2024-06-30")

    def test_start_before_end(self) -> None:
        windows = sample_windows("2024-12-31")
        for _name, (start, end) in windows.items():
            assert start <= end

    def test_sample_out_contains_recent(self) -> None:
        windows = sample_windows("2024-06-30")
        so_start, so_end = windows["sample_out"]
        r_start, r_end = windows["recent"]
        assert so_start <= r_start
        assert so_end >= r_end


class TestMissingBenchmarkIsReported:
    """test_missing_benchmark_is_reported"""

    def test_missing_benchmark_zero_return_with_audit(self) -> None:
        # 只有 CSI300 数据，缺少 CSI500 和 CSI1000
        index_daily = [
            IndexDaily("2023-01-02", "000300", None, None, None, 3000.0, None, None),
            IndexDaily("2024-06-28", "000300", None, None, None, 3300.0, None, None),
        ]
        equity = [
            _ep("2024-01-01", 1_000_000),
            _ep("2024-06-30", 1_100_000),
        ]
        rows = build_benchmark_comparison_rows(
            equity_curve=equity,
            index_daily=index_daily,
            as_of="2024-06-30",
        )
        # CSI500 and CSI1000 should have benchmark_return 0.00 and audit note about missing data
        csi500_rows = [r for r in rows if r["benchmark"] == "CSI500"]
        assert len(csi500_rows) >= 1
        for row in csi500_rows:
            assert row["benchmark_return"] == "0.00"
            assert "缺少" in str(row["audit_note"]) or "不足" in str(row["audit_note"])

        csi1000_rows = [r for r in rows if r["benchmark"] == "CSI1000"]
        assert len(csi1000_rows) >= 1
        for row in csi1000_rows:
            assert row["benchmark_return"] == "0.00"


class TestBenchmarkReturnInWindow:
    """test_benchmark_return_in_window_filters_correctly"""

    def test_filters_to_window(self) -> None:
        index_daily = [
            IndexDaily("2020-01-02", "000300", None, None, None, 3000.0, None, None),
            IndexDaily("2021-06-30", "000300", None, None, None, 3600.0, None, None),
            IndexDaily("2023-06-30", "000300", None, None, None, 3300.0, None, None),
        ]
        # Full range: 3000 -> 3300 = 10%
        # 2021 only: 3000 -> 3600 = 20%
        ret_full = benchmark_return_in_window(index_daily, "CSI300", "2020-01-01", "2023-12-31")
        ret_2021 = benchmark_return_in_window(index_daily, "CSI300", "2020-01-01", "2021-12-31")
        assert abs(ret_full - 0.1) < 1e-4
        assert abs(ret_2021 - 0.2) < 1e-4

    def test_out_of_range_returns_zero(self) -> None:
        index_daily = [
            IndexDaily("2020-01-02", "000300", None, None, None, 3000.0, None, None),
            IndexDaily("2020-12-31", "000300", None, None, None, 3300.0, None, None),
        ]
        ret = benchmark_return_in_window(index_daily, "CSI300", "2025-01-01", "2025-12-31")
        assert ret == 0.0


class TestEquityCurveInWindow:
    """test_equity_curve_in_window_filters_correctly"""

    def test_filters_to_window(self) -> None:
        curve = [
            _ep("2022-06-01", 100),
            _ep("2023-01-15", 110),
            _ep("2024-03-01", 120),
        ]
        result = equity_curve_in_window(curve, "2023-01-01", "2023-12-31")
        assert len(result) == 1
        assert result[0]["date"] == "2023-01-15"

    def test_empty_result(self) -> None:
        curve = [_ep("2023-01-01", 100)]
        result = equity_curve_in_window(curve, "2025-01-01", "2025-12-31")
        assert result == []


class TestBuildBenchmarkComparisonRowsNotCopies:
    """test_build_benchmark_comparison_rows_not_copies — 每个 period 数字不同。"""

    def test_different_periods_have_different_numbers(self) -> None:
        # 构造一条在不同 period 有不同收益的 equity curve
        equity = [
            _ep("2018-01-02", 1_000_000),
            _ep("2022-12-30", 1_200_000),  # sample_in: +20%
            _ep("2023-01-02", 1_200_000),
            _ep("2023-12-29", 1_080_000),  # sample_out: -10%
            _ep("2024-01-02", 1_080_000),
            _ep("2024-06-28", 1_188_000),  # recent: +10%
        ]
        index_daily = [
            IndexDaily("2018-01-02", "000300", None, None, None, 3000.0, None, None),
            IndexDaily("2022-12-30", "000300", None, None, None, 3600.0, None, None),
            IndexDaily("2023-01-02", "000300", None, None, None, 3600.0, None, None),
            IndexDaily("2023-12-29", "000300", None, None, None, 3420.0, None, None),
            IndexDaily("2024-01-02", "000300", None, None, None, 3420.0, None, None),
            IndexDaily("2024-06-28", "000300", None, None, None, 3591.0, None, None),
        ]
        rows = build_benchmark_comparison_rows(
            equity_curve=equity,
            index_daily=index_daily,
            as_of="2024-06-30",
        )

        csi300_rows = {r["period"]: r for r in rows if r["benchmark"] == "CSI300"}

        si_strat = csi300_rows["sample_in"]["strategy_return"]
        so_strat = csi300_rows["sample_out"]["strategy_return"]
        r_strat = csi300_rows["recent"]["strategy_return"]

        # 三个 period 的 strategy_return 必须不同
        assert si_strat != so_strat, f"sample_in={si_strat} should != sample_out={so_strat}"
        assert so_strat != r_strat, f"sample_out={so_strat} should != recent={r_strat}"

        # 三个 period 的 benchmark_return 也必须不同
        si_bench = csi300_rows["sample_in"]["benchmark_return"]
        so_bench = csi300_rows["sample_out"]["benchmark_return"]
        r_bench = csi300_rows["recent"]["benchmark_return"]
        assert si_bench != so_bench, f"bench sample_in={si_bench} should != sample_out={so_bench}"
        assert so_bench != r_bench, f"bench sample_out={so_bench} should != recent={r_bench}"

        # 验收标准核心：audit_note 包含 window 边界
        for row in rows:
            assert "window=[" in str(row["audit_note"])


class TestWinRate:
    """test_win_rate"""

    def test_all_wins(self) -> None:
        trades = [
            {"net_pnl": 100.0},
            {"net_pnl": 50.0},
            {"net_pnl": 200.0},
        ]
        assert win_rate(trades) == 1.0

    def test_mixed(self) -> None:
        trades = [
            {"net_pnl": 100.0},
            {"net_pnl": -50.0},
            {"net_pnl": 0.0},
        ]
        assert win_rate(trades) == 1 / 3

    def test_empty(self) -> None:
        assert win_rate([]) == 0.0

    def test_all_losses(self) -> None:
        trades = [{"net_pnl": -10.0}, {"net_pnl": -20.0}]
        assert win_rate(trades) == 0.0


class TestTradeCount:
    """test_trade_count"""

    def test_count(self) -> None:
        trades = [{"net_pnl": 1.0}, {"net_pnl": 2.0}, {"net_pnl": 3.0}]
        assert trade_count(trades) == 3

    def test_empty(self) -> None:
        assert trade_count([]) == 0
