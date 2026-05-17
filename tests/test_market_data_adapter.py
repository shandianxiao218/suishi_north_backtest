from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from suishi_north_backtest.data import (
    AStockDataAdapter,
    BaiduKlineClient,
    CsvMarketDataAdapter,
    DataSnapshot,
    MarketBar,
)


class FakeAStockDataClient:
    def __init__(
        self,
        rows: list[dict[str, object]] | None = None,
        benchmark_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.rows = rows or []
        self.benchmark_rows = benchmark_rows or []
        self.calls: list[dict[str, object]] = []

    def daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[dict[str, object]]:
        self.calls.append({"symbol": symbol, "start": start, "end": end})
        return self.rows

    def benchmark_daily_bars(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {"benchmark": symbol, "start": start, "end": end}
        )
        return self.benchmark_rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_baidu_kline_client_parses_stock_daily_rows() -> None:
    calls: list[dict[str, object]] = []

    def fake_get_json(
        url: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return {
            "Result": {
                "newMarketData": {
                    "keys": [
                        "time",
                        "open",
                        "close",
                        "high",
                        "low",
                        "volume",
                        "amount",
                    ],
                    "marketData": "2024-01-02,10.00,10.50,10.80,9.90,1200000,12600000",
                }
            }
        }

    client = BaiduKlineClient(get_json=fake_get_json)

    rows = client.daily_bars(
        "000001.SZ",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
    )

    assert calls[0]["params"] == {
        "all": "1",
        "isIndex": "false",
        "isBk": "false",
        "isBlock": "false",
        "isFutures": "false",
        "isStock": "true",
        "newFormat": "1",
        "group": "quotation_kline_ab",
        "finClientType": "pc",
        "code": "000001",
        "start_time": "2024-01-01",
        "ktype": "1",
    }
    assert rows == [
        {
            "date": "2024-01-02",
            "open": 10.00,
            "close": 10.50,
            "high": 10.80,
            "low": 9.90,
            "volume": 1_200_000,
            "amount": 12_600_000,
            "adjust_factor": 1.0,
        }
    ]


def test_baidu_kline_client_requests_benchmark_as_index() -> None:
    calls: list[dict[str, object]] = []

    def fake_get_json(
        url: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        calls.append({"params": params})
        return {
            "Result": {
                "newMarketData": {
                    "keys": [
                        "time",
                        "open",
                        "close",
                        "high",
                        "low",
                        "volume",
                        "amount",
                    ],
                    "marketData": (
                        "2024-01-02,3400,3410,3420,3380,"
                        "210000000,320000000000"
                    ),
                }
            }
        }

    client = BaiduKlineClient(get_json=fake_get_json)

    rows = client.benchmark_daily_bars(
        "000300",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
    )

    assert calls[0]["params"] == {
        "all": "1",
        "isIndex": "true",
        "isBk": "false",
        "isBlock": "false",
        "isFutures": "false",
        "isStock": "false",
        "newFormat": "1",
        "group": "quotation_kline_ab",
        "finClientType": "pc",
        "code": "000300",
        "start_time": "2024-01-01",
        "ktype": "1",
    }
    assert rows[0]["close"] == 3410.0


def test_astock_adapter_reads_stock_daily_bars_as_internal_market_bars() -> None:
    client = FakeAStockDataClient(
        [
            {
                "datetime": "2024-01-02",
                "open": 10.00,
                "high": 10.80,
                "low": 9.90,
                "close": 10.50,
                "vol": 1_200_000,
                "amount": 12_600_000,
                "adjust_factor": 1.10,
            },
            {
                "datetime": "2024-01-03",
                "open": 0,
                "high": 0,
                "low": 0,
                "close": 10.50,
                "vol": 0,
                "amount": 0,
                "adjust_factor": 1.10,
            },
        ]
    )

    adapter = AStockDataAdapter(client)

    bars = adapter.stock_daily_bars(
        "000001.SZ",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
    )

    assert client.calls == [
        {
            "symbol": "000001.SZ",
            "start": date(2024, 1, 1),
            "end": date(2024, 1, 31),
        }
    ]
    assert bars == [
        MarketBar(
            symbol="000001.SZ",
            date=date(2024, 1, 2),
            open=10.00,
            high=10.80,
            low=9.90,
            close=10.50,
            volume=1_200_000,
            amount=12_600_000,
            adjust_factor=1.10,
            is_suspended=False,
            has_open_price=True,
        ),
        MarketBar(
            symbol="000001.SZ",
            date=date(2024, 1, 3),
            open=None,
            high=None,
            low=None,
            close=10.50,
            volume=0,
            amount=0,
            adjust_factor=1.10,
            is_suspended=True,
            has_open_price=False,
        ),
    ]


def test_astock_adapter_filters_rows_to_requested_date_range() -> None:
    client = FakeAStockDataClient(
        [
            {
                "datetime": "2024-01-02",
                "open": 10.00,
                "high": 10.80,
                "low": 9.90,
                "close": 10.50,
                "vol": 1_200_000,
                "amount": 12_600_000,
            },
            {
                "datetime": "2024-02-01",
                "open": 12.00,
                "high": 12.80,
                "low": 11.90,
                "close": 12.50,
                "vol": 1_300_000,
                "amount": 16_250_000,
            },
        ]
    )
    adapter = AStockDataAdapter(client)

    bars = adapter.stock_daily_bars(
        "000001.SZ",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
    )

    assert [bar.date for bar in bars] == [date(2024, 1, 2)]


def test_astock_adapter_reads_benchmark_daily_bars() -> None:
    client = FakeAStockDataClient(
        benchmark_rows=[
            {
                "date": "2024-01-02",
                "open": 3400.00,
                "high": 3420.00,
                "low": 3380.00,
                "close": 3410.00,
                "volume": 210_000_000,
                "amount": 320_000_000_000,
            },
        ]
    )
    adapter = AStockDataAdapter(client)

    bars = adapter.benchmark_daily_bars(
        "000300",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
    )

    assert client.calls == [
        {
            "benchmark": "000300",
            "start": date(2024, 1, 1),
            "end": date(2024, 1, 31),
        }
    ]
    assert bars == [
        MarketBar(
            symbol="000300",
            date=date(2024, 1, 2),
            open=3400.00,
            high=3420.00,
            low=3380.00,
            close=3410.00,
            volume=210_000_000,
            amount=320_000_000_000,
            adjust_factor=1.00,
            is_suspended=False,
            has_open_price=True,
        )
    ]


def test_astock_adapter_builds_stock_weekly_bars_from_daily_bars() -> None:
    client = FakeAStockDataClient(
        [
            {
                "datetime": "2024-01-02",
                "open": 10.00,
                "high": 10.80,
                "low": 9.90,
                "close": 10.50,
                "vol": 1_200_000,
                "amount": 12_600_000,
                "adjust_factor": 1.10,
            },
            {
                "datetime": "2024-01-03",
                "open": 10.60,
                "high": 11.20,
                "low": 10.30,
                "close": 11.00,
                "vol": 1_500_000,
                "amount": 16_200_000,
                "adjust_factor": 1.11,
            },
            {
                "datetime": "2024-01-08",
                "open": 11.10,
                "high": 11.30,
                "low": 10.70,
                "close": 10.90,
                "vol": 900_000,
                "amount": 9_900_000,
                "adjust_factor": 1.12,
            },
        ]
    )
    adapter = AStockDataAdapter(client)

    bars = adapter.stock_weekly_bars(
        "000001.SZ",
        start=date(2024, 1, 1),
        end=date(2024, 1, 12),
    )

    assert bars == [
        MarketBar(
            symbol="000001.SZ",
            date=date(2024, 1, 5),
            open=10.00,
            high=11.20,
            low=9.90,
            close=11.00,
            volume=2_700_000,
            amount=28_800_000,
            adjust_factor=1.11,
            is_suspended=False,
            has_open_price=True,
        ),
        MarketBar(
            symbol="000001.SZ",
            date=date(2024, 1, 12),
            open=11.10,
            high=11.30,
            low=10.70,
            close=10.90,
            volume=900_000,
            amount=9_900_000,
            adjust_factor=1.12,
            is_suspended=False,
            has_open_price=True,
        ),
    ]


def test_csv_adapter_reads_stock_daily_bars_as_internal_market_bars(
    tmp_path: Path,
) -> None:
    write_csv(
        tmp_path / "daily" / "000001.SZ.csv",
        [
            {
                "date": "2024-01-02",
                "open": "10.00",
                "high": "10.80",
                "low": "9.90",
                "close": "10.50",
                "volume": "1200000",
                "amount": "12600000",
                "adjust_factor": "1.10",
                "suspended": "false",
            },
            {
                "date": "2024-01-03",
                "open": "",
                "high": "",
                "low": "",
                "close": "10.50",
                "volume": "0",
                "amount": "0",
                "adjust_factor": "1.10",
                "suspended": "true",
            },
        ],
    )

    adapter = CsvMarketDataAdapter(tmp_path)

    bars = adapter.stock_daily_bars(
        "000001.SZ",
        start=date(2024, 1, 1),
        end=date(2024, 1, 3),
    )

    assert bars == [
        MarketBar(
            symbol="000001.SZ",
            date=date(2024, 1, 2),
            open=10.00,
            high=10.80,
            low=9.90,
            close=10.50,
            volume=1_200_000,
            amount=12_600_000,
            adjust_factor=1.10,
            is_suspended=False,
            has_open_price=True,
        ),
        MarketBar(
            symbol="000001.SZ",
            date=date(2024, 1, 3),
            open=None,
            high=None,
            low=None,
            close=10.50,
            volume=0,
            amount=0,
            adjust_factor=1.10,
            is_suspended=True,
            has_open_price=False,
        ),
    ]


def test_csv_adapter_builds_stock_weekly_bars_from_daily_bars(
    tmp_path: Path,
) -> None:
    write_csv(
        tmp_path / "daily" / "000001.SZ.csv",
        [
            {
                "date": "2024-01-02",
                "open": "10.00",
                "high": "10.80",
                "low": "9.90",
                "close": "10.50",
                "volume": "1200000",
                "amount": "12600000",
                "adjust_factor": "1.10",
                "suspended": "false",
            },
            {
                "date": "2024-01-03",
                "open": "10.60",
                "high": "11.20",
                "low": "10.30",
                "close": "11.00",
                "volume": "1500000",
                "amount": "16200000",
                "adjust_factor": "1.11",
                "suspended": "false",
            },
            {
                "date": "2024-01-08",
                "open": "11.10",
                "high": "11.30",
                "low": "10.70",
                "close": "10.90",
                "volume": "900000",
                "amount": "9900000",
                "adjust_factor": "1.12",
                "suspended": "false",
            },
        ],
    )

    adapter = CsvMarketDataAdapter(tmp_path)

    bars = adapter.stock_weekly_bars(
        "000001.SZ",
        start=date(2024, 1, 1),
        end=date(2024, 1, 12),
    )

    assert bars == [
        MarketBar(
            symbol="000001.SZ",
            date=date(2024, 1, 5),
            open=10.00,
            high=11.20,
            low=9.90,
            close=11.00,
            volume=2_700_000,
            amount=28_800_000,
            adjust_factor=1.11,
            is_suspended=False,
            has_open_price=True,
        ),
        MarketBar(
            symbol="000001.SZ",
            date=date(2024, 1, 12),
            open=11.10,
            high=11.30,
            low=10.70,
            close=10.90,
            volume=900_000,
            amount=9_900_000,
            adjust_factor=1.12,
            is_suspended=False,
            has_open_price=True,
        ),
    ]


def test_csv_adapter_keeps_all_suspended_week_visible_in_weekly_bars(
    tmp_path: Path,
) -> None:
    write_csv(
        tmp_path / "daily" / "000001.SZ.csv",
        [
            {
                "date": "2024-01-02",
                "open": "",
                "high": "",
                "low": "",
                "close": "10.50",
                "volume": "0",
                "amount": "0",
                "adjust_factor": "1.10",
                "suspended": "true",
            },
            {
                "date": "2024-01-03",
                "open": "",
                "high": "",
                "low": "",
                "close": "10.50",
                "volume": "0",
                "amount": "0",
                "adjust_factor": "1.10",
                "suspended": "true",
            },
        ],
    )

    adapter = CsvMarketDataAdapter(tmp_path)

    bars = adapter.stock_weekly_bars(
        "000001.SZ",
        start=date(2024, 1, 1),
        end=date(2024, 1, 5),
    )

    assert bars == [
        MarketBar(
            symbol="000001.SZ",
            date=date(2024, 1, 5),
            open=None,
            high=None,
            low=None,
            close=10.50,
            volume=0,
            amount=0,
            adjust_factor=1.10,
            is_suspended=True,
            has_open_price=False,
        )
    ]


def test_csv_adapter_reads_benchmark_daily_bars(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "benchmarks" / "CSI300.csv",
        [
            {
                "date": "2024-01-02",
                "open": "3400.00",
                "high": "3420.00",
                "low": "3380.00",
                "close": "3410.00",
                "volume": "210000000",
                "amount": "320000000000",
                "suspended": "false",
            },
        ],
    )

    adapter = CsvMarketDataAdapter(tmp_path)

    bars = adapter.benchmark_daily_bars(
        "CSI300",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
    )

    assert bars == [
        MarketBar(
            symbol="CSI300",
            date=date(2024, 1, 2),
            open=3400.00,
            high=3420.00,
            low=3380.00,
            close=3410.00,
            volume=210_000_000,
            amount=320_000_000_000,
            adjust_factor=1.00,
            is_suspended=False,
            has_open_price=True,
        )
    ]


def test_csv_adapter_reads_data_snapshot_manifest(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "data_version": "fixture-2024-01",
                "source": "local-fixture",
                "created_at": "2024-01-31T15:00:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    adapter = CsvMarketDataAdapter(tmp_path)

    assert adapter.snapshot() == DataSnapshot(
        data_version="fixture-2024-01",
        source="local-fixture",
        created_at="2024-01-31T15:00:00+08:00",
    )
