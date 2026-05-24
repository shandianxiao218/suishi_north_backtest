"""测试 metrics.py 指标计算模块。

覆盖 Issue #36 要求的测试：
- test_total_return
- test_max_drawdown
- test_annualized_return
- test_volatility
- test_benchmark_excess_return
- test_sample_windows_are_split_correctly
- test_missing_benchmark_is_reported

整改要求补充：
- benchmark_comparison 输出同时包含策略侧和基准侧指标
- win_rate / trade_count 按 period 正确统计
- 真实 0% benchmark return 不被误报为缺失
- 缺少基准数据时 benchmark_status 明确标记
- 三个 period 独立计算，不复制全周期数字
- sample_in / sample_out / recent 精确期望值断言
"""
from __future__ import annotations

from datetime import date

from suishi_north_backtest.market_data import IndexDaily
from suishi_north_backtest.metrics import (
    BenchmarkResult,
    EquityPoint,
    annualized_return,
    benchmark_metrics_in_window,
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


# --- 辅助构造 ---


def _ep(d: str, equity: float) -> dict[str, object]:
    return {"date": d, "equity": equity}


def _trade(exit_date: str, net_pnl: float) -> dict[str, object]:
    return {"exit_date": exit_date, "net_pnl": net_pnl}


# --- 共享测试数据 ---

# equity curve 跨 3 个 period，每个 period 有不同收益
EQUITY = [
    _ep("2018-01-02", 1_000_000),
    _ep("2022-12-30", 1_200_000),   # sample_in: +20%
    _ep("2023-01-02", 1_200_000),
    _ep("2023-12-29", 1_080_000),   # sample_out: -10%
    _ep("2024-01-02", 1_080_000),
    _ep("2024-06-28", 1_188_000),   # recent: +10%
]

# CSI300 基准: sample_in +20%, sample_out -5%, recent +5%
INDEX_DAILY = [
    IndexDaily("2018-01-02", "000300", None, None, None, 3000.0, None, None),
    IndexDaily("2022-12-30", "000300", None, None, None, 3600.0, None, None),
    IndexDaily("2023-01-02", "000300", None, None, None, 3600.0, None, None),
    IndexDaily("2023-12-29", "000300", None, None, None, 3420.0, None, None),
    IndexDaily("2024-01-02", "000300", None, None, None, 3420.0, None, None),
    IndexDaily("2024-06-28", "000300", None, None, None, 3591.0, None, None),
    # CSI500: sample_in +10%, sample_out -15%, recent +5%
    IndexDaily("2018-01-02", "000905", None, None, None, 5000.0, None, None),
    IndexDaily("2022-12-30", "000905", None, None, None, 5500.0, None, None),
    IndexDaily("2023-01-02", "000905", None, None, None, 5500.0, None, None),
    IndexDaily("2023-12-29", "000905", None, None, None, 4675.0, None, None),
    IndexDaily("2024-01-02", "000905", None, None, None, 4675.0, None, None),
    IndexDaily("2024-06-28", "000905", None, None, None, 4908.75, None, None),
    # CSI1000: 只有 sample_in 数据，其余 insufficient
    IndexDaily("2018-01-02", "000852", None, None, None, 1000.0, None, None),
    IndexDaily("2022-12-30", "000852", None, None, None, 1200.0, None, None),
]

# trades 跨 3 个 period
TRADES = [
    _trade("2022-06-15", 100.0),   # sample_in: win
    _trade("2023-06-15", -50.0),   # sample_out: loss
    _trade("2024-03-15", 200.0),   # recent: win
]

AS_OF = "2024-06-30"

ALL_ROWS = build_benchmark_comparison_rows(
    equity_curve=EQUITY,
    index_daily=INDEX_DAILY,
    as_of=AS_OF,
    trades=TRADES,
)


# --- 旧接口测试（保留） ---


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
        curve = [_ep("2023-01-01", 100), _ep("2023-12-31", 110)]
        ar = annualized_return(curve, trading_days_per_year=242)
        assert abs(ar - 0.1) < 0.02

    def test_two_years(self) -> None:
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
        assert volatility(curve) == 0.0


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


class TestWinRate:
    """test_win_rate"""

    def test_all_wins(self) -> None:
        trades = [{"net_pnl": 100.0}, {"net_pnl": 50.0}, {"net_pnl": 200.0}]
        assert win_rate(trades) == 1.0

    def test_mixed(self) -> None:
        trades = [{"net_pnl": 100.0}, {"net_pnl": -50.0}, {"net_pnl": 0.0}]
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


class TestBenchmarkMetricsInWindow:
    """基准指标按窗口计算，区分 ok / missing / insufficient_data。"""

    def test_ok_with_full_data(self) -> None:
        result = benchmark_metrics_in_window(INDEX_DAILY, "CSI300", "2018-01-01", "2022-12-31")
        assert result.status == "ok"
        assert abs(result.return_value - 0.2) < 1e-4   # 3000->3600 = +20%
        assert result.max_drawdown == 0.0               # 单调递增
        assert result.volatility == 0.0                  # 只有2点，无法算std

    def test_insufficient_data(self) -> None:
        result = benchmark_metrics_in_window(INDEX_DAILY, "CSI300", "2025-01-01", "2025-12-31")
        assert result.status == "insufficient_data"
        assert result.return_value == 0.0

    def test_missing_benchmark(self) -> None:
        result = benchmark_metrics_in_window([], "UNKNOWN", "2020-01-01", "2020-12-31")
        assert result.status == "missing"
        assert result.return_value == 0.0

    def test_true_zero_return_is_ok(self) -> None:
        """真实 0% 收益应返回 status=ok。"""
        data = [
            IndexDaily("2024-01-02", "000300", None, None, None, 3000.0, None, None),
            IndexDaily("2024-06-30", "000300", None, None, None, 3000.0, None, None),
        ]
        result = benchmark_metrics_in_window(data, "CSI300", "2024-01-01", "2024-12-31")
        assert result.status == "ok"
        assert result.return_value == 0.0

    def test_benchmark_max_drawdown(self) -> None:
        """基准指数有回撤时正确计算。"""
        data = [
            IndexDaily("2024-01-01", "000300", None, None, None, 100.0, None, None),
            IndexDaily("2024-06-01", "000300", None, None, None, 120.0, None, None),
            IndexDaily("2024-12-01", "000300", None, None, None, 108.0, None, None),
        ]
        result = benchmark_metrics_in_window(data, "CSI300", "2024-01-01", "2024-12-31")
        assert result.status == "ok"
        # peak=120, trough=108, dd = 12/120 = 0.1
        assert abs(result.max_drawdown - 0.1) < 1e-4


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


# --- 精确断言测试：benchmark_comparison 全量输出 ---


class TestBuildBenchmarkComparisonExactValues:
    """对 sample_in / sample_out / recent 做精确期望值断言。"""

    def _rows_for(self, benchmark: str) -> dict[str, dict[str, object]]:
        return {
            r["period"]: r
            for r in ALL_ROWS
            if r["benchmark"] == benchmark
        }

    # --- CSI300 sample_in 精确断言 ---

    def test_csi300_sample_in_strategy_return(self) -> None:
        row = self._rows_for("CSI300")["sample_in"]
        assert row["strategy_return"] == "20.00"

    def test_csi300_sample_in_benchmark_return(self) -> None:
        row = self._rows_for("CSI300")["sample_in"]
        assert row["benchmark_return"] == "20.00"

    def test_csi300_sample_in_benchmark_status(self) -> None:
        row = self._rows_for("CSI300")["sample_in"]
        assert row["benchmark_status"] == "ok"

    def test_csi300_sample_in_win_rate_and_trade_count(self) -> None:
        row = self._rows_for("CSI300")["sample_in"]
        assert row["strategy_win_rate"] == "100.00"
        assert row["strategy_trade_count"] == "1"

    # --- CSI300 sample_out 精确断言 ---
    # 策略: 1_200_000 -> 1_188_000 = -1%
    # CSI300: 3600 -> 3591 = -0.25%
    # trades: 2 trades (1 loss, 1 win) -> wr=50%

    def test_csi300_sample_out_strategy_return(self) -> None:
        row = self._rows_for("CSI300")["sample_out"]
        assert row["strategy_return"] == "-1.00"

    def test_csi300_sample_out_benchmark_return(self) -> None:
        row = self._rows_for("CSI300")["sample_out"]
        assert row["benchmark_return"] == "-0.25"

    def test_csi300_sample_out_benchmark_status(self) -> None:
        row = self._rows_for("CSI300")["sample_out"]
        assert row["benchmark_status"] == "ok"

    def test_csi300_sample_out_win_rate_and_trade_count(self) -> None:
        row = self._rows_for("CSI300")["sample_out"]
        assert row["strategy_win_rate"] == "50.00"
        assert row["strategy_trade_count"] == "2"

    # --- CSI300 recent 精确断言 ---

    def test_csi300_recent_strategy_return(self) -> None:
        row = self._rows_for("CSI300")["recent"]
        assert row["strategy_return"] == "10.00"

    def test_csi300_recent_benchmark_return(self) -> None:
        row = self._rows_for("CSI300")["recent"]
        assert row["benchmark_return"] == "5.00"

    def test_csi300_recent_benchmark_status(self) -> None:
        row = self._rows_for("CSI300")["recent"]
        assert row["benchmark_status"] == "ok"

    def test_csi300_recent_win_rate_and_trade_count(self) -> None:
        row = self._rows_for("CSI300")["recent"]
        assert row["strategy_win_rate"] == "100.00"
        assert row["strategy_trade_count"] == "1"

    # --- CSI500 精确断言 ---

    def test_csi500_sample_in_benchmark_return(self) -> None:
        row = self._rows_for("CSI500")["sample_in"]
        assert row["benchmark_return"] == "10.00"
        assert row["benchmark_status"] == "ok"

    # --- CSI500 sample_out: 5500 -> 4908.75 = -10.75% ---

    def test_csi500_sample_out_benchmark_return(self) -> None:
        row = self._rows_for("CSI500")["sample_out"]
        assert row["benchmark_return"] == "-10.75"
        assert row["benchmark_status"] == "ok"

    def test_csi500_recent_benchmark_return(self) -> None:
        row = self._rows_for("CSI500")["recent"]
        assert row["benchmark_return"] == "5.00"
        assert row["benchmark_status"] == "ok"

    # --- CSI1000：只有 sample_in 有数据 ---

    def test_csi1000_sample_in_ok(self) -> None:
        row = self._rows_for("CSI1000")["sample_in"]
        assert row["benchmark_return"] == "20.00"
        assert row["benchmark_status"] == "ok"

    def test_csi1000_sample_out_insufficient(self) -> None:
        row = self._rows_for("CSI1000")["sample_out"]
        assert row["benchmark_return"] == "0.00"
        assert row["benchmark_status"] == "insufficient_data"

    def test_csi1000_recent_insufficient(self) -> None:
        row = self._rows_for("CSI1000")["recent"]
        assert row["benchmark_return"] == "0.00"
        assert row["benchmark_status"] == "insufficient_data"

    # --- 三个 period 策略指标独立计算 ---

    def test_strategy_return_per_period_not_copied(self) -> None:
        csi300 = self._rows_for("CSI300")
        si = csi300["sample_in"]["strategy_return"]
        so = csi300["sample_out"]["strategy_return"]
        r = csi300["recent"]["strategy_return"]
        assert si != so
        assert so != r

    def test_benchmark_return_per_period_not_copied(self) -> None:
        csi300 = self._rows_for("CSI300")
        si = csi300["sample_in"]["benchmark_return"]
        so = csi300["sample_out"]["benchmark_return"]
        r = csi300["recent"]["benchmark_return"]
        assert si != so
        assert so != r


class TestBuildBenchmarkComparisonAllColumns:
    """输出包含全部必需列。"""

    REQUIRED_COLUMNS = {
        "period", "benchmark",
        "strategy_return", "strategy_max_drawdown",
        "strategy_annualized_return", "strategy_volatility",
        "strategy_win_rate", "strategy_trade_count",
        "strategy_return_drawdown_ratio",
        "benchmark_return", "benchmark_max_drawdown",
        "benchmark_annualized_return", "benchmark_volatility",
        "benchmark_return_drawdown_ratio",
        "excess_return", "benchmark_status", "audit_note",
    }

    def test_all_required_columns_present(self) -> None:
        for row in ALL_ROWS:
            assert self.REQUIRED_COLUMNS <= set(row.keys()), (
                f"缺少列: {self.REQUIRED_COLUMNS - set(row.keys())}"
            )

    def test_audit_note_contains_window(self) -> None:
        for row in ALL_ROWS:
            assert "window=[" in str(row["audit_note"])


class TestTrueZeroBenchmarkNotMisreported:
    """真实 0% benchmark return 不被误报为缺失。"""

    def test_zero_return_has_ok_status(self) -> None:
        data = [
            IndexDaily("2023-01-02", "000300", None, None, None, 3000.0, None, None),
            IndexDaily("2024-06-28", "000300", None, None, None, 3000.0, None, None),
        ]
        equity = [_ep("2024-01-01", 1_000_000), _ep("2024-06-30", 1_100_000)]
        rows = build_benchmark_comparison_rows(
            equity_curve=equity,
            index_daily=data,
            as_of="2024-06-30",
            required_benchmarks=["CSI300"],
            required_periods=["sample_out"],
        )
        assert len(rows) == 1
        assert rows[0]["benchmark_return"] == "0.00"
        assert rows[0]["benchmark_status"] == "ok"
        assert "insufficient_data" not in str(rows[0]["audit_note"])
        assert "missing" not in str(rows[0]["audit_note"])


class TestMissingBenchmarkIsReported:
    """test_missing_benchmark_is_reported"""

    def test_missing_benchmark_status_and_audit(self) -> None:
        index_daily = [
            IndexDaily("2023-01-02", "000300", None, None, None, 3000.0, None, None),
            IndexDaily("2024-06-28", "000300", None, None, None, 3300.0, None, None),
        ]
        equity = [_ep("2024-01-01", 1_000_000), _ep("2024-06-30", 1_100_000)]
        rows = build_benchmark_comparison_rows(
            equity_curve=equity,
            index_daily=index_daily,
            as_of="2024-06-30",
        )
        csi500_rows = [r for r in rows if r["benchmark"] == "CSI500"]
        assert len(csi500_rows) >= 1
        for row in csi500_rows:
            assert row["benchmark_return"] == "0.00"
            assert row["benchmark_status"] in ("missing", "insufficient_data")
            assert "CSI500" in str(row["audit_note"])


class TestBenchmarkComparisonWithNoTrades:
    """无交易时 win_rate=0, trade_count=0。"""

    def test_no_trades(self) -> None:
        equity = [_ep("2024-01-01", 1_000_000), _ep("2024-06-30", 1_100_000)]
        rows = build_benchmark_comparison_rows(
            equity_curve=equity,
            index_daily=[],
            as_of="2024-06-30",
            trades=[],
            required_benchmarks=["CSI300"],
            required_periods=["recent"],
        )
        assert len(rows) == 1
        assert rows[0]["strategy_win_rate"] == "0.00"
        assert rows[0]["strategy_trade_count"] == "0"


class TestRunnerCoversAllThreeBenchmarks:
    """三个基准 CSI300/CSI500/CSI1000 都在输出中。"""

    def test_all_benchmarks_present(self) -> None:
        benchmarks = {r["benchmark"] for r in ALL_ROWS}
        assert benchmarks == {"CSI300", "CSI500", "CSI1000"}

    def test_all_periods_per_benchmark(self) -> None:
        for bench in ["CSI300", "CSI500", "CSI1000"]:
            periods = {r["period"] for r in ALL_ROWS if r["benchmark"] == bench}
            assert periods == {"sample_in", "sample_out", "recent"}
