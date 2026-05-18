from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from suishi_north_backtest.config import BacktestConfig


@dataclass(frozen=True)
class Mvp1DataSet:
    """MVP-1 回测引擎使用的统一数据集边界。"""

    data_version: str
    parameter_set: str
    universe: str
    equity_curve: list[dict[str, object]]
    trades: list[dict[str, object]]
    skipped_trades: list[dict[str, object]]
    candidates: list[dict[str, object]]
    holdings: list[dict[str, object]]
    benchmark_comparison: list[dict[str, object]]
    track_comparison: list[dict[str, object]]
    sensitivity: list[dict[str, object]]
    metrics: dict[str, object]


class DataProvider(Protocol):
    """MVP-1 数据源适配器协议。"""

    def load(self, config: BacktestConfig) -> Mvp1DataSet:
        """加载统一数据集。"""


class FixtureDataProvider:
    """确定性 fixture 数据源，用于验收和回归测试。"""

    def load(self, config: BacktestConfig) -> Mvp1DataSet:
        ending_equity = round(config.initial_cash * 1.0342, 2)
        midpoint_equity = round(config.initial_cash * 1.012, 2)
        return Mvp1DataSet(
            data_version=config.data_snapshot or "deterministic-fixture-v1-2026-05-18",
            parameter_set="ADR-0002-defaults-fixture-run",
            universe="fixture-core-a-share-sample",
            equity_curve=[
                {
                    "date": config.start_date,
                    "cash": config.initial_cash,
                    "equity": config.initial_cash,
                    "drawdown": "0.0",
                    "track": "portfolio",
                },
                {
                    "date": "2024-01-03",
                    "cash": round(config.initial_cash * 0.78, 2),
                    "equity": midpoint_equity,
                    "drawdown": "0.0",
                    "track": "portfolio",
                },
                {
                    "date": config.end_date,
                    "cash": ending_equity,
                    "equity": ending_equity,
                    "drawdown": "0.0",
                    "track": "portfolio",
                },
            ],
            trades=[
                {
                    "trade_id": "FTR-0001",
                    "track": "mainline_filtered",
                    "symbol": "000001.SZ",
                    "entry_signal_date": "2024-01-02",
                    "entry_date": "2024-01-03",
                    "entry_price": "10.2051",
                    "entry_shares": "10000",
                    "exit_trigger_date": "2024-01-05",
                    "exit_date": "2024-01-08",
                    "exit_price": "10.7956",
                    "exit_reason": "trend_exit",
                    "commission": "62.99",
                    "stamp_tax": "53.98",
                    "slippage_cost": "105.00",
                    "total_cost": "221.97",
                    "gross_pnl": "5905.00",
                    "net_pnl": "5683.03",
                    "first_target_achieved": "true",
                    "audit_note": "deterministic fixture trade with T+1 open execution and cost accounting",
                }
            ],
            skipped_trades=[],
            candidates=[
                {
                    "signal_date": "2024-01-02",
                    "track": "mainline_filtered",
                    "symbol": "000001.SZ",
                    "industry_level2": "fixture_bank_level2",
                    "is_strong_mainline": "true",
                    "a_date": "2023-12-20",
                    "a_price": "8.00",
                    "b_date": "2023-12-28",
                    "b_price": "10.40",
                    "c_date": "2024-01-02",
                    "c_price": "9.60",
                    "ab_gain_pct": "30.00",
                    "bc_retracement_pct": "33.33",
                    "distance_to_c_low_pct": "4.17",
                    "weekly_filter_passed": "true",
                    "annual_filter_passed": "true",
                    "score": "88.5",
                    "audit_note": "deterministic fixture candidate generated with as-of date 2024-01-02",
                }
            ],
            holdings=[
                {
                    "date": "2024-01-04",
                    "track": "mainline_filtered",
                    "symbol": "000001.SZ",
                    "shares": "10000",
                    "cost_basis": "102051.00",
                    "market_value": "107600.00",
                    "unrealized_pnl": "5549.00",
                    "holding_days": "2",
                    "highest_close_since_entry": "10.76",
                    "audit_note": "fixture position snapshot before exit trigger",
                },
                {
                    "date": config.end_date,
                    "track": "portfolio",
                    "symbol": "CASH",
                    "shares": "0",
                    "cost_basis": "0",
                    "market_value": ending_equity,
                    "unrealized_pnl": "0",
                    "holding_days": "0",
                    "highest_close_since_entry": "0",
                    "audit_note": "fixture ending cash after closed trade",
                },
            ],
            benchmark_comparison=_fixture_benchmark_rows(),
            track_comparison=[
                {
                    "metric": "total_return",
                    "pure_structure_track": "2.10",
                    "mainline_filtered_track": "3.42",
                    "delta": "1.32",
                    "audit_note": "fixture mainline track improves total return",
                },
                {
                    "metric": "max_drawdown",
                    "pure_structure_track": "2.00",
                    "mainline_filtered_track": "1.25",
                    "delta": "-0.75",
                    "audit_note": "fixture mainline track lowers drawdown",
                },
            ],
            sensitivity=[
                {
                    "parameter": "baseline",
                    "baseline_value": "ADR-0002",
                    "variant_value": "ADR-0002",
                    "sample_in_metric": "3.42",
                    "sample_out_metric": "3.42",
                    "overfit_risk": "low",
                    "accepted": "true",
                    "audit_note": "fixture baseline uses ADR-0002 defaults",
                },
                {
                    "parameter": "ab_min_gain",
                    "baseline_value": "20%",
                    "variant_value": "25%",
                    "sample_in_metric": "3.10",
                    "sample_out_metric": "2.95",
                    "overfit_risk": "low",
                    "accepted": "false",
                    "audit_note": "fixture perturbation keeps sample-out behavior observable",
                },
            ],
            metrics={
                "name": config.name,
                "initial_cash": config.initial_cash,
                "ending_equity": ending_equity,
                "total_return": 0.0342,
                "max_drawdown": 0.0125,
                "profit_factor": 1.34,
                "win_rate": 1.0,
                "trade_count": 1,
                "tracks": {
                    "pure_structure": {"trade_count": 1, "total_return": 0.021},
                    "mainline_filtered": {"trade_count": 1, "total_return": 0.0342},
                },
                "benchmarks": ["CSI300", "CSI500", "CSI1000"],
                "sample_windows": {
                    "sample_in": ["2018-01-01", "2022-12-31"],
                    "sample_out": ["2023-01-01", "latest_complete_trading_day"],
                    "recent": ["2024-01-01", "latest_complete_trading_day"],
                },
                "audit_note": "deterministic fixture metrics for acceptance verification",
            },
        )


class AStockDataProvider:
    """a-stock-data 数据源边界。

    该类先固定接口和错误信息，避免策略引擎直接依赖外部字段形状。
    真正接入外部数据源时，应在这里完成字段映射、缓存和数据版本生成。
    """

    def load(self, config: BacktestConfig) -> Mvp1DataSet:
        snapshot = config.data_snapshot or "unspecified"
        raise NotImplementedError(
            "a-stock-data provider is not implemented yet. "
            f"Requested snapshot: {snapshot}. Use --data-source fixture for now."
        )


def build_data_provider(name: str) -> DataProvider:
    if name == "fixture":
        return FixtureDataProvider()
    if name == "a-stock-data":
        return AStockDataProvider()
    raise ValueError(f"Unsupported data source: {name}")


def _fixture_benchmark_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for period in ["sample_in", "sample_out", "recent"]:
        rows.extend(
            [
                _benchmark_row(period, "CSI300", "3.42", "1.10"),
                _benchmark_row(period, "CSI500", "3.42", "1.80"),
                _benchmark_row(period, "CSI1000", "3.42", "2.40"),
            ]
        )
    return rows


def _benchmark_row(
    period: str,
    benchmark: str,
    strategy_return: str,
    benchmark_return: str,
) -> dict[str, object]:
    excess = round(float(strategy_return) - float(benchmark_return), 2)
    return {
        "period": period,
        "benchmark": benchmark,
        "strategy_return": strategy_return,
        "benchmark_return": benchmark_return,
        "excess_return": f"{excess:.2f}",
        "max_drawdown": "1.25",
        "return_drawdown_ratio": "2.74",
        "audit_note": "deterministic fixture benchmark comparison",
    }
