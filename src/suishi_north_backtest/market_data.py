from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from suishi_north_backtest.raw_data import RawSnapshotManifest


@dataclass
class StockDaily:
    trade_date: str
    symbol: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    amount: float | None
    is_st: bool
    limit_up: float | None
    limit_down: float | None
    is_suspended: bool


@dataclass
class IndexDaily:
    trade_date: str
    index_code: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    amount: float | None


@dataclass
class IndustryMap:
    symbol: str
    industry_level2: str


@dataclass
class IndustryDailyAmount:
    trade_date: str
    industry_level2: str
    amount: float


@dataclass
class TradingCalendarEntry:
    trade_date: str
    is_open: bool


@dataclass
class MarketData:
    stock_daily: list[StockDaily]
    index_daily: list[IndexDaily]
    industry_map: list[IndustryMap]
    industry_daily_amount: list[IndustryDailyAmount]
    trading_calendar: list[TradingCalendarEntry]


def load_market_data(
    snapshot_dir: Path, manifest: RawSnapshotManifest
) -> MarketData:
    return MarketData(
        stock_daily=_load_stock_daily(snapshot_dir / manifest.stock_daily_file),
        index_daily=_load_index_daily(snapshot_dir / manifest.index_daily_file),
        industry_map=_load_industry_map(snapshot_dir / manifest.industry_map_file),
        industry_daily_amount=_load_industry_daily_amount(
            snapshot_dir / manifest.industry_daily_amount_file
        ),
        trading_calendar=_load_trading_calendar(
            snapshot_dir / manifest.trading_calendar_file
        ),
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"CSV 无法读取：{path}")


def _to_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value)


def _load_stock_daily(path: Path) -> list[StockDaily]:
    rows = _read_csv_rows(path)
    result = []
    for row in rows:
        has_open = row.get("open", "").strip() != ""
        result.append(
            StockDaily(
                trade_date=row["trade_date"],
                symbol=row["symbol"],
                open=_to_float(row.get("open")),
                high=_to_float(row.get("high")),
                low=_to_float(row.get("low")),
                close=_to_float(row.get("close")),
                volume=_to_float(row.get("volume")),
                amount=_to_float(row.get("amount")),
                is_st=False,
                limit_up=_to_float(row.get("limit_up")),
                limit_down=_to_float(row.get("limit_down")),
                is_suspended=not has_open,
            )
        )
    result.sort(key=lambda s: (s.trade_date, s.symbol))
    return result


def _load_index_daily(path: Path) -> list[IndexDaily]:
    rows = _read_csv_rows(path)
    result = []
    for row in rows:
        result.append(
            IndexDaily(
                trade_date=row["trade_date"],
                index_code=row["index_code"],
                open=_to_float(row.get("open")),
                high=_to_float(row.get("high")),
                low=_to_float(row.get("low")),
                close=_to_float(row.get("close")),
                volume=_to_float(row.get("volume")),
                amount=_to_float(row.get("amount")),
            )
        )
    result.sort(key=lambda i: (i.trade_date, i.index_code))
    return result


def _load_industry_map(path: Path) -> list[IndustryMap]:
    rows = _read_csv_rows(path)
    return [IndustryMap(symbol=r["symbol"], industry_level2=r["industry_level2"]) for r in rows]


def _load_industry_daily_amount(path: Path) -> list[IndustryDailyAmount]:
    rows = _read_csv_rows(path)
    result = []
    for row in rows:
        result.append(
            IndustryDailyAmount(
                trade_date=row["trade_date"],
                industry_level2=row["industry_level2"],
                amount=float(row["amount"]),
            )
        )
    result.sort(key=lambda d: (d.trade_date, d.industry_level2))
    return result


def _load_trading_calendar(path: Path) -> list[TradingCalendarEntry]:
    rows = _read_csv_rows(path)
    result = []
    for row in rows:
        result.append(
            TradingCalendarEntry(
                trade_date=row["trade_date"],
                is_open=row["is_open"].strip() == "1",
            )
        )
    result.sort(key=lambda e: e.trade_date)
    return result
