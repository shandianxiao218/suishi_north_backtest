from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.data import (
    AStockDataProvider,
    FixtureDataProvider,
    build_data_provider,
)


def test_fixture_provider_returns_unified_dataset() -> None:
    config = BacktestConfig(name="fixture-provider-test", data_source="fixture")

    data_set = FixtureDataProvider().load(config)

    assert data_set.data_version == "deterministic-fixture-v1-2026-05-18"
    assert data_set.universe == "fixture-core-a-share-sample"
    assert data_set.trades
    assert data_set.candidates
    assert data_set.metrics["trade_count"] == 1


def test_fixture_provider_allows_snapshot_override() -> None:
    config = BacktestConfig(
        data_source="fixture",
        data_snapshot="fixture-snapshot-local-test",
    )

    data_set = FixtureDataProvider().load(config)

    assert data_set.data_version == "fixture-snapshot-local-test"


def test_build_data_provider_resolves_fixture() -> None:
    provider = build_data_provider("fixture")

    assert isinstance(provider, FixtureDataProvider)


def test_build_data_provider_resolves_a_stock_data_boundary() -> None:
    provider = build_data_provider("a-stock-data")

    assert isinstance(provider, AStockDataProvider)


def test_a_stock_data_provider_requires_snapshot_name(tmp_path: Path) -> None:
    config = BacktestConfig(
        data_source="a-stock-data",
        data_dir=tmp_path,
    )

    with pytest.raises(ValueError, match="--data-snapshot is required"):
        AStockDataProvider().load(config)


def test_a_stock_data_provider_reads_snapshot_directory(tmp_path: Path) -> None:
    snapshot_dir = create_snapshot(tmp_path, "snapshot-001")
    config = BacktestConfig(
        data_source="a-stock-data",
        data_snapshot="snapshot-001",
        data_dir=tmp_path,
    )

    data_set = AStockDataProvider().load(config)

    assert snapshot_dir.exists()
    assert data_set.data_version == "a-stock-data-snapshot-001"
    assert data_set.parameter_set == "ADR-0002 defaults"
    assert data_set.universe == "沪深 A 股核心股票池"
    assert data_set.trades[0]["symbol"] == "000001.SZ"
    assert data_set.candidates[0]["signal_date"] == "2024-01-02"
    assert data_set.candidates[0]["track"] == "mainline_filtered"
    assert data_set.metrics["trade_count"] == 1


def test_a_stock_data_provider_requires_manifest(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot-missing-manifest"
    snapshot_dir.mkdir()

    config = BacktestConfig(
        data_source="a-stock-data",
        data_snapshot="snapshot-missing-manifest",
        data_dir=tmp_path,
    )

    with pytest.raises(FileNotFoundError, match="manifest.json"):
        AStockDataProvider().load(config)


def test_a_stock_data_provider_requires_all_snapshot_files(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot-missing-files"
    snapshot_dir.mkdir()
    write_json(
        snapshot_dir / "manifest.json",
        {"data_version": "a-stock-data-snapshot-missing"},
    )

    config = BacktestConfig(
        data_source="a-stock-data",
        data_snapshot="snapshot-missing-files",
        data_dir=tmp_path,
    )

    with pytest.raises(FileNotFoundError, match="missing required files"):
        AStockDataProvider().load(config)


def test_a_stock_data_provider_requires_manifest_data_version(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot-empty-version"
    snapshot_dir.mkdir()
    write_json(snapshot_dir / "manifest.json", {"data_version": ""})

    config = BacktestConfig(
        data_source="a-stock-data",
        data_snapshot="snapshot-empty-version",
        data_dir=tmp_path,
    )

    with pytest.raises(ValueError, match="data_version"):
        AStockDataProvider().load(config)


def test_build_data_provider_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="Unsupported data source"):
        build_data_provider("unknown")


def create_snapshot(root: Path, name: str) -> Path:
    snapshot_dir = root / name
    snapshot_dir.mkdir()
    write_json(
        snapshot_dir / "manifest.json",
        {
            "data_version": "a-stock-data-snapshot-001",
            "parameter_set": "ADR-0002 defaults",
            "universe": "沪深 A 股核心股票池",
        },
    )
    write_json(
        snapshot_dir / "metrics.json",
        {"name": "test", "initial_cash": 1000000, "ending_equity": 1010000, "total_return": 0.01, "max_drawdown": 0.005, "trade_count": 1},
    )
    write_csv(snapshot_dir / "equity_curve.csv", ["date", "cash", "equity", "drawdown", "track"], [])
    write_csv(
        snapshot_dir / "trades.csv",
        ["trade_id", "track", "symbol", "entry_signal_date", "entry_date", "entry_price",
         "entry_shares", "exit_trigger_date", "exit_date", "exit_price", "exit_reason",
         "commission", "stamp_tax", "slippage_cost", "total_cost", "gross_pnl", "net_pnl",
         "first_target_achieved", "audit_note"],
        [{"trade_id": "T-001", "track": "mainline_filtered", "symbol": "000001.SZ",
          "entry_signal_date": "2024-01-02", "entry_date": "2024-01-03", "entry_price": "10.0",
          "entry_shares": "1000", "exit_trigger_date": "", "exit_date": "", "exit_price": "",
          "exit_reason": "", "commission": "3.0", "stamp_tax": "0", "slippage_cost": "5.0",
          "total_cost": "8.0", "gross_pnl": "0", "net_pnl": "-8.0",
          "first_target_achieved": "false", "audit_note": "test"}],
    )
    write_csv(snapshot_dir / "skipped_trades.csv", ["signal_date", "track", "symbol", "reason"], [])
    write_csv(
        snapshot_dir / "candidates.csv",
        ["signal_date", "track", "symbol", "industry_level2", "is_strong_mainline",
         "a_date", "a_price", "b_date", "b_price", "c_date", "c_price",
         "ab_gain_pct", "bc_retracement_pct", "distance_to_c_low_pct",
         "weekly_filter_passed", "annual_filter_passed", "score", "audit_note"],
        [{"signal_date": "2024-01-02", "track": "mainline_filtered", "symbol": "000001.SZ",
          "industry_level2": "test_industry", "is_strong_mainline": "true",
          "a_date": "2023-12-20", "a_price": "8.0", "b_date": "2023-12-28", "b_price": "10.0",
          "c_date": "2024-01-02", "c_price": "9.0", "ab_gain_pct": "25.0",
          "bc_retracement_pct": "50.0", "distance_to_c_low_pct": "3.0",
          "weekly_filter_passed": "true", "annual_filter_passed": "true",
          "score": "85.0", "audit_note": "test"}],
    )
    write_csv(
        snapshot_dir / "holdings.csv",
        ["date", "track", "symbol", "shares", "cost_basis", "market_value",
         "unrealized_pnl", "holding_days", "highest_close_since_entry", "audit_note"],
        [],
    )
    write_csv(
        snapshot_dir / "benchmark_comparison.csv",
        ["period", "benchmark", "strategy_return", "benchmark_return", "excess_return",
         "max_drawdown", "return_drawdown_ratio", "audit_note"],
        [],
    )
    write_csv(
        snapshot_dir / "track_comparison.csv",
        ["metric", "pure_structure_track", "mainline_filtered_track", "delta", "audit_note"],
        [],
    )
    write_csv(
        snapshot_dir / "sensitivity.csv",
        ["parameter", "baseline_value", "variant_value", "sample_in_metric",
         "sample_out_metric", "overfit_risk", "accepted", "audit_note"],
        [],
    )
    return snapshot_dir


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
