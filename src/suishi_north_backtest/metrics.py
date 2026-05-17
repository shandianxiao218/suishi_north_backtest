from __future__ import annotations

from dataclasses import dataclass
from datetime import date


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

    start_equity = points[0].equity
    end_equity = points[-1].equity
    cumulative_return = end_equity / start_equity - 1
    max_drawdown = _max_drawdown(points)
    ratio = cumulative_return / max_drawdown if max_drawdown > 0 else float("inf")
    return EquityMetrics(
        cumulative_return=cumulative_return,
        max_drawdown=max_drawdown,
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

    return {
        "样本内": evaluate_equity_curve(
            _window_points(points, date(2018, 1, 1), date(2022, 12, 31))
        ),
        "样本外": evaluate_equity_curve(
            _window_points(points, date(2023, 1, 1), points[-1].date)
        ),
        "近期窗口": evaluate_equity_curve(
            _window_points(points, date(2024, 1, 1), points[-1].date)
        ),
    }


def _window_points(
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


def _max_drawdown(points: list[EquityPoint]) -> float:
    peak = points[0].equity
    max_drawdown = 0.0
    for point in points:
        peak = max(peak, point.equity)
        drawdown = point.equity / peak - 1
        max_drawdown = min(max_drawdown, drawdown)
    return abs(max_drawdown)
