from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from suishi_north_backtest import __version__
from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.data import Mvp1DataSet, build_data_provider


RESEARCH_LIMITATION = "MVP-1 是日线代理研究系统，不等同于完整实盘交易系统。"
CSV_ENCODING = "utf-8-sig"

FULL_ACCEPTANCE_OUTPUTS = [
    "metrics.json",
    "candidates.csv",
    "holdings.csv",
    "benchmark_comparison.csv",
    "track_comparison.csv",
    "sensitivity.csv",
]


@dataclass(frozen=True)
class BacktestResult:
    """MVP-1 回测运行结果。"""

    output_dir: Path


def run_mvp1_backtest(config: BacktestConfig) -> BacktestResult:
    """运行 MVP-1 组合回测。

    引擎只依赖统一 `Mvp1DataSet`，不直接依赖外部数据源字段形状。
    当前默认使用 fixture provider；真实 A 股数据应通过 data provider 替换。
    """

    output_dir = config.normalized_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    provider = build_data_provider(config.data_source)
    data_set = provider.load(config)

    _write_equity_curve(output_dir / "equity_curve.csv", data_set)
    _write_trades(output_dir / "trades.csv", data_set)
    _write_skipped_trades(output_dir / "skipped_trades.csv", data_set)
    _write_candidates(output_dir / "candidates.csv", data_set)
    _write_holdings(output_dir / "holdings.csv", data_set)
    _write_benchmark_comparison(output_dir / "benchmark_comparison.csv", data_set)
    _write_track_comparison(output_dir / "track_comparison.csv", data_set)
    _write_sensitivity(output_dir / "sensitivity.csv", data_set)
    _write_metrics(output_dir / "metrics.json", data_set, config)
    _write_metadata(output_dir / "run_metadata.json", config, data_set)

    return BacktestResult(output_dir=output_dir)


def _write_equity_curve(path: Path, data_set: Mvp1DataSet) -> None:
    _write_csv(path, ["date", "cash", "equity", "drawdown", "track"], data_set.equity_curve)


def _write_trades(path: Path, data_set: Mvp1DataSet) -> None:
    _write_csv(
        path,
        [
            "trade_id",
            "track",
            "symbol",
            "entry_signal_date",
            "entry_date",
            "entry_price",
            "entry_shares",
            "exit_trigger_date",
            "exit_date",
            "exit_price",
            "exit_reason",
            "commission",
            "stamp_tax",
            "slippage_cost",
            "total_cost",
            "gross_pnl",
            "net_pnl",
            "first_target_achieved",
            "audit_note",
        ],
        data_set.trades,
    )


def _write_skipped_trades(path: Path, data_set: Mvp1DataSet) -> None:
    _write_csv(path, ["signal_date", "track", "symbol", "reason"], data_set.skipped_trades)


def _write_candidates(path: Path, data_set: Mvp1DataSet) -> None:
    _write_csv(
        path,
        [
            "signal_date",
            "track",
            "symbol",
            "industry_level2",
            "is_strong_mainline",
            "a_date",
            "a_price",
            "b_date",
            "b_price",
            "c_date",
            "c_price",
            "ab_gain_pct",
            "bc_retracement_pct",
            "distance_to_c_low_pct",
            "weekly_filter_passed",
            "annual_filter_passed",
            "score",
            "audit_note",
        ],
        data_set.candidates,
    )


def _write_holdings(path: Path, data_set: Mvp1DataSet) -> None:
    _write_csv(
        path,
        [
            "date",
            "track",
            "symbol",
            "shares",
            "cost_basis",
            "market_value",
            "unrealized_pnl",
            "holding_days",
            "highest_close_since_entry",
            "audit_note",
        ],
        data_set.holdings,
    )


def _write_benchmark_comparison(path: Path, data_set: Mvp1DataSet) -> None:
    _write_csv(
        path,
        [
            "period",
            "benchmark",
            "strategy_return",
            "benchmark_return",
            "excess_return",
            "max_drawdown",
            "return_drawdown_ratio",
            "audit_note",
        ],
        data_set.benchmark_comparison,
    )


def _write_track_comparison(path: Path, data_set: Mvp1DataSet) -> None:
    _write_csv(
        path,
        [
            "metric",
            "pure_structure_track",
            "mainline_filtered_track",
            "delta",
            "audit_note",
        ],
        data_set.track_comparison,
    )


def _write_sensitivity(path: Path, data_set: Mvp1DataSet) -> None:
    _write_csv(
        path,
        [
            "parameter",
            "baseline_value",
            "variant_value",
            "sample_in_metric",
            "sample_out_metric",
            "overfit_risk",
            "accepted",
            "audit_note",
        ],
        data_set.sensitivity,
    )


def _write_metrics(path: Path, data_set: Mvp1DataSet, config: BacktestConfig) -> None:
    metrics = {
        **data_set.metrics,
        "name": config.name,
        "research_limitation": RESEARCH_LIMITATION,
    }
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_metadata(path: Path, config: BacktestConfig, data_set: Mvp1DataSet) -> None:
    outputs = [
        "equity_curve.csv",
        "trades.csv",
        "skipped_trades.csv",
        "run_metadata.json",
        *FULL_ACCEPTANCE_OUTPUTS,
    ]
    metadata = {
        "name": config.name,
        "start_date": config.start_date,
        "end_date": config.end_date,
        "initial_cash": config.initial_cash,
        "code_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_source": config.data_source,
        "data_version": data_set.data_version,
        "parameter_set": data_set.parameter_set,
        "universe": data_set.universe,
        "research_limitation": RESEARCH_LIMITATION,
        "outputs": outputs,
    }
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding=CSV_ENCODING) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
