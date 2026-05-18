from __future__ import annotations

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


def test_a_stock_data_provider_fails_with_clear_message() -> None:
    config = BacktestConfig(
        data_source="a-stock-data",
        data_snapshot="real-snapshot-test",
    )

    with pytest.raises(NotImplementedError, match="a-stock-data provider is not implemented"):
        AStockDataProvider().load(config)


def test_build_data_provider_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="Unsupported data source"):
        build_data_provider("unknown")
