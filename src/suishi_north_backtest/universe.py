from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from suishi_north_backtest.data import MarketBar
from suishi_north_backtest.market_data import MarketData, StockDaily


CORE_BOARDS = {"main", "chinext", "star"}


@dataclass(frozen=True)
class StockInfo:
    """股票基础信息，保留给早期股票池 API 使用。"""

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
        visible_bars = _visible_market_bars(bars_by_symbol.get(stock.symbol, []), as_of)
        reasons = _legacy_exclude_reasons(stock, visible_bars, rules)
        if reasons:
            excluded_reasons[stock.symbol] = reasons
        else:
            included.append(stock)

    return StockPoolSelection(
        included=included,
        excluded_reasons=excluded_reasons,
    )


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

    long_suspended_from = _compute_long_suspended_from(md, long_suspension_days)

    universe: list[UniverseEntry] = []
    audit: list[TradabilityAudit] = []

    for s in md.stock_daily:
        # 长期停牌：只从连续停牌达到阈值的日期起排除，不回溯历史
        excluded = False
        reason = ""
        if (
            long_suspension_days > 0
            and s.symbol in long_suspended_from
            and s.trade_date >= long_suspended_from[s.symbol]
        ):
            excluded = True
            reason = f"长期停牌：{s.symbol}"
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


def _legacy_exclude_reasons(
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
    if recent_bars and _average_market_amount(recent_bars) < rules.min_recent_average_amount:
        threshold = int(rules.min_recent_average_amount)
        reasons.append(
            f"最近 {rules.recent_liquidity_days} 日平均成交额低于 {threshold}"
        )
    return reasons


def _visible_market_bars(bars: list[MarketBar], as_of: date) -> list[MarketBar]:
    return sorted(
        [bar for bar in bars if bar.date <= as_of],
        key=lambda bar: bar.date,
    )


def _average_market_amount(bars: list[MarketBar]) -> float:
    return sum(bar.amount for bar in bars) / len(bars)


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


def _compute_long_suspended_from(
    md: MarketData,
    long_suspension_days: int,
) -> dict[str, str]:
    """计算每个 symbol 从哪个日期开始长期停牌。

    按日期正序扫描，找出连续停牌天数首次达到阈值的日期。
    只有从该日期起的 bar 才被排除，不回溯历史正常交易日。

    Returns:
        symbol -> 长期停牌起始日期 的映射。
    """
    if long_suspension_days <= 0:
        return {}

    by_symbol: dict[str, list[StockDaily]] = {}
    for s in md.stock_daily:
        by_symbol.setdefault(s.symbol, []).append(s)

    result: dict[str, str] = {}
    for symbol, bars in by_symbol.items():
        bars = sorted(bars, key=lambda b: b.trade_date)

        # 找连续停牌段，记录每个段的起始日期和长度
        consecutive = 0
        seg_start: str | None = None
        for b in bars:
            if b.is_suspended:
                if consecutive == 0:
                    seg_start = b.trade_date
                consecutive += 1
                if consecutive >= long_suspension_days and symbol not in result:
                    result[symbol] = b.trade_date
            else:
                consecutive = 0
                seg_start = None

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
