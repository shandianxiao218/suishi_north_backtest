from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from suishi_north_backtest.metrics import EquityMetrics, EquityPoint
from suishi_north_backtest.report import (
    BacktestReport,
    write_backtest_report,
)


def test_writes_report_outputs_and_audit_metadata(tmp_path: Path) -> None:
    report = BacktestReport(
        name="mvp1-report-test",
        data_version="fixture-2024",
        code_version="test-sha",
        stock_pool=["000001.SZ"],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        parameters={"risk_per_trade": 0.01},
        equity_curve=[
            EquityPoint(date(2024, 1, 1), 1_000_000),
            EquityPoint(date(2024, 1, 31), 1_100_000),
        ],
        trades=[{"symbol": "000001.SZ", "entry_date": "2024-01-02"}],
        skipped_trades=[{"symbol": "300001.SZ", "reason": "最大同时持仓已达上限"}],
        metrics={"纯结构组合轨": EquityMetrics(0.10, 0.05, 2.0)},
    )

    write_backtest_report(report, tmp_path)

    assert (tmp_path / "equity_curve.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert (tmp_path / "trades.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert (tmp_path / "skipped_trades.csv").read_bytes().startswith(b"\xef\xbb\xbf")

    metadata = json.loads((tmp_path / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["name"] == "mvp1-report-test"
    assert metadata["data_version"] == "fixture-2024"
    assert metadata["code_version"] == "test-sha"
    assert metadata["research_limitation"] == (
        "MVP-1 是日线代理研究系统，不等同于完整实盘交易系统。"
    )
    assert metadata["stock_pool"] == ["000001.SZ"]
    assert metadata["parameters"] == {"risk_per_trade": 0.01}

    metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["纯结构组合轨"]["cumulative_return"] == 0.10
