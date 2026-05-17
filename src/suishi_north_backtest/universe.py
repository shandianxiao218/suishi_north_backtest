from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from suishi_north_backtest.data import MarketBar


CORE_BOARDS = {"main", "chinext", "star"}


@dataclass(frozen=True)
class StockInfo:
    """股票基础信息。"""

    symbol: str
    name: str
    board: str
    listing_date: date
    is_delisting: bool = False


@dataclass(frozen=True)
class StockPoolRules:
    """MVP-1 股票池过滤参数。"""

    min_listing_trading_days: int = 120
    min_recent_average_amount: float = 20_000_000
    recent_liquidity_days: int = 20


@dataclass(frozen=True)
class StockPoolSelection:
    """股票池选择结果。"""

    included: list[StockInfo]
    excluded_reasons: dict[str, list[str]]


def select_mvp1_stock_pool(
    stocks: list[StockInfo],
    bars_by_symbol: dict[str, list[MarketBar]],
    *,
    as_of: date,
    rules: StockPoolRules = StockPoolRules(),
) -> StockPoolSelection:
    """选择 MVP-1 沪深核心 A 股股票池。"""

    included: list[StockInfo] = []
    excluded_reasons: dict[str, list[str]] = {}

    for stock in stocks:
        visible_bars = _visible_bars(bars_by_symbol.get(stock.symbol, []), as_of)
        reasons = _exclude_reasons(stock, visible_bars, rules)
        if reasons:
            excluded_reasons[stock.symbol] = reasons
        else:
            included.append(stock)

    return StockPoolSelection(
        included=included,
        excluded_reasons=excluded_reasons,
    )


def _exclude_reasons(
    stock: StockInfo,
    visible_bars: list[MarketBar],
    rules: StockPoolRules,
) -> list[str]:
    reasons: list[str] = []
    if stock.board not in CORE_BOARDS:
        reasons.append("非沪深核心板块")
    if "ST" in stock.name.upper():
        reasons.append("ST 或 *ST")
    if stock.is_delisting:
        reasons.append("退市整理股票")
    if len(visible_bars) < rules.min_listing_trading_days:
        reasons.append(f"上市交易日不足 {rules.min_listing_trading_days} 日")
    recent_bars = visible_bars[-rules.recent_liquidity_days :]
    if recent_bars and all(not bar.has_open_price for bar in recent_bars):
        reasons.append(f"最近 {rules.recent_liquidity_days} 日长期停牌")
    if recent_bars and _average_amount(recent_bars) < rules.min_recent_average_amount:
        threshold = int(rules.min_recent_average_amount)
        reasons.append(
            f"最近 {rules.recent_liquidity_days} 日平均成交额低于 {threshold}"
        )
    return reasons


def _visible_bars(bars: list[MarketBar], as_of: date) -> list[MarketBar]:
    return sorted(
        [bar for bar in bars if bar.date <= as_of],
        key=lambda bar: bar.date,
    )


def _average_amount(bars: list[MarketBar]) -> float:
    return sum(bar.amount for bar in bars) / len(bars)
