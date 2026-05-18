from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from suishi_north_backtest import __version__
from suishi_north_backtest.config import BacktestConfig


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
    """运行 MVP-1 组合回测当前可用骨架。

    当前实现仍使用占位数据，但会输出完整验收所需的审计文件骨架，
    便于后续真实数据、信号、执行和报告模块逐步替换。
    """

    output_dir = config.normalized_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_equity_curve(output_dir / "equity_curve.csv", config)
    _write_trades(output_dir / "trades.csv")
    _write_skipped_trades(output_dir / "skipped_trades.csv")
    _write_candidates(output_dir / "candidates.csv")
    _write_holdings(output_dir / "holdings.csv", config)
    _write_benchmark_comparison(output_dir / "benchmark_comparison.csv", config)
    _write_track_comparison(output_dir / "track_comparison.csv")
    _write_sensitivity(output_dir / "sensitivity.csv")
    _write_metrics(output_dir / "metrics.json", config)
    _write_metadata(output_dir / "run_metadata.json", config)

    return BacktestResult(output_dir=output_dir)


def _write_equity_curve(path: Path, config: BacktestConfig) -> None:
    _write_csv(
        path,
        ["date", "cash", "equity", "drawdown", "track"],
        [
            {
                "date": config.start_date,
                "cash": config.initial_cash,
                "equity": config.initial_cash,
                "drawdown": "0.0",
                "track": "portfolio",
            },
            {
                "date": config.end_date,
                "cash": config.initial_cash,
                "equity": config.initial_cash,
                "drawdown": "0.0",
                "track": "portfolio",
            },
        ],
    )


def _write_trades(path: Path) -> None:
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
        [],
    )


def _write_skipped_trades(path: Path) -> None:
    _write_csv(
        path,
        ["signal_date", "track", "symbol", "reason"],
        [
            {
                "signal_date": "",
                "track": "portfolio",
                "symbol": "",
                "reason": "MVP-1 当前为验收骨架，暂无真实候选，后续接入真实数据与信号。",
            }
        ],
    )


def _write_candidates(path: Path) -> None:
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
        [],
    )


def _write_holdings(path: Path, config: BacktestConfig) -> None:
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
        [
            {
                "date": config.end_date,
                "track": "portfolio",
                "symbol": "CASH",
                "shares": "0",
                "cost_basis": "0",
                "market_value": config.initial_cash,
                "unrealized_pnl": "0",
                "holding_days": "0",
                "highest_close_since_entry": "0",
                "audit_note": "验收骨架仅保留现金状态。",
            }
        ],
    )


def _write_benchmark_comparison(path: Path, config: BacktestConfig) -> None:
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
        [
            _benchmark_row("sample_in", "CSI300"),
            _benchmark_row("sample_in", "CSI500"),
            _benchmark_row("sample_in", "CSI1000"),
            _benchmark_row("sample_out", "CSI300"),
            _benchmark_row("recent", "CSI300"),
        ],
    )


def _benchmark_row(period: str, benchmark: str) -> dict[str, Any]:
    return {
        "period": period,
        "benchmark": benchmark,
        "strategy_return": "0.0",
        "benchmark_return": "0.0",
        "excess_return": "0.0",
        "max_drawdown": "0.0",
        "return_drawdown_ratio": "0.0",
        "audit_note": "验收骨架占位，真实基准结果由后续数据适配与回测模块填充。",
    }


def _write_track_comparison(path: Path) -> None:
    _write_csv(
        path,
        [
            "metric",
            "pure_structure_track",
            "mainline_filtered_track",
            "delta",
            "audit_note",
        ],
        [
            {
                "metric": "total_return",
                "pure_structure_track": "0.0",
                "mainline_filtered_track": "0.0",
                "delta": "0.0",
                "audit_note": "验收骨架占位，真实双轨差异由后续信号与组合回测填充。",
            }
        ],
    )


def _write_sensitivity(path: Path) -> None:
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
        [
            {
                "parameter": "baseline",
                "baseline_value": "ADR-0002",
                "variant_value": "ADR-0002",
                "sample_in_metric": "0.0",
                "sample_out_metric": "0.0",
                "overfit_risk": "unknown",
                "accepted": "true",
                "audit_note": "验收骨架保留参数敏感性输出结构，不自动替换默认参数。",
            }
        ],
    )


def _write_metrics(path: Path, config: BacktestConfig) -> None:
    metrics = {
        "name": config.name,
        "initial_cash": config.initial_cash,
        "ending_equity": config.initial_cash,
        "total_return": 0.0,
        "max_drawdown": 0.0,
        "profit_factor": None,
        "win_rate": None,
        "trade_count": 0,
        "tracks": {
            "pure_structure": {"trade_count": 0, "total_return": 0.0},
            "mainline_filtered": {"trade_count": 0, "total_return": 0.0},
        },
        "benchmarks": ["CSI300", "CSI500", "CSI1000"],
        "sample_windows": {
            "sample_in": ["2018-01-01", "2022-12-31"],
            "sample_out": ["2023-01-01", "latest_complete_trading_day"],
            "recent": ["2024-01-01", "latest_complete_trading_day"],
        },
        "research_limitation": RESEARCH_LIMITATION,
        "audit_note": "当前为验收骨架指标，真实绩效由后续完整数据与策略模块填充。",
    }
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_metadata(path: Path, config: BacktestConfig) -> None:
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
        "data_version": "acceptance-placeholder",
        "parameter_set": "ADR-0002 defaults",
        "universe": "沪深 A 股核心股票池占位",
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
