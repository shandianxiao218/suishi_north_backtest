from __future__ import annotations

from pathlib import Path

import pytest

from suishi_north_backtest.market_data import (
    IndustryMap,
    MarketData,
    StockDaily,
)
from suishi_north_backtest.universe import (
    TradabilityAudit,
    UniverseEntry,
    build_universe,
    build_universe_with_audit,
)


# ---- 辅助函数 ----


def make_market_data(stocks: list[StockDaily], **kwargs: object) -> MarketData:
    return MarketData(
        stock_daily=stocks,
        index_daily=kwargs.get("index_daily", []),
        industry_map=kwargs.get("industry_map", []),
        industry_daily_amount=kwargs.get("industry_daily_amount", []),
        trading_calendar=kwargs.get("trading_calendar", []),
    )


def stock(
    trade_date: str = "2024-01-02",
    symbol: str = "000001",
    open: float | None = 10.0,
    close: float | None = 10.5,
    high: float | None = 11.0,
    low: float | None = 9.5,
    volume: float | None = 100000.0,
    amount: float | None = 1000000.0,
    is_st: bool = False,
    is_suspended: bool = False,
    limit_up: float | None = None,
    limit_down: float | None = None,
) -> StockDaily:
    return StockDaily(
        trade_date=trade_date,
        symbol=symbol,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        amount=amount,
        is_st=is_st,
        limit_up=limit_up,
        limit_down=limit_down,
        is_suspended=is_suspended,
    )


# ---- 测试 ----


def test_st_stock_excluded() -> None:
    stocks = [
        stock(symbol="000001", is_st=True, close=5.0),
        stock(symbol="000002", is_st=False, close=10.0),
    ]
    md = make_market_data(stocks)
    universe = build_universe(md)

    symbols = {e.symbol for e in universe}
    assert "000001" not in symbols
    assert "000002" in symbols


def test_suspended_stock_excluded_on_suspend_day() -> None:
    stocks = [
        stock(symbol="000001", is_suspended=True, open=None, close=None),
    ]
    md = make_market_data(stocks)
    universe = build_universe(md)

    symbols = {e.symbol for e in universe}
    assert "000001" not in symbols


def test_new_stock_excluded() -> None:
    """上市不足 120 个交易日的新股被排除。"""
    stocks = [
        stock(symbol="301001"),
    ]
    md = make_market_data(stocks)
    listing_dates = {"301001": "2023-10-01"}
    universe = build_universe(md, as_of="2024-01-02", listing_dates=listing_dates)

    symbols = {e.symbol for e in universe}
    assert "301001" not in symbols


def test_old_enough_stock_included() -> None:
    """上市超过 120 个交易日的股票被纳入。"""
    stocks = [
        stock(symbol="000001"),
    ]
    md = make_market_data(stocks)
    listing_dates = {"000001": "2020-01-01"}
    # 无交易日历，用近似估算：2020-01-01 到 2024-01-02 约 1000 个交易日 >> 120
    universe = build_universe(md, as_of="2024-01-02", listing_dates=listing_dates)

    symbols = {e.symbol for e in universe}
    assert "000001" in symbols


def test_limit_up_buy_skipped() -> None:
    """一字涨停无法买入：收盘价等于涨停价。"""
    stocks = [
        stock(symbol="000001", close=11.0, limit_up=11.0),
    ]
    md = make_market_data(stocks)
    _, audit = build_universe_with_audit(md)

    audited = {a.symbol: a for a in audit}
    assert audited["000001"].buy_restricted is True


def test_limit_down_sell_deferred() -> None:
    """一字跌停无法卖出：收盘价等于跌停价。"""
    stocks = [
        stock(symbol="000001", close=9.0, limit_down=9.0),
    ]
    md = make_market_data(stocks)
    _, audit = build_universe_with_audit(md)

    audited = {a.symbol: a for a in audit}
    assert audited["000001"].sell_deferred is True


def test_normal_stock_tradable() -> None:
    stocks = [
        stock(symbol="000001", close=10.5, limit_up=11.55, limit_down=9.45),
    ]
    md = make_market_data(stocks)
    universe, audit = build_universe_with_audit(md)

    symbols = {e.symbol for e in universe}
    assert "000001" in symbols
    # 正常可交易股票不生成审计记录
    stock_audit = [a for a in audit if a.symbol == "000001"]
    assert len(stock_audit) == 0


def test_universe_output_contains_correct_fields() -> None:
    stocks = [stock(symbol="000001")]
    md = make_market_data(stocks)
    universe = build_universe(md)

    entry = universe[0]
    assert hasattr(entry, "trade_date")
    assert hasattr(entry, "symbol")
    assert hasattr(entry, "industry_level2")


def test_tradability_audit_contains_reason() -> None:
    stocks = [
        stock(symbol="000001", is_st=True),
    ]
    md = make_market_data(stocks)
    _, audit = build_universe_with_audit(md)

    assert len(audit) == 1
    assert audit[0].reason is not None
    assert "ST" in audit[0].reason


def test_multiple_exclusion_reasons() -> None:
    stocks = [
        stock(symbol="000001", is_st=True),
        stock(symbol="000002", is_suspended=True, open=None),
        stock(symbol="000003", close=10.5),
    ]
    md = make_market_data(stocks)
    universe, audit = build_universe_with_audit(md)

    universe_symbols = {e.symbol for e in universe}
    assert "000003" in universe_symbols
    assert len(audit) == 2


def test_universe_without_list_date_includes_all_non_st() -> None:
    """没有 listing_dates 参数时，不因新股规则排除。"""
    stocks = [
        stock(symbol="000001"),
    ]
    md = make_market_data(stocks)
    universe = build_universe(md, as_of="2024-01-02")

    symbols = {e.symbol for e in universe}
    assert "000001" in symbols
