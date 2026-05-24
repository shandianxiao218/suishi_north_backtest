from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from suishi_north_backtest.raw_data import (
    RawSnapshotManifest,
    validate_raw_snapshot,
)


# ---- 辅助函数 ----


def write_manifest(
    snapshot_dir: Path,
    data_version: str = "a-stock-data-raw-2026-05-18",
    extra_fields: dict | None = None,
) -> None:
    manifest: dict = {
        "data_version": data_version,
        "source": "a-stock-data",
        "created_at": "2026-05-18T00:00:00+08:00",
        "stock_daily_file": "stock_daily.csv",
        "index_daily_file": "index_daily.csv",
        "industry_map_file": "industry_map.csv",
        "industry_daily_amount_file": "industry_daily_amount.csv",
        "trading_calendar_file": "trading_calendar.csv",
    }
    if extra_fields:
        manifest.update(extra_fields)
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


REQUIRED_CSV_FIELDS: dict[str, list[str]] = {
    "stock_daily.csv": [
        "trade_date",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ],
    "index_daily.csv": [
        "trade_date",
        "index_code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ],
    "industry_map.csv": ["symbol", "industry_level2"],
    "industry_daily_amount.csv": ["trade_date", "industry_level2", "amount"],
    "trading_calendar.csv": ["trade_date", "is_open"],
}


def write_minimal_csv(snapshot_dir: Path, filename: str, fields: list[str]) -> None:
    path = snapshot_dir / filename
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)


def write_valid_snapshot(snapshot_dir: Path) -> None:
    write_manifest(snapshot_dir)
    for filename, fields in REQUIRED_CSV_FIELDS.items():
        write_minimal_csv(snapshot_dir, filename, fields)


# ---- 测试 ----


def test_missing_snapshot_dir_raises(tmp_path: Path) -> None:
    nonexistent = tmp_path / "no-such-snapshot"

    with pytest.raises(FileNotFoundError, match="原始快照目录不存在"):
        validate_raw_snapshot(nonexistent)


def test_missing_manifest_raises(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="manifest.json"):
        validate_raw_snapshot(snapshot_dir)


def test_manifest_missing_data_version_raises(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    manifest = {
        "source": "a-stock-data",
        "created_at": "2026-05-18T00:00:00+08:00",
    }
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="data_version"):
        validate_raw_snapshot(snapshot_dir)


def test_manifest_empty_data_version_raises(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_manifest(snapshot_dir, data_version="")

    with pytest.raises(ValueError, match="data_version"):
        validate_raw_snapshot(snapshot_dir)


def test_missing_required_raw_file_raises(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_manifest(snapshot_dir)
    # 只写部分文件
    write_minimal_csv(
        snapshot_dir, "stock_daily.csv", REQUIRED_CSV_FIELDS["stock_daily.csv"]
    )

    with pytest.raises(FileNotFoundError, match="stock_daily|index_daily|industry"):
        validate_raw_snapshot(snapshot_dir)


def test_csv_missing_required_column_raises(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_manifest(snapshot_dir)

    # stock_daily.csv 缺少 close 列
    bad_fields = [f for f in REQUIRED_CSV_FIELDS["stock_daily.csv"] if f != "close"]
    write_minimal_csv(snapshot_dir, "stock_daily.csv", bad_fields)

    # 其余文件正常
    for filename, fields in REQUIRED_CSV_FIELDS.items():
        if filename != "stock_daily.csv":
            write_minimal_csv(snapshot_dir, filename, fields)

    with pytest.raises(ValueError, match="close"):
        validate_raw_snapshot(snapshot_dir)


def test_chinese_industry_name_reads_correctly(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_manifest(snapshot_dir)

    for filename, fields in REQUIRED_CSV_FIELDS.items():
        if filename != "industry_map.csv":
            write_minimal_csv(snapshot_dir, filename, fields)

    # 写入中文行业名
    path = snapshot_dir / "industry_map.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "industry_level2"])
        writer.writerow(["000001", "银行"])
        writer.writerow(["600519", "白酒"])

    manifest = validate_raw_snapshot(snapshot_dir)
    assert manifest.data_version == "a-stock-data-raw-2026-05-18"


def test_utf8_sig_csv_reads_correctly(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_manifest(snapshot_dir)
    write_valid_snapshot(snapshot_dir)

    manifest = validate_raw_snapshot(snapshot_dir)
    assert manifest.data_version == "a-stock-data-raw-2026-05-18"


def test_plain_utf8_csv_reads_correctly(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    write_manifest(snapshot_dir)

    for filename, fields in REQUIRED_CSV_FIELDS.items():
        path = snapshot_dir / filename
        # 不带 BOM 的 utf-8 也应能读取
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(fields)

    manifest = validate_raw_snapshot(snapshot_dir)
    assert manifest is not None


def test_valid_snapshot_returns_manifest(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    for filename, fields in REQUIRED_CSV_FIELDS.items():
        write_minimal_csv(snapshot_dir, filename, fields)
    write_manifest(snapshot_dir, data_version="a-stock-data-raw-2026-06-01")

    manifest = validate_raw_snapshot(snapshot_dir)
    assert isinstance(manifest, RawSnapshotManifest)
    assert manifest.data_version == "a-stock-data-raw-2026-06-01"
    assert manifest.source == "a-stock-data"


def test_manifest_with_custom_filenames(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    # 使用自定义文件名
    write_manifest(
        snapshot_dir,
        extra_fields={
            "stock_daily_file": "stocks.csv",
            "index_daily_file": "indices.csv",
            "industry_map_file": "ind_map.csv",
            "industry_daily_amount_file": "ind_amount.csv",
            "trading_calendar_file": "calendar.csv",
        },
    )
    for custom_name, fields in [
        ("stocks.csv", REQUIRED_CSV_FIELDS["stock_daily.csv"]),
        ("indices.csv", REQUIRED_CSV_FIELDS["index_daily.csv"]),
        ("ind_map.csv", REQUIRED_CSV_FIELDS["industry_map.csv"]),
        ("ind_amount.csv", REQUIRED_CSV_FIELDS["industry_daily_amount.csv"]),
        ("calendar.csv", REQUIRED_CSV_FIELDS["trading_calendar.csv"]),
    ]:
        write_minimal_csv(snapshot_dir, custom_name, fields)

    manifest = validate_raw_snapshot(snapshot_dir)
    assert manifest.data_version == "a-stock-data-raw-2026-05-18"


def test_manifest_custom_file_missing_raises(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    write_manifest(
        snapshot_dir,
        extra_fields={
            "stock_daily_file": "custom_stocks.csv",
        },
    )
    # 只写了默认文件名，没写自定义文件名
    for filename, fields in REQUIRED_CSV_FIELDS.items():
        write_minimal_csv(snapshot_dir, filename, fields)

    with pytest.raises(FileNotFoundError, match="custom_stocks.csv"):
        validate_raw_snapshot(snapshot_dir)
