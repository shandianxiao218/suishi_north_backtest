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
DEFAULT_MIN_AMOUNT = 0.0
DEFAULT_LONG_SUSPENSION_DAYS = 0


def build_universe(
    md: MarketData,
    as_of: str | None = None,
    new_stock_days: int = DEFAULT_NEW_STOCK_DAYS,
    listing_dates: dict[str, str] | None = None,
    min_amount: float = DEFAULT_MIN_AMOUNT,
    long_suspension_days: int = DEFAULT_LONG_SUSPENSION_DAYS,
) -> list[UniverseEntry]:
    entries, _ = _build_universe_internal(md, as_of, new_stock_days, listing_dates, min_amount, long_suspension_days)
    return entries


def build_universe_with_audit(
    md: MarketData,
    as_of: str | None = None,
    new_stock_days: int = DEFAULT_NEW_STOCK_DAYS,
    listing_dates: dict[str, str] | None = None,
    min_amount: float = DEFAULT_MIN_AMOUNT,
    long_suspension_days: int = DEFAULT_LONG_SUSPENSION_DAYS,
) -> tuple[list[UniverseEntry], list[TradabilityAudit]]:
    return _build_universe_internal(md, as_of, new_stock_days, listing_dates, min_amount, long_suspension_days)


def _build_universe_internal(
    md: MarketData,
    as_of: str | None,
    new_stock_days: int,
    listing_dates: dict[str, str] | None,
    min_amount: float,
    long_suspension_days: int,
) -> tuple[list[UniverseEntry], list[TradabilityAudit]]:
    industry_by_symbol = {m.symbol: m.industry_level2 for m in md.industry_map}

    calendar_dates = sorted(
        e.trade_date for e in md.trading_calendar if e.is_open
    )

    long_suspended = _compute_long_suspended(md, long_suspension_days, as_of)

    universe: list[UniverseEntry] = []
    audit: list[TradabilityAudit] = []

    for s in md.stock_daily:
        # 长期停牌优先于单日停牌检查
        excluded = False
        reason = ""
        if long_suspension_days > 0 and s.symbol in long_suspended:
            excluded = True
            reason = f"长期停牌（连续 {long_suspended[s.symbol]} 个交易日）：{s.symbol}"
        if not excluded:
            excluded, reason = _check_exclusion(
                s, as_of, calendar_dates, new_stock_days, listing_dates, min_amount,
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
    min_amount: float,
) -> tuple[bool, str]:
    if _is_beijing_exchange(s.symbol, s.market):
        return True, f"北交所股票：{s.symbol}"

    if s.is_st or _is_st_from_name(s.stock_name):
        return True, f"ST 股票：{s.symbol}"

    if s.is_delisting or _is_delisting_from_name(s.stock_name):
        return True, f"退市股票：{s.symbol}"

    if s.is_suspended:
        # 单日停牌：如果有长期停牌检查，会被外层覆盖
        return True, f"停牌：{s.symbol}"

    if min_amount > 0 and s.amount is not None and s.amount < min_amount:
        return True, f"低流动性（成交额 {s.amount:.0f} < {min_amount:.0f}）：{s.symbol}"

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


def _is_beijing_exchange(symbol: str, market: str = "") -> bool:
    """判断是否为北交所或新三板股票。

    优先使用 market 字段判定，其次用代码前缀推断。
    """
    if market:
        return market.upper() in ("BJ", "BSE", "北交所", "新三板")
    return symbol.startswith("8") or symbol.startswith("4")


def _is_st_from_name(stock_name: str) -> bool:
    return stock_name.startswith("ST") or stock_name.startswith("*ST")


def _is_delisting_from_name(stock_name: str) -> bool:
    return "退" in stock_name


def _compute_long_suspended(
    md: MarketData,
    long_suspension_days: int,
    as_of: str | None,
) -> dict[str, int]:
    """计算截至 as_of 连续停牌天数超过阈值的股票。

    Returns:
        symbol -> 连续停牌天数 的映射（仅包含超过阈值的）。
    """
    if long_suspension_days <= 0:
        return {}

    # 按日期排序，按 symbol 分组
    by_symbol: dict[str, list[StockDaily]] = {}
    for s in md.stock_daily:
        by_symbol.setdefault(s.symbol, []).append(s)

    result: dict[str, int] = {}
    for symbol, bars in by_symbol.items():
        bars = sorted(bars, key=lambda b: b.trade_date)
        if as_of:
            bars = [b for b in bars if b.trade_date <= as_of]

        # 从末尾往前数连续停牌天数
        consecutive = 0
        for b in reversed(bars):
            if b.is_suspended:
                consecutive += 1
            else:
                break

        if consecutive >= long_suspension_days:
            result[symbol] = consecutive

    return result


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
