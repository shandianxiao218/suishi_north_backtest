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
    stock_name: str = "",
    is_delisting: bool = False,
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
        stock_name=stock_name,
        is_delisting=is_delisting,
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
    """一字涨停无法买入：open==high==low==close==limit_up。"""
    stocks = [
        stock(symbol="000001", open=11.0, high=11.0, low=11.0, close=11.0, limit_up=11.0),
    ]
    md = make_market_data(stocks)
    _, audit = build_universe_with_audit(md)

    audited = {a.symbol: a for a in audit}
    assert audited["000001"].buy_restricted is True


def test_normal_limit_up_not_restricted() -> None:
    """普通涨停（有日内波动）不应视为一字涨停，不限制买入。"""
    stocks = [
        stock(symbol="000001", open=10.5, high=11.0, low=10.3, close=11.0, limit_up=11.0),
    ]
    md = make_market_data(stocks)
    universe, audit = build_universe_with_audit(md)

    symbols = {e.symbol for e in universe}
    assert "000001" in symbols
    # 普通涨停不应产生 buy_restricted 审计
    stock_audit = [a for a in audit if a.symbol == "000001"]
    restricted = [a for a in stock_audit if a.buy_restricted]
    assert len(restricted) == 0


def test_limit_down_sell_deferred() -> None:
    """一字跌停无法卖出：open==high==low==close==limit_down。"""
    stocks = [
        stock(symbol="000001", open=9.0, high=9.0, low=9.0, close=9.0, limit_down=9.0),
    ]
    md = make_market_data(stocks)
    _, audit = build_universe_with_audit(md)

    audited = {a.symbol: a for a in audit}
    assert audited["000001"].sell_deferred is True


def test_normal_limit_down_not_deferred() -> None:
    """普通跌停（有日内波动）不应视为一字跌停，不延迟卖出。"""
    stocks = [
        stock(symbol="000001", open=9.5, high=9.8, low=9.0, close=9.0, limit_down=9.0),
    ]
    md = make_market_data(stocks)
    universe, audit = build_universe_with_audit(md)

    symbols = {e.symbol for e in universe}
    assert "000001" in symbols
    # 普通跌停不应产生 sell_deferred 审计
    stock_audit = [a for a in audit if a.symbol == "000001"]
    deferred = [a for a in stock_audit if a.sell_deferred]
    assert len(deferred) == 0


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


# ---- Issue #32：真实 A 股股票池与可交易性过滤 ----


def test_excludes_beijing_exchange() -> None:
    """北交所股票（8xxxxx / 4xxxxx）被排除。"""
    stocks = [
        stock(symbol="430047", amount=5_000_000),   # 新三板/北交所
        stock(symbol="830799", amount=5_000_000),   # 北交所
        stock(symbol="000001", amount=1_000_000),   # 主板
    ]
    md = make_market_data(stocks)
    universe = build_universe(md)

    symbols = {e.symbol for e in universe}
    assert "000001" in symbols
    assert "430047" not in symbols
    assert "830799" not in symbols


def test_includes_main_board_chinext_star() -> None:
    """主板、创业板、科创板纳入。"""
    stocks = [
        stock(symbol="000001", amount=1_000_000),   # 主板 SZ
        stock(symbol="600519", amount=1_000_000),   # 主板 SH
        stock(symbol="601318", amount=1_000_000),   # 主板 SH
        stock(symbol="300001", amount=1_000_000),   # 创业板
        stock(symbol="301001", amount=1_000_000),   # 创业板
        stock(symbol="688001", amount=1_000_000),   # 科创板
    ]
    md = make_market_data(stocks)
    universe = build_universe(md)

    symbols = {e.symbol for e in universe}
    assert symbols == {"000001", "600519", "601318", "300001", "301001", "688001"}


def test_excludes_st_from_is_st_field() -> None:
    """is_st 字段为 True 的股票被排除。"""
    stocks = [
        stock(symbol="000001", is_st=True),
        stock(symbol="000002", is_st=False),
    ]
    md = make_market_data(stocks)
    universe = build_universe(md)

    symbols = {e.symbol for e in universe}
    assert "000001" not in symbols
    assert "000002" in symbols


def test_excludes_st_from_stock_name() -> None:
    """stock_name 以 ST 或 *ST 开头的股票被排除。"""
    stocks = [
        stock(symbol="000001", stock_name="ST万科"),
        stock(symbol="000002", stock_name="*ST金科"),
        stock(symbol="000003", stock_name="平安银行"),
    ]
    md = make_market_data(stocks)
    universe = build_universe(md)

    symbols = {e.symbol for e in universe}
    assert "000001" not in symbols
    assert "000002" not in symbols
    assert "000003" in symbols


def test_excludes_delisting_stock() -> None:
    """退市整理股票被排除。"""
    stocks = [
        stock(symbol="000001", is_delisting=True),
        stock(symbol="000002", is_delisting=False),
    ]
    md = make_market_data(stocks)
    universe = build_universe(md)

    symbols = {e.symbol for e in universe}
    assert "000001" not in symbols
    assert "000002" in symbols


def test_excludes_delisting_from_stock_name() -> None:
    """stock_name 含"退"字的退市股票被排除。"""
    stocks = [
        stock(symbol="000001", stock_name="退市海润"),
        stock(symbol="000002", stock_name="正常股票"),
    ]
    md = make_market_data(stocks)
    universe = build_universe(md)

    symbols = {e.symbol for e in universe}
    assert "000001" not in symbols
    assert "000002" in symbols


def test_excludes_low_liquidity_stock() -> None:
    """成交额低于阈值的低流动性股票被排除。"""
    stocks = [
        stock(symbol="000001", amount=500_000),      # 低于默认阈值
        stock(symbol="000002", amount=10_000_000),    # 正常
    ]
    md = make_market_data(stocks)
    universe = build_universe(md, min_amount=1_000_000)

    symbols = {e.symbol for e in universe}
    assert "000001" not in symbols
    assert "000002" in symbols


def test_buy_restricted_only_for_one_word_limit_up() -> None:
    """只有一字涨停（open==high==low==close==limit_up）才限制买入。"""
    # 一字涨停
    stocks_restricted = [
        stock(symbol="000001", open=11.0, high=11.0, low=11.0, close=11.0, limit_up=11.0),
    ]
    md = make_market_data(stocks_restricted)
    _, audit = build_universe_with_audit(md)
    assert any(a.buy_restricted for a in audit if a.symbol == "000001")

    # 普通涨停（非一字）不应限制
    stocks_normal = [
        stock(symbol="000002", open=10.5, high=11.0, low=10.3, close=11.0, limit_up=11.0),
    ]
    md2 = make_market_data(stocks_normal)
    universe2, audit2 = build_universe_with_audit(md2)
    assert "000002" in {e.symbol for e in universe2}
    assert not any(a.buy_restricted for a in audit2 if a.symbol == "000002")


def test_sell_deferred_only_for_one_word_limit_down() -> None:
    """只有一字跌停（open==high==low==close==limit_down）才延迟卖出。"""
    # 一字跌停
    stocks_deferred = [
        stock(symbol="000001", open=9.0, high=9.0, low=9.0, close=9.0, limit_down=9.0),
    ]
    md = make_market_data(stocks_deferred)
    _, audit = build_universe_with_audit(md)
    assert any(a.sell_deferred for a in audit if a.symbol == "000001")

    # 普通跌停（非一字）不应延迟
    stocks_normal = [
        stock(symbol="000002", open=9.5, high=9.8, low=9.0, close=9.0, limit_down=9.0),
    ]
    md2 = make_market_data(stocks_normal)
    universe2, audit2 = build_universe_with_audit(md2)
    assert "000002" in {e.symbol for e in universe2}
    assert not any(a.sell_deferred for a in audit2 if a.symbol == "000002")


def test_beijing_exchange_audit_has_reason() -> None:
    """北交所排除有审计原因。"""
    stocks = [
        stock(symbol="830799", amount=5_000_000),
    ]
    md = make_market_data(stocks)
    _, audit = build_universe_with_audit(md)

    assert len(audit) == 1
    assert "北交所" in audit[0].reason


def test_delisting_audit_has_reason() -> None:
    """退市排除有审计原因。"""
    stocks = [
        stock(symbol="000001", is_delisting=True),
    ]
    md = make_market_data(stocks)
    _, audit = build_universe_with_audit(md)

    assert len(audit) == 1
    assert "退市" in audit[0].reason


def test_low_liquidity_audit_has_reason() -> None:
    """低流动性排除有审计原因。"""
    stocks = [
        stock(symbol="000001", amount=500),
    ]
    md = make_market_data(stocks)
    _, audit = build_universe_with_audit(md, min_amount=1_000_000)

    assert len(audit) >= 1
    liquidity_audits = [a for a in audit if "流动性" in a.reason or "成交额" in a.reason]
    assert len(liquidity_audits) >= 1
