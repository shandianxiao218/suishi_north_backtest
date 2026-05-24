from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawSnapshotManifest:
    data_version: str
    source: str
    created_at: str
    stock_daily_file: str
    index_daily_file: str
    industry_map_file: str
    industry_daily_amount_file: str
    trading_calendar_file: str


REQUIRED_CSV_COLUMNS: dict[str, list[str]] = {
    "stock_daily": [
        "trade_date",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ],
    "index_daily": [
        "trade_date",
        "index_code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ],
    "industry_map": ["symbol", "industry_level2"],
    "industry_daily_amount": ["trade_date", "industry_level2", "amount"],
    "trading_calendar": ["trade_date", "is_open"],
}

FILE_KEYS = [
    "stock_daily_file",
    "index_daily_file",
    "industry_map_file",
    "industry_daily_amount_file",
    "trading_calendar_file",
]


def validate_raw_snapshot(snapshot_dir: Path) -> RawSnapshotManifest:
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"原始快照目录不存在：{snapshot_dir}")

    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"缺少 manifest.json：{manifest_path}")

    raw_manifest = _load_manifest(manifest_path)
    _validate_manifest_files(snapshot_dir, raw_manifest)
    _validate_csv_columns(snapshot_dir, raw_manifest)

    return raw_manifest


def _load_manifest(path: Path) -> RawSnapshotManifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"manifest.json 不是合法 JSON：{e}") from e

    data_version = data.get("data_version")
    if not data_version:
        raise ValueError("manifest.json 缺少 data_version 或 data_version 为空")

    return RawSnapshotManifest(
        data_version=data_version,
        source=data.get("source", ""),
        created_at=data.get("created_at", ""),
        stock_daily_file=data.get("stock_daily_file", "stock_daily.csv"),
        index_daily_file=data.get("index_daily_file", "index_daily.csv"),
        industry_map_file=data.get("industry_map_file", "industry_map.csv"),
        industry_daily_amount_file=data.get(
            "industry_daily_amount_file", "industry_daily_amount.csv"
        ),
        trading_calendar_file=data.get(
            "trading_calendar_file", "trading_calendar.csv"
        ),
    )


def _validate_manifest_files(
    snapshot_dir: Path, manifest: RawSnapshotManifest
) -> None:
    for key in FILE_KEYS:
        filename = getattr(manifest, key)
        filepath = snapshot_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"缺少必需 raw 文件：{filepath}")


def _validate_csv_columns(
    snapshot_dir: Path, manifest: RawSnapshotManifest
) -> None:
    key_to_attr = {
        "stock_daily": manifest.stock_daily_file,
        "index_daily": manifest.index_daily_file,
        "industry_map": manifest.industry_map_file,
        "industry_daily_amount": manifest.industry_daily_amount_file,
        "trading_calendar": manifest.trading_calendar_file,
    }
    for key, filename in key_to_attr.items():
        filepath = snapshot_dir / filename
        required = REQUIRED_CSV_COLUMNS[key]
        _check_csv_headers(filepath, required)


def _check_csv_headers(filepath: Path, required_columns: list[str]) -> None:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            with filepath.open("r", encoding=encoding, newline="") as f:
                reader = csv.reader(f)
                headers = next(reader, [])
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"CSV 无法读取：{filepath}")

    missing = set(required_columns).difference(headers)
    if missing:
        raise ValueError(
            f"CSV 缺少必需列：{filepath}，缺少：{', '.join(sorted(missing))}"
        )
