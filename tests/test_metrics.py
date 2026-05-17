from __future__ import annotations

from datetime import date

from suishi_north_backtest.metrics import (
    EquityPoint,
    compare_with_benchmarks,
    evaluate_equity_curve,
    evaluate_sample_windows,
)


def test_evaluates_equity_curve_return_drawdown_and_ratio() -> None:
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


def test_compares_strategy_equity_curve_with_required_benchmarks() -> None:
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


def test_evaluates_in_sample_out_of_sample_and_recent_windows() -> None:
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
