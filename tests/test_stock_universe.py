from __future__ import annotations

from datetime import date

from suishi_north_backtest.data import MarketBar
from suishi_north_backtest.universe import (
    StockInfo,
    StockPoolRules,
    select_mvp1_stock_pool,
)


def bar(
    day: date,
    amount: float = 30_000_000,
    *,
    has_open_price: bool = True,
) -> MarketBar:
    return MarketBar(
        symbol="",
        date=day,
        open=10.0 if has_open_price else None,
        high=10.5 if has_open_price else None,
        low=9.8 if has_open_price else None,
        close=10.2,
        volume=1_000_000 if has_open_price else 0,
        amount=amount,
        adjust_factor=1.0,
        is_suspended=not has_open_price,
        has_open_price=has_open_price,
    )


def test_selects_only_hushen_core_pool_tradable_stocks() -> None:
    stocks = [
        StockInfo(
            symbol="600000.SH",
            name="浦发银行",
            board="main",
            listing_date=date(2000, 1, 1),
        ),
        StockInfo(
            symbol="300001.SZ",
            name="特锐德",
            board="chinext",
            listing_date=date(2009, 10, 30),
        ),
        StockInfo(
            symbol="688001.SH",
            name="华兴源创",
            board="star",
            listing_date=date(2019, 7, 22),
        ),
        StockInfo(
            symbol="430047.BJ",
            name="北交所样本",
            board="beijing",
            listing_date=date(2020, 1, 1),
        ),
        StockInfo(
            symbol="000001.SZ",
            name="*ST 平安",
            board="main",
            listing_date=date(1991, 4, 3),
        ),
        StockInfo(
            symbol="002001.SZ",
            name="退市样本",
            board="main",
            listing_date=date(2004, 6, 25),
            is_delisting=True,
        ),
    ]
    bars_by_symbol = {
        stock.symbol: [bar(date(2024, 1, day)) for day in range(1, 6)]
        for stock in stocks
    }

    selection = select_mvp1_stock_pool(
        stocks,
        bars_by_symbol,
        as_of=date(2024, 1, 5),
        rules=StockPoolRules(min_listing_trading_days=3),
    )

    assert [stock.symbol for stock in selection.included] == [
        "600000.SH",
        "300001.SZ",
        "688001.SH",
    ]
    assert selection.excluded_reasons == {
        "430047.BJ": ["非沪深核心板块"],
        "000001.SZ": ["ST 或 *ST"],
        "002001.SZ": ["退市整理股票"],
    }


def test_excludes_new_stocks_using_only_bars_available_as_of() -> None:
    stock = StockInfo(
        symbol="301001.SZ",
        name="新股样本",
        board="chinext",
        listing_date=date(2024, 1, 1),
    )
    bars_by_symbol = {
        "301001.SZ": [
            bar(date(2024, 1, day)) for day in range(1, 6)
        ]
        + [
            bar(date(2024, 2, day)) for day in range(1, 6)
        ]
    }

    selection = select_mvp1_stock_pool(
        [stock],
        bars_by_symbol,
        as_of=date(2024, 1, 5),
        rules=StockPoolRules(min_listing_trading_days=6),
    )

    assert selection.included == []
    assert selection.excluded_reasons == {
        "301001.SZ": ["上市交易日不足 6 日"]
    }


def test_excludes_long_suspended_and_low_liquidity_stocks() -> None:
    suspended = StockInfo(
        symbol="600001.SH",
        name="停牌样本",
        board="main",
        listing_date=date(2000, 1, 1),
    )
    illiquid = StockInfo(
        symbol="600002.SH",
        name="低流动性样本",
        board="main",
        listing_date=date(2000, 1, 1),
    )

    selection = select_mvp1_stock_pool(
        [suspended, illiquid],
        {
            "600001.SH": [
                bar(date(2024, 1, day), has_open_price=False)
                for day in range(1, 6)
            ],
            "600002.SH": [
                bar(date(2024, 1, day), amount=8_000_000)
                for day in range(1, 6)
            ],
        },
        as_of=date(2024, 1, 5),
        rules=StockPoolRules(
            min_listing_trading_days=3,
            recent_liquidity_days=5,
            min_recent_average_amount=10_000_000,
        ),
    )

    assert selection.included == []
    assert selection.excluded_reasons == {
        "600001.SH": ["最近 5 日长期停牌"],
        "600002.SH": ["最近 5 日平均成交额低于 10000000"],
    }
