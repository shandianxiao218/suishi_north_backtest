from __future__ import annotations

import csv
import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from suishi_north_backtest.metrics import EquityMetrics
from suishi_north_backtest.metrics import EquityPoint


RESEARCH_LIMITATION = "MVP-1 是日线代理研究系统，不等同于完整实盘交易系统。"
CSV_ENCODING = "utf-8-sig"


@dataclass(frozen=True)
class BacktestReport:
    """MVP-1 回测报告数据。"""

    name: str
    data_version: str
    code_version: str
    stock_pool: list[str]
    start_date: date
    end_date: date
    parameters: dict[str, Any]
    equity_curve: list[EquityPoint]
    trades: list[dict[str, Any]]
    skipped_trades: list[dict[str, Any]]
    metrics: dict[str, EquityMetrics]


def write_backtest_report(report: BacktestReport, output_dir: Path) -> None:
    """写出 MVP-1 回测报告和审计日志。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_equity_curve(output_dir / "equity_curve.csv", report.equity_curve)
    _write_dict_rows(output_dir / "trades.csv", report.trades)
    _write_dict_rows(output_dir / "skipped_trades.csv", report.skipped_trades)
    _write_metrics(output_dir / "metrics.json", report.metrics)
    _write_metadata(output_dir / "run_metadata.json", report)


def _write_equity_curve(path: Path, equity_curve: list[EquityPoint]) -> None:
    rows = [
        {"date": point.date.isoformat(), "equity": point.equity}
        for point in equity_curve
    ]
    _write_dict_rows(path, rows)


def _write_dict_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({field for row in rows for field in row})
    with path.open("w", newline="", encoding=CSV_ENCODING) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_metrics(path: Path, metrics: dict[str, EquityMetrics]) -> None:
    payload = {name: asdict(value) for name, value in metrics.items()}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_metadata(path: Path, report: BacktestReport) -> None:
    payload = {
        "name": report.name,
        "data_version": report.data_version,
        "code_version": report.code_version,
        "stock_pool": report.stock_pool,
        "start_date": report.start_date.isoformat(),
        "end_date": report.end_date.isoformat(),
        "parameters": report.parameters,
        "research_limitation": RESEARCH_LIMITATION,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
