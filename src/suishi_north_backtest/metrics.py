"""指标计算模块。

提供纯函数计算组合回测各项指标：累计收益、最大回撤、年化收益、波动率、
胜率、超额收益、收益回撤比。按样本区间拆分 equity_curve 和基准数据，
每个 period 独立计算，不复制全周期数字。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from suishi_north_backtest.market_data import IndexDaily


# --- 旧接口保留（optimization.py / report.py 依赖） ---


@dataclass(frozen=True)
class EquityPoint:
    """单日权益点。"""

    date: date
    equity: float


@dataclass(frozen=True)
class EquityMetrics:
    """权益曲线绩效指标。"""

    cumulative_return: float
    max_drawdown: float
    return_drawdown_ratio: float


@dataclass(frozen=True)
class BenchmarkComparison:
    """策略相对单个基准的表现。"""

    benchmark_name: str
    strategy_return: float
    benchmark_return: float
    excess_return: float
    max_drawdown_delta: float


def evaluate_equity_curve(points: list[EquityPoint]) -> EquityMetrics:
    """计算累计收益、最大回撤和收益回撤比。"""
    if not points:
        return EquityMetrics(cumulative_return=0.0, max_drawdown=0.0, return_drawdown_ratio=0.0)
    start_equity = points[0].equity
    end_equity = points[-1].equity
    cumulative_return = end_equity / start_equity - 1 if start_equity != 0 else 0.0
    dd = _max_drawdown_equity_points(points)
    ratio = cumulative_return / dd if dd > 0 else (0.0 if cumulative_return == 0 else float("inf"))
    return EquityMetrics(
        cumulative_return=cumulative_return,
        max_drawdown=dd,
        return_drawdown_ratio=ratio,
    )


def compare_with_benchmarks(
    strategy: list[EquityPoint],
    benchmarks: dict[str, list[EquityPoint]],
) -> dict[str, BenchmarkComparison]:
    """比较策略与多个指数基准的表现。"""
    strategy_metrics = evaluate_equity_curve(strategy)
    return {
        name: _compare_single_benchmark(strategy_metrics, name, points)
        for name, points in benchmarks.items()
    }


def evaluate_sample_windows(
    points: list[EquityPoint],
) -> dict[str, EquityMetrics]:
    """评估样本内、样本外和近期窗口。"""
    if not points:
        return {
            "样本内": EquityMetrics(0.0, 0.0, 0.0),
            "样本外": EquityMetrics(0.0, 0.0, 0.0),
            "近期窗口": EquityMetrics(0.0, 0.0, 0.0),
        }
    last_date = points[-1].date
    return {
        "样本内": evaluate_equity_curve(
            _window_equity_points(points, date(2018, 1, 1), date(2022, 12, 31))
        ),
        "样本外": evaluate_equity_curve(
            _window_equity_points(points, date(2023, 1, 1), last_date)
        ),
        "近期窗口": evaluate_equity_curve(
            _window_equity_points(points, date(2024, 1, 1), last_date)
        ),
    }


def _window_equity_points(
    points: list[EquityPoint],
    start: date,
    end: date,
) -> list[EquityPoint]:
    return [point for point in points if start <= point.date <= end]


def _compare_single_benchmark(
    strategy_metrics: EquityMetrics,
    benchmark_name: str,
    benchmark: list[EquityPoint],
) -> BenchmarkComparison:
    benchmark_metrics = evaluate_equity_curve(benchmark)
    return BenchmarkComparison(
        benchmark_name=benchmark_name,
        strategy_return=strategy_metrics.cumulative_return,
        benchmark_return=benchmark_metrics.cumulative_return,
        excess_return=(
            strategy_metrics.cumulative_return
            - benchmark_metrics.cumulative_return
        ),
        max_drawdown_delta=(
            strategy_metrics.max_drawdown - benchmark_metrics.max_drawdown
        ),
    )


def _max_drawdown_equity_points(points: list[EquityPoint]) -> float:
    if not points:
        return 0.0
    peak = points[0].equity
    result = 0.0
    for point in points:
        peak = max(peak, point.equity)
        dd = 0.0 if peak == 0 else (peak - point.equity) / peak
        result = max(result, dd)
    return result


# --- 新接口：dict-based 指标函数（Issue #36） ---


# 基准代码映射

BENCHMARK_CODE_TO_NAME: dict[str, str] = {
    "000300": "CSI300",
    "000905": "CSI500",
    "000852": "CSI1000",
}

_NAME_TO_CODE: dict[str, str] = {v: k for k, v in BENCHMARK_CODE_TO_NAME.items()}


def total_return(equity_curve: list[dict[str, object]]) -> float:
    """累计收益：首尾权益百分比变化。"""
    values = [float(p["equity"]) for p in equity_curve]
    if len(values) < 2 or values[0] == 0:
        return 0.0
    return (values[-1] - values[0]) / values[0]


def max_drawdown(equity_curve: list[dict[str, object]]) -> float:
    """最大回撤：峰到谷最大跌幅。"""
    values = [float(p["equity"]) for p in equity_curve]
    if not values:
        return 0.0
    peak = values[0]
    result = 0.0
    for v in values:
        peak = max(peak, v)
        dd = 0.0 if peak == 0 else (peak - v) / peak
        result = max(result, dd)
    return result


def annualized_return(
    equity_curve: list[dict[str, object]],
    trading_days_per_year: int = 242,
) -> float:
    """年化收益：(1 + total)^(252/calendar_days) - 1。"""
    if len(equity_curve) < 2:
        return 0.0
    from datetime import datetime as _dt
    dates = [str(p["date"]) for p in equity_curve]
    try:
        d0 = _dt.strptime(dates[0], "%Y-%m-%d")
        d1 = _dt.strptime(dates[-1], "%Y-%m-%d")
    except (ValueError, IndexError):
        return 0.0
    calendar_days = (d1 - d0).days
    if calendar_days < 1:
        return 0.0
    tr = total_return(equity_curve)
    return (1.0 + tr) ** (365 / calendar_days) - 1.0


def volatility(
    equity_curve: list[dict[str, object]],
    trading_days_per_year: int = 242,
) -> float:
    """年化波动率：日收益率标准差 × √252。"""
    values = [float(p["equity"]) for p in equity_curve]
    if len(values) < 2:
        return 0.0
    daily_returns = [
        (values[i] / values[i - 1]) - 1.0
        for i in range(1, len(values))
        if values[i - 1] != 0
    ]
    if len(daily_returns) < 2:
        return 0.0
    mean_r = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    return math.sqrt(variance) * math.sqrt(trading_days_per_year)


def win_rate(trades: list[dict[str, object]]) -> float:
    """胜率：盈利交易占比。"""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if float(t.get("net_pnl", 0)) > 0)
    return wins / len(trades)


def trade_count(trades: list[dict[str, object]]) -> int:
    """交易次数。"""
    return len(trades)


def excess_return(strategy_ret: float, benchmark_ret: float) -> float:
    """超额收益：策略 - 基准。"""
    return strategy_ret - benchmark_ret


def return_drawdown_ratio(total_ret: float, max_dd: float) -> float:
    """收益回撤比。"""
    if max_dd == 0:
        return 0.0
    return total_ret / max_dd


# --- 样本窗口与基准辅助 ---


def sample_windows(as_of: str) -> dict[str, tuple[str, str]]:
    """返回三个样本区间 {name: (start, end)}。"""
    return {
        "sample_in": ("2018-01-01", "2022-12-31"),
        "sample_out": ("2023-01-01", as_of),
        "recent": ("2024-01-01", as_of),
    }


def equity_curve_in_window(
    equity_curve: list[dict[str, object]],
    start_date: str,
    end_date: str,
) -> list[dict[str, object]]:
    """按日期范围过滤 equity_curve。"""
    return [
        p for p in equity_curve
        if start_date <= str(p["date"]) <= end_date
    ]


def benchmark_return_in_window(
    index_daily: list[IndexDaily],
    benchmark_name: str,
    start_date: str,
    end_date: str,
) -> float:
    """计算指定基准在日期窗口内的总回报。"""
    code = _NAME_TO_CODE.get(benchmark_name)
    if code is None:
        return 0.0
    rows = [
        r for r in index_daily
        if r.index_code == code
        and start_date <= r.trade_date <= end_date
        and r.close is not None
    ]
    if len(rows) < 2:
        return 0.0
    rows.sort(key=lambda r: r.trade_date)
    first_close = float(rows[0].close)
    last_close = float(rows[-1].close)
    if first_close == 0:
        return 0.0
    return (last_close - first_close) / first_close


# --- 组合函数 ---


def build_benchmark_comparison_rows(
    equity_curve: list[dict[str, object]],
    index_daily: list[IndexDaily],
    as_of: str,
    required_benchmarks: list[str] | None = None,
    required_periods: list[str] | None = None,
) -> list[dict[str, object]]:
    """构建 benchmark_comparison.csv 行，每个 period 独立计算指标。

    不复制全周期数字到所有 period。
    """
    if required_benchmarks is None:
        required_benchmarks = ["CSI300", "CSI500", "CSI1000"]
    if required_periods is None:
        required_periods = ["sample_in", "sample_out", "recent"]

    windows = sample_windows(as_of)
    rows: list[dict[str, object]] = []

    for period in required_periods:
        start, end = windows[period]
        window_curve = equity_curve_in_window(equity_curve, start, end)

        if window_curve:
            strat_ret = total_return(window_curve)
            strat_dd = max_drawdown(window_curve)
            curve_note = ""
        else:
            strat_ret = 0.0
            strat_dd = 0.0
            curve_note = "窗口内无权益数据"

        for benchmark in required_benchmarks:
            bench_ret = benchmark_return_in_window(index_daily, benchmark, start, end)
            ex_ret = excess_return(strat_ret, bench_ret)
            rd_ratio = return_drawdown_ratio(strat_ret, strat_dd)

            parts = [f"window=[{start},{end}]"]
            if curve_note:
                parts.append(curve_note)
            if bench_ret == 0.0:
                parts.append(f"缺少{benchmark}基准数据或窗口内数据不足")
            parts.append("per-period real benchmark comparison")

            rows.append({
                "period": period,
                "benchmark": benchmark,
                "strategy_return": f"{strat_ret * 100:.2f}",
                "benchmark_return": f"{bench_ret * 100:.2f}",
                "excess_return": f"{ex_ret * 100:.2f}",
                "max_drawdown": f"{strat_dd * 100:.2f}",
                "return_drawdown_ratio": f"{rd_ratio:.2f}",
                "audit_note": "; ".join(parts),
            })

    return rows
