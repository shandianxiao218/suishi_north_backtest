from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from suishi_north_backtest.market_data import (
    IndustryDailyAmount,
    IndustryMap,
    IndexDaily,
    MarketData,
    StockDaily,
    TradingCalendarEntry,
    load_market_data,
)
from suishi_north_backtest.raw_data import validate_raw_snapshot


# ---- 辅助函数 ----


STOCK_DAILY_FIELDS = [
    "trade_date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]

INDEX_DAILY_FIELDS = [
    "trade_date",
    "index_code",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]


def write_manifest(snapshot_dir: Path) -> None:
    manifest = {
        "data_version": "a-stock-data-raw-test",
        "source": "a-stock-data",
        "created_at": "2026-05-19T00:00:00+08:00",
        "stock_daily_file": "stock_daily.csv",
        "index_daily_file": "index_daily.csv",
        "industry_map_file": "industry_map.csv",
        "industry_daily_amount_file": "industry_daily_amount.csv",
        "trading_calendar_file": "trading_calendar.csv",
    }
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def write_csv(
    snapshot_dir: Path,
    filename: str,
    fields: list[str],
    rows: list[list[str]],
) -> None:
    path = snapshot_dir / filename
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        writer.writerows(rows)


def write_valid_snapshot_with_data(snapshot_dir: Path) -> None:
    write_manifest(snapshot_dir)

    write_csv(
        snapshot_dir,
        "stock_daily.csv",
        STOCK_DAILY_FIELDS,
        [
            ["2024-01-02", "000001", "10.5", "11.0", "10.3", "10.8", "100000", "1080000"],
            ["2024-01-02", "600519", "1800.0", "1810.0", "1795.0", "1805.0", "5000", "9025000"],
            ["2024-01-03", "000001", "10.8", "11.2", "10.7", "11.0", "80000", "880000"],
            ["2024-01-03", "600519", "", "", "", "", "", ""],
        ],
    )

    write_csv(
        snapshot_dir,
        "index_daily.csv",
        INDEX_DAILY_FIELDS,
        [
            ["2024-01-02", "000300", "3500.0", "3520.0", "3490.0", "3510.0", "10000000", "35000000000"],
            ["2024-01-03", "000300", "3510.0", "3530.0", "3505.0", "3525.0", "9500000", "33500000000"],
        ],
    )

    write_csv(
        snapshot_dir,
        "industry_map.csv",
        ["symbol", "industry_level2"],
        [
            ["000001", "银行"],
            ["600519", "白酒"],
        ],
    )

    write_csv(
        snapshot_dir,
        "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        [
            ["2024-01-02", "银行", "5000000000"],
            ["2024-01-02", "白酒", "8000000000"],
            ["2024-01-03", "银行", "4500000000"],
            ["2024-01-03", "白酒", "7500000000"],
        ],
    )

    write_csv(
        snapshot_dir,
        "trading_calendar.csv",
        ["trade_date", "is_open"],
        [
            ["2024-01-02", "1"],
            ["2024-01-03", "1"],
            ["2024-01-04", "1"],
            ["2024-01-05", "0"],
        ],
    )


# ---- 测试 ----


def test_load_market_data_returns_market_data(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    assert isinstance(md, MarketData)


# ---- stock_daily 测试 ----


def test_stock_daily_numeric_fields_are_float(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    first = md.stock_daily[0]
    assert isinstance(first.open, float)
    assert isinstance(first.high, float)
    assert isinstance(first.low, float)
    assert isinstance(first.close, float)
    assert isinstance(first.volume, float)
    assert isinstance(first.amount, float)


def test_stock_daily_sorted_by_trade_date_then_symbol(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    dates = [s.trade_date for s in md.stock_daily]
    assert dates == sorted(dates)

    # 同日期内按 symbol 排序
    jan2_stocks = [s for s in md.stock_daily if s.trade_date == "2024-01-02"]
    symbols = [s.symbol for s in jan2_stocks]
    assert symbols == sorted(symbols)


def test_stock_daily_empty_values_become_none(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    # 600519 在 2024-01-03 有空行
    suspended = [s for s in md.stock_daily if s.symbol == "600519" and s.trade_date == "2024-01-03"]
    assert len(suspended) == 1
    assert suspended[0].open is None
    assert suspended[0].close is None
    assert suspended[0].is_suspended is True


def test_stock_daily_non_empty_values_not_suspended(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    active = [s for s in md.stock_daily if s.symbol == "000001" and s.trade_date == "2024-01-02"]
    assert len(active) == 1
    assert active[0].is_suspended is False


# ---- index_daily 测试 ----


def test_index_daily_numeric_fields_are_float(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    first = md.index_daily[0]
    assert isinstance(first.open, float)
    assert isinstance(first.close, float)


def test_index_daily_sorted_by_trade_date(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    dates = [i.trade_date for i in md.index_daily]
    assert dates == sorted(dates)


# ---- industry_map 测试 ----


def test_industry_map_reads_chinese_names(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    symbols = {m.symbol for m in md.industry_map}
    industries = {m.industry_level2 for m in md.industry_map}
    assert "000001" in symbols
    assert "银行" in industries
    assert "白酒" in industries


# ---- industry_daily_amount 测试 ----


def test_industry_daily_amount_numeric(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    first = md.industry_daily_amount[0]
    assert isinstance(first.amount, float)


def test_industry_daily_amount_sorted(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    dates = [d.trade_date for d in md.industry_daily_amount]
    assert dates == sorted(dates)


# ---- trading_calendar 测试 ----


def test_trading_calendar_is_open_is_bool(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    for entry in md.trading_calendar:
        assert isinstance(entry.is_open, bool)


def test_trading_calendar_sorted(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    dates = [e.trade_date for e in md.trading_calendar]
    assert dates == sorted(dates)


# ---- stock_daily 衍生字段测试 ----


def test_stock_daily_is_st_defaults_false(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    for s in md.stock_daily:
        assert isinstance(s.is_st, bool)
        assert s.is_st is False


def test_stock_daily_limit_fields_default_none(tmp_path: Path) -> None:
    """原始 CSV 没有 limit_up/limit_down 列时，字段为 None。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    for s in md.stock_daily:
        assert s.limit_up is None
        assert s.limit_down is None


def test_stock_daily_with_optional_limit_columns(tmp_path: Path) -> None:
    """如果原始 CSV 包含 limit_up/limit_down 列，应能读取。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_manifest(snapshot_dir)

    extended_fields = STOCK_DAILY_FIELDS + ["limit_up", "limit_down"]
    write_csv(
        snapshot_dir,
        "stock_daily.csv",
        extended_fields,
        [
            ["2024-01-02", "000001", "10.5", "11.0", "10.3", "10.8", "100000", "1080000", "11.55", "9.45"],
        ],
    )
    write_csv(snapshot_dir, "index_daily.csv", INDEX_DAILY_FIELDS, [["2024-01-02", "000300", "3500.0", "3520.0", "3490.0", "3510.0", "10000000", "35000000000"]])
    write_csv(snapshot_dir, "industry_map.csv", ["symbol", "industry_level2"], [["000001", "银行"]])
    write_csv(snapshot_dir, "industry_daily_amount.csv", ["trade_date", "industry_level2", "amount"], [["2024-01-02", "银行", "5000000000"]])
    write_csv(snapshot_dir, "trading_calendar.csv", ["trade_date", "is_open"], [["2024-01-02", "1"]])

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    first = md.stock_daily[0]
    assert first.limit_up == 11.55
    assert first.limit_down == 9.45


# ---- 集成：从 snapshot_dir 直接加载 ----


def test_load_market_data_count(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_valid_snapshot_with_data(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    md = load_market_data(snapshot_dir, manifest)

    assert len(md.stock_daily) == 4
    assert len(md.index_daily) == 2
    assert len(md.industry_map) == 2
    assert len(md.industry_daily_amount) == 4
    assert len(md.trading_calendar) == 4
