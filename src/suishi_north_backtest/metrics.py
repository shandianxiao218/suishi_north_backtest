from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, Sequence

from suishi_north_backtest.market_data import IndexDaily


BENCHMARK_CODE_TO_NAME = {
    "000300": "CSI300",
    "000905": "CSI500",
    "000852": "CSI1000",
    "CSI300": "CSI300",
    "CSI500": "CSI500",
    "CSI1000": "CSI1000",
}
REQUIRED_BENCHMARKS = ["CSI300", "CSI500", "CSI1000"]
SAMPLE_WINDOWS = {
    "sample_in": ("2018-01-01", "2022-12-31"),
    "sample_out": ("2023-01-01", None),
    "recent": ("2024-01-01", None),
}


@dataclass(frozen=True)
class DatedValue:
    date: str
    value: float


@dataclass(frozen=True)
class PeriodMetrics:
    total_return: float
    max_drawdown: float
    annualized_return: float
    volatility: float


@dataclass(frozen=True)
class Window:
    name: str
    start_date: str
    end_date: str


def total_return(values: Sequence[float]) -> float:
    if len(values) < 2 or values[0] == 0:
        return 0.0
    return (values[-1] - values[0]) / values[0]


def max_drawdown(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = max(worst, (peak - value) / peak)
    return worst


def annualized_return(points: Sequence[DatedValue]) -> float:
    if len(points) < 2 or points[0].value == 0:
        return 0.0
    days = max(_date_to_ordinal(points[-1].date) - _date_to_ordinal(points[0].date), 1)
    cumulative = total_return([p.value for p in points])
    if cumulative <= -1.0:
        return -1.0
    return (1.0 + cumulative) ** (365.0 / days) - 1.0


def volatility(values: Sequence[float], periods_per_year: int = 252) -> float:
    returns = []
    for prev, curr in zip(values, values[1:]):
        if prev != 0:
            returns.append((curr - prev) / prev)
    if len(returns) < 2:
        return 0.0
    avg = sum(returns) / len(returns)
    variance = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
    return sqrt(variance) * sqrt(periods_per_year)


def benchmark_excess_return(strategy_return: float, benchmark_return: float) -> float:
    return strategy_return - benchmark_return


def return_drawdown_ratio(return_value: float, drawdown: float) -> float:
    if drawdown == 0:
        return 0.0
    return return_value / drawdown


def sample_windows(as_of: str) -> list[Window]:
    return [
        Window("sample_in", "2018-01-01", "2022-12-31"),
        Window("sample_out", "2023-01-01", as_of),
        Window("recent", "2024-01-01", as_of),
    ]


def split_sample_windows(points: Sequence[DatedValue], as_of: str) -> dict[str, list[DatedValue]]:
    result: dict[str, list[DatedValue]] = {}
    for window in sample_windows(as_of):
        result[window.name] = [
            p for p in points if window.start_date <= p.date <= window.end_date
        ]
    return result


def compute_period_metrics(points: Sequence[DatedValue]) -> PeriodMetrics:
    ordered = sorted(points, key=lambda p: p.date)
    values = [p.value for p in ordered]
    return PeriodMetrics(
        total_return=total_return(values),
        max_drawdown=max_drawdown(values),
        annualized_return=annualized_return(ordered),
        volatility=volatility(values),
    )


def benchmark_points_by_name(index_daily: Iterable[IndexDaily]) -> dict[str, list[DatedValue]]:
    by_name: dict[str, list[DatedValue]] = {}
    for row in index_daily:
        name = BENCHMARK_CODE_TO_NAME.get(row.index_code)
        if not name or row.close is None:
            continue
        by_name.setdefault(name, []).append(DatedValue(row.trade_date, float(row.close)))
    for rows in by_name.values():
        rows.sort(key=lambda p: p.date)
    return by_name


def equity_points_from_rows(equity_curve: Iterable[dict[str, object]]) -> list[DatedValue]:
    points: list[DatedValue] = []
    for row in equity_curve:
        if str(row.get("track", "")) not in ("mainline_filtered", "portfolio"):
            continue
        date = str(row.get("date", ""))
        if not date:
            continue
        try:
            value = float(row.get("equity", 0.0))
        except (TypeError, ValueError):
            continue
        points.append(DatedValue(date, value))
    points.sort(key=lambda p: p.date)
    return points


def build_benchmark_comparison_rows(
    *,
    index_daily: Iterable[IndexDaily],
    strategy_equity: Sequence[DatedValue],
    trades: Sequence[object],
    as_of: str,
) -> list[dict[str, object]]:
    benchmark_points = benchmark_points_by_name(index_daily)
    strategy_windows = split_sample_windows(strategy_equity, as_of)
    rows: list[dict[str, object]] = []

    for window in sample_windows(as_of):
        strategy_points = strategy_windows[window.name]
        strategy_metrics = compute_period_metrics(strategy_points)
        period_trades = _trades_in_window(trades, window.start_date, window.end_date)
        trade_count = len(period_trades)
        win_rate = _trade_win_rate(period_trades)

        for benchmark in REQUIRED_BENCHMARKS:
            b_points = [
                p for p in benchmark_points.get(benchmark, [])
                if window.start_date <= p.date <= window.end_date
            ]
            if len(b_points) < 2:
                benchmark_metrics = PeriodMetrics(0.0, 0.0, 0.0, 0.0)
                audit_note = (
                    f"missing benchmark data for {benchmark} in {window.name} "
                    f"{window.start_date}..{window.end_date}"
                )
            else:
                benchmark_metrics = compute_period_metrics(b_points)
                audit_note = (
                    f"real benchmark comparison for {benchmark} in {window.name} "
                    f"{window.start_date}..{window.end_date}"
                )

            rows.append({
                "period": window.name,
                "benchmark": benchmark,
                "strategy_return": _pct(strategy_metrics.total_return),
                "benchmark_return": _pct(benchmark_metrics.total_return),
                "excess_return": _pct(benchmark_excess_return(strategy_metrics.total_return, benchmark_metrics.total_return)),
                "max_drawdown": _pct(strategy_metrics.max_drawdown),
                "annualized_return": _pct(strategy_metrics.annualized_return),
                "volatility": _pct(strategy_metrics.volatility),
                "win_rate": _pct(win_rate),
                "trade_count": str(trade_count),
                "return_drawdown_ratio": f"{return_drawdown_ratio(strategy_metrics.total_return, strategy_metrics.max_drawdown):.2f}",
                "audit_note": audit_note,
            })
    return rows


def _trades_in_window(trades: Sequence[object], start_date: str, end_date: str) -> list[object]:
    result = []
    for trade in trades:
        exit_date = str(getattr(trade, "exit_date", ""))
        if start_date <= exit_date <= end_date:
            result.append(trade)
    return result


def _trade_win_rate(trades: Sequence[object]) -> float:
    if not trades:
        return 0.0
    wins = 0
    for trade in trades:
        try:
            wins += 1 if float(getattr(trade, "net_pnl", 0.0)) > 0 else 0
        except (TypeError, ValueError):
            pass
    return wins / len(trades)


def _pct(value: float) -> str:
    return f"{value * 100:.2f}"


def _date_to_ordinal(date_str: str) -> int:
    year, month, day = (int(part) for part in date_str.split("-"))
    # Civil date to ordinal, valid for Gregorian dates used by this project.
    if month <= 2:
        year -= 1
        month += 12
    era = year // 400
    yoe = year - era * 400
    doy = (153 * (month - 3) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe
