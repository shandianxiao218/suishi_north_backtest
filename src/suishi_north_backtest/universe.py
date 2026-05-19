from __future__ import annotations

from dataclasses import dataclass

from suishi_north_backtest.market_data import MarketData, StockDaily


@dataclass
class UniverseEntry:
    trade_date: str
    symbol: str
    industry_level2: str


@dataclass
class TradabilityAudit:
    trade_date: str
    symbol: str
    reason: str
    buy_restricted: bool
    sell_deferred: bool


DEFAULT_NEW_STOCK_DAYS = 120
APPROX_TRADING_DAYS_PER_YEAR = 250


def build_universe(
    md: MarketData,
    as_of: str | None = None,
    new_stock_days: int = DEFAULT_NEW_STOCK_DAYS,
    listing_dates: dict[str, str] | None = None,
) -> list[UniverseEntry]:
    entries, _ = _build_universe_internal(md, as_of, new_stock_days, listing_dates)
    return entries


def build_universe_with_audit(
    md: MarketData,
    as_of: str | None = None,
    new_stock_days: int = DEFAULT_NEW_STOCK_DAYS,
    listing_dates: dict[str, str] | None = None,
) -> tuple[list[UniverseEntry], list[TradabilityAudit]]:
    return _build_universe_internal(md, as_of, new_stock_days, listing_dates)


def _build_universe_internal(
    md: MarketData,
    as_of: str | None,
    new_stock_days: int,
    listing_dates: dict[str, str] | None,
) -> tuple[list[UniverseEntry], list[TradabilityAudit]]:
    industry_by_symbol = {m.symbol: m.industry_level2 for m in md.industry_map}

    calendar_dates = sorted(
        e.trade_date for e in md.trading_calendar if e.is_open
    )

    universe: list[UniverseEntry] = []
    audit: list[TradabilityAudit] = []

    for s in md.stock_daily:
        excluded, reason = _check_exclusion(
            s, as_of, calendar_dates, new_stock_days, listing_dates
        )
        if excluded:
            audit.append(
                TradabilityAudit(
                    trade_date=s.trade_date,
                    symbol=s.symbol,
                    reason=reason,
                    buy_restricted=_is_buy_restricted(s),
                    sell_deferred=_is_sell_deferred(s),
                )
            )
        else:
            industry = industry_by_symbol.get(s.symbol, "")
            universe.append(
                UniverseEntry(
                    trade_date=s.trade_date,
                    symbol=s.symbol,
                    industry_level2=industry,
                )
            )
            if _is_buy_restricted(s) or _is_sell_deferred(s):
                audit.append(
                    TradabilityAudit(
                        trade_date=s.trade_date,
                        symbol=s.symbol,
                        reason=_tradability_reason(s),
                        buy_restricted=_is_buy_restricted(s),
                        sell_deferred=_is_sell_deferred(s),
                    )
                )

    return universe, audit


def _check_exclusion(
    s: StockDaily,
    as_of: str | None,
    calendar_dates: list[str],
    new_stock_days: int,
    listing_dates: dict[str, str] | None,
) -> tuple[bool, str]:
    if s.is_st:
        return True, f"ST 股票：{s.symbol}"

    if s.is_suspended:
        return True, f"停牌：{s.symbol}"

    if listing_dates and s.symbol in listing_dates and as_of:
        list_date_str = listing_dates[s.symbol]
        days_between = _count_trading_days_between(
            list_date_str, as_of, calendar_dates
        )
        if days_between < new_stock_days:
            return True, (
                f"新股不足 {new_stock_days} 个交易日：{s.symbol}，"
                f"已上市约 {days_between} 个交易日"
            )

    return False, ""


def _count_trading_days_between(
    start: str, end: str, calendar_dates: list[str]
) -> int:
    if calendar_dates:
        return sum(1 for d in calendar_dates if start <= d <= end)
    # 无交易日历时，用日历日近似估算
    from datetime import date

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    calendar_days = (end_date - start_date).days
    return int(calendar_days * APPROX_TRADING_DAYS_PER_YEAR / 365)


def _is_buy_restricted(s: StockDaily) -> bool:
    if s.open is None or s.high is None or s.low is None or s.close is None:
        return False
    if s.limit_up is None:
        return False
    return s.open == s.high == s.low == s.close == s.limit_up


def _is_sell_deferred(s: StockDaily) -> bool:
    if s.open is None or s.high is None or s.low is None or s.close is None:
        return False
    if s.limit_down is None:
        return False
    return s.open == s.high == s.low == s.close == s.limit_down


def _tradability_reason(s: StockDaily) -> str:
    reasons = []
    if _is_buy_restricted(s):
        reasons.append(f"一字涨停无法买入：{s.symbol}")
    if _is_sell_deferred(s):
        reasons.append(f"一字跌停无法卖出：{s.symbol}")
    return "；".join(reasons)
