from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from datetime import timedelta
from pathlib import Path


@dataclass(frozen=True)
class MarketBar:
    """统一后的市场 K 线。"""

    symbol: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: int
    amount: float
    adjust_factor: float
    is_suspended: bool
    has_open_price: bool


@dataclass(frozen=True)
class DataSnapshot:
    """用于复现实验的数据快照信息。"""

    data_version: str
    source: str
    created_at: str


class CsvMarketDataAdapter:
    """从本地 CSV 快照读取市场数据。"""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)

    def stock_daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[MarketBar]:
        path = self.root_dir / "daily" / f"{symbol}.csv"
        return [
            bar
            for bar in self._read_bars(path, symbol)
            if start <= bar.date <= end
        ]

    def stock_weekly_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[MarketBar]:
        daily_bars = self.stock_daily_bars(symbol, start=start, end=end)
        weeks: dict[date, list[MarketBar]] = {}
        for bar in daily_bars:
            weeks.setdefault(_week_ending_date(bar.date), []).append(bar)

        return [
            _aggregate_week(symbol, week_end, bars)
            for week_end, bars in sorted(weeks.items())
        ]

    def benchmark_daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[MarketBar]:
        path = self.root_dir / "benchmarks" / f"{symbol}.csv"
        return [
            bar
            for bar in self._read_bars(path, symbol)
            if start <= bar.date <= end
        ]

    def snapshot(self) -> DataSnapshot:
        manifest = json.loads(
            (self.root_dir / "manifest.json").read_text(encoding="utf-8")
        )
        return DataSnapshot(
            data_version=manifest["data_version"],
            source=manifest["source"],
            created_at=manifest["created_at"],
        )

    def _read_bars(self, path: Path, symbol: str) -> list[MarketBar]:
        with path.open(newline="", encoding="utf-8-sig") as file:
            return [
                _row_to_market_bar(symbol, row)
                for row in csv.DictReader(file)
            ]


def _row_to_market_bar(symbol: str, row: dict[str, str]) -> MarketBar:
    open_price = _optional_float(row["open"])
    return MarketBar(
        symbol=symbol,
        date=date.fromisoformat(row["date"]),
        open=open_price,
        high=_optional_float(row["high"]),
        low=_optional_float(row["low"]),
        close=float(row["close"]),
        volume=int(float(row["volume"])),
        amount=float(row["amount"]),
        adjust_factor=_adjust_factor(row),
        is_suspended=_parse_bool(row["suspended"]),
        has_open_price=open_price is not None,
    )


def _optional_float(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _adjust_factor(row: dict[str, str]) -> float:
    value = row.get("adjust_factor", "")
    if value == "":
        return 1.0
    return float(value)


def _week_ending_date(day: date) -> date:
    return day + timedelta(days=4 - day.weekday())


def _aggregate_week(symbol: str, week_end: date, bars: list[MarketBar]) -> MarketBar:
    tradable_bars = [bar for bar in bars if bar.open is not None]
    high_values = [bar.high for bar in bars if bar.high is not None]
    low_values = [bar.low for bar in bars if bar.low is not None]
    first_open = tradable_bars[0].open if tradable_bars else None
    return MarketBar(
        symbol=symbol,
        date=week_end,
        open=first_open,
        high=max(high_values) if high_values else None,
        low=min(low_values) if low_values else None,
        close=bars[-1].close,
        volume=sum(bar.volume for bar in bars),
        amount=sum(bar.amount for bar in bars),
        adjust_factor=bars[-1].adjust_factor,
        is_suspended=all(bar.is_suspended for bar in bars),
        has_open_price=first_open is not None,
    )
