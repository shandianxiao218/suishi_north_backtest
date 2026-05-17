from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from suishi_north_backtest import __version__
from suishi_north_backtest.config import BacktestConfig


RESEARCH_LIMITATION = "MVP-1 是日线代理研究系统，不等同于完整实盘交易系统。"
CSV_ENCODING = "utf-8-sig"


@dataclass(frozen=True)
class BacktestResult:
    """MVP-1 回测运行结果。"""

    output_dir: Path


def run_mvp1_backtest(config: BacktestConfig) -> BacktestResult:
    """运行最小 MVP-1 组合回测骨架。"""

    output_dir = config.normalized_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_equity_curve(output_dir / "equity_curve.csv", config)
    _write_trades(output_dir / "trades.csv")
    _write_skipped_trades(output_dir / "skipped_trades.csv")
    _write_metadata(output_dir / "run_metadata.json", config)

    return BacktestResult(output_dir=output_dir)


def _write_equity_curve(path: Path, config: BacktestConfig) -> None:
    with path.open("w", newline="", encoding=CSV_ENCODING) as file:
        writer = csv.DictWriter(file, fieldnames=["date", "cash", "equity"])
        writer.writeheader()
        writer.writerow(
            {
                "date": config.start_date,
                "cash": config.initial_cash,
                "equity": config.initial_cash,
            }
        )
        writer.writerow(
            {
                "date": config.end_date,
                "cash": config.initial_cash,
                "equity": config.initial_cash,
            }
        )


def _write_trades(path: Path) -> None:
    with path.open("w", newline="", encoding=CSV_ENCODING) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "trade_id",
                "symbol",
                "entry_date",
                "entry_price",
                "exit_date",
                "exit_price",
                "exit_reason",
            ],
        )
        writer.writeheader()


def _write_skipped_trades(path: Path) -> None:
    with path.open("w", newline="", encoding=CSV_ENCODING) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["signal_date", "symbol", "reason"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "signal_date": "",
                "symbol": "",
                "reason": "MVP-1 骨架阶段暂无真实候选，后续 issue 接入。",
            }
        )


def _write_metadata(path: Path, config: BacktestConfig) -> None:
    metadata = {
        "name": config.name,
        "start_date": config.start_date,
        "end_date": config.end_date,
        "initial_cash": config.initial_cash,
        "code_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "research_limitation": RESEARCH_LIMITATION,
        "outputs": [
            "equity_curve.csv",
            "trades.csv",
            "skipped_trades.csv",
            "run_metadata.json",
        ],
    }
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
