from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.output_contract import (
    CSV_ENCODING,
    mvp1_csv_specs,
    validate_csv_header,
)


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
                    "failure_reason": "",
                    "as_of": "2024-01-02",
                    "signal_rule_version": "MVP1-SIGNAL-AUDIT-v1",
                    "score": "60.90",
                    "score_breakdown": "mainline=20.0; industry_rank=10.0; ab_gain=5.0; bc_retracement=6.7; distance_to_c=4.8; liquidity=4.4; weekly_filter=5.0; annual_filter=5.0; concentration_penalty=0.0; total=60.9",
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
    """读取 a-stock-data 本地快照目录。"""

    REQUIRED_CSV_FILES = {spec.filename for spec in mvp1_csv_specs()}

    def load(self, config: BacktestConfig) -> Mvp1DataSet:
        snapshot_dir = self._resolve_snapshot_dir(config)
        manifest = self._read_manifest(snapshot_dir)
        self._validate_required_files(snapshot_dir)
        self._validate_csv_headers(snapshot_dir)
        metrics = _read_json(snapshot_dir / "metrics.json")
        return Mvp1DataSet(
            data_version=str(manifest.get("data_version") or config.data_snapshot),
            parameter_set=str(manifest.get("parameter_set", "ADR-0002 defaults")),
            universe=str(manifest.get("universe", "a-stock-data snapshot")),
            equity_curve=_read_csv(snapshot_dir / "equity_curve.csv"),
            trades=_read_csv(snapshot_dir / "trades.csv"),
            skipped_trades=_read_csv(snapshot_dir / "skipped_trades.csv"),
            candidates=_read_csv(snapshot_dir / "candidates.csv"),
            holdings=_read_csv(snapshot_dir / "holdings.csv"),
            benchmark_comparison=_read_csv(snapshot_dir / "benchmark_comparison.csv"),
            track_comparison=_read_csv(snapshot_dir / "track_comparison.csv"),
            sensitivity=_read_csv(snapshot_dir / "sensitivity.csv"),
            metrics=metrics,
        )

    def _resolve_snapshot_dir(self, config: BacktestConfig) -> Path:
        if not config.data_snapshot:
            raise ValueError(
                "--data-snapshot is required when --data-source a-stock-data is used."
            )
        snapshot_dir = config.normalized_data_dir() / config.data_snapshot
        if not snapshot_dir.exists():
            raise FileNotFoundError(
                f"a-stock-data snapshot directory does not exist: {snapshot_dir}"
            )
        if not snapshot_dir.is_dir():
            raise NotADirectoryError(
                f"a-stock-data snapshot path is not a directory: {snapshot_dir}"
            )
        return snapshot_dir

    def _read_manifest(self, snapshot_dir: Path) -> dict[str, Any]:
        manifest_path = snapshot_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"a-stock-data snapshot missing manifest.json: {manifest_path}"
            )
        manifest = _read_json(manifest_path)
        data_version = manifest.get("data_version")
        if not data_version:
            raise ValueError("manifest.json must include non-empty data_version")
        return manifest

    def _validate_required_files(self, snapshot_dir: Path) -> None:
        missing = [
            filename
            for filename in [*self.REQUIRED_CSV_FILES, "metrics.json"]
            if not (snapshot_dir / filename).exists()
        ]
        if missing:
            raise FileNotFoundError(
                "a-stock-data snapshot missing required files: " + ", ".join(missing)
            )

    def _validate_csv_headers(self, snapshot_dir: Path) -> None:
        csv_specs = {s.filename: s for s in mvp1_csv_specs()}
        all_errors: list[str] = []
        for filename, spec in csv_specs.items():
            path = snapshot_dir / filename
            if not path.exists():
                continue
            with path.open("r", encoding=CSV_ENCODING, newline="") as f:
                reader = csv.reader(f)
                header = next(reader, [])
            errors = validate_csv_header(spec.filename, header, spec.required_columns)
            all_errors.extend(errors)
        if all_errors:
            raise ValueError("; ".join(all_errors))


def build_data_provider(name: str) -> DataProvider:
    if name == "fixture":
        return FixtureDataProvider()
    if name == "a-stock-data":
        return AStockDataProvider()
    raise ValueError(f"Unsupported data source: {name}")


def _read_csv(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
