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
from suishi_north_backtest.output_contract import (
    CSV_ENCODING,
    mvp1_csv_specs,
    mvp1_json_specs,
    mvp1_required_files,
)


RESEARCH_LIMITATION = "MVP-1 是日线代理研究系统，不等同于完整实盘交易系统。"


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

    return write_mvp1_dataset_outputs(config, data_set)


def write_mvp1_dataset_outputs(
    config: BacktestConfig,
    data_set: Mvp1DataSet,
) -> BacktestResult:
    """将 Mvp1DataSet 写入标准 MVP-1 输出目录。

    供 mvp1_runner 等外部模块调用：先构造 Mvp1DataSet，再调用本函数写文件。
    """
    output_dir = config.normalized_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_specs = {s.filename: s for s in mvp1_csv_specs()}
    field_map = {
        "equity_curve.csv": "equity_curve",
        "trades.csv": "trades",
        "skipped_trades.csv": "skipped_trades",
        "candidates.csv": "candidates",
        "holdings.csv": "holdings",
        "benchmark_comparison.csv": "benchmark_comparison",
        "track_comparison.csv": "track_comparison",
        "sensitivity.csv": "sensitivity",
    }
    for filename, attr in field_map.items():
        _write_csv(
            output_dir / filename,
            csv_specs[filename].required_columns,
            getattr(data_set, attr),
        )

    _write_metrics(output_dir / "metrics.json", data_set, config)
    _write_metadata(output_dir / "run_metadata.json", config, data_set)

    return BacktestResult(output_dir=output_dir)


def _write_metrics(path: Path, data_set: Mvp1DataSet, config: BacktestConfig) -> None:
    metrics = {
        **data_set.metrics,
        "name": config.name,
        "research_limitation": RESEARCH_LIMITATION,
    }
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_metadata(path: Path, config: BacktestConfig, data_set: Mvp1DataSet) -> None:
    outputs = mvp1_required_files("full")
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
