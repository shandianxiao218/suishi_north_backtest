from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from datetime import timedelta
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen


GetJson = Callable[[str, dict[str, str], dict[str, str], int], dict[str, Any]]


class AStockDataClient(Protocol):
    """a-stock-data 行情客户端的最小协议。"""

    def daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[dict[str, Any]]:
        """读取指定标的的日线行情。"""

    def benchmark_daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[dict[str, Any]]:
        """读取指定指数基准的日线行情。"""


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
        return _daily_bars_to_weekly_bars(symbol, daily_bars)

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


class BaiduKlineClient:
    """百度股市通 K 线客户端。"""

    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"

    def __init__(self, get_json: GetJson | None = None) -> None:
        self.get_json = get_json or _get_json

    def daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[dict[str, Any]]:
        response = self.get_json(
            self.url,
            _baidu_kline_params(symbol, start, is_index=False),
            _baidu_headers(),
            10,
        )
        return _baidu_market_rows(response)

    def benchmark_daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[dict[str, Any]]:
        response = self.get_json(
            self.url,
            _baidu_kline_params(symbol, start, is_index=True),
            _baidu_headers(),
            10,
        )
        return _baidu_market_rows(response)


class AStockDataAdapter:
    """把 a-stock-data 行情结果转换为内部市场数据结构。"""

    def __init__(self, client: AStockDataClient) -> None:
        self.client = client

    def stock_daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[MarketBar]:
        rows = self.client.daily_bars(symbol, start=start, end=end)
        return _filter_bars(
            [_astock_row_to_market_bar(symbol, row) for row in rows],
            start=start,
            end=end,
        )

    def stock_weekly_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[MarketBar]:
        daily_bars = self.stock_daily_bars(symbol, start=start, end=end)
        return _daily_bars_to_weekly_bars(symbol, daily_bars)

    def benchmark_daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[MarketBar]:
        rows = self.client.benchmark_daily_bars(symbol, start=start, end=end)
        return _filter_bars(
            [_astock_row_to_market_bar(symbol, row) for row in rows],
            start=start,
            end=end,
        )


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


def _get_json(
    url: str,
    params: dict[str, str],
    headers: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    request = Request(f"{url}?{urlencode(params)}", headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _baidu_kline_params(
    symbol: str,
    start: date,
    *,
    is_index: bool,
) -> dict[str, str]:
    return {
        "all": "1",
        "isIndex": str(is_index).lower(),
        "isBk": "false",
        "isBlock": "false",
        "isFutures": "false",
        "isStock": str(not is_index).lower(),
        "newFormat": "1",
        "group": "quotation_kline_ab",
        "finClientType": "pc",
        "code": _plain_symbol(symbol),
        "start_time": start.isoformat(),
        "ktype": "1",
    }


def _baidu_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }


def _baidu_market_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    market_data = response.get("Result", {}).get("newMarketData", {})
    keys = market_data.get("keys", [])
    rows = str(market_data.get("marketData", "")).split(";")
    return [
        _baidu_row_to_dict(keys, row)
        for row in rows
        if row.strip()
    ]


def _baidu_row_to_dict(keys: list[str], row: str) -> dict[str, Any]:
    values = row.split(",")
    raw = dict(zip(keys, values))
    return {
        "date": raw["time"],
        "open": float(raw["open"]),
        "close": float(raw["close"]),
        "high": float(raw["high"]),
        "low": float(raw["low"]),
        "volume": int(float(raw["volume"])),
        "amount": float(raw["amount"]),
        "adjust_factor": 1.0,
    }


def _plain_symbol(symbol: str) -> str:
    return symbol.split(".")[0]


def _astock_row_to_market_bar(symbol: str, row: dict[str, Any]) -> MarketBar:
    open_price = _zero_as_missing(_value(row, "open"))
    return MarketBar(
        symbol=symbol,
        date=_parse_date(_value(row, "datetime", "date")),
        open=open_price,
        high=_zero_as_missing(_value(row, "high")),
        low=_zero_as_missing(_value(row, "low")),
        close=float(_value(row, "close")),
        volume=int(float(_value(row, "vol", "volume"))),
        amount=float(_value(row, "amount")),
        adjust_factor=float(row.get("adjust_factor", 1.0) or 1.0),
        is_suspended=open_price is None,
        has_open_price=open_price is not None,
    )


def _value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    raise KeyError(keys[0])


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _zero_as_missing(value: Any) -> float | None:
    if value in {"", None}:
        return None
    number = float(value)
    if number == 0:
        return None
    return number


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


def _daily_bars_to_weekly_bars(
    symbol: str,
    daily_bars: list[MarketBar],
) -> list[MarketBar]:
    weeks: dict[date, list[MarketBar]] = {}
    for bar in daily_bars:
        weeks.setdefault(_week_ending_date(bar.date), []).append(bar)

    return [
        _aggregate_week(symbol, week_end, bars)
        for week_end, bars in sorted(weeks.items())
    ]


def _filter_bars(
    bars: list[MarketBar],
    *,
    start: date,
    end: date,
) -> list[MarketBar]:
    return [bar for bar in bars if start <= bar.date <= end]


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
