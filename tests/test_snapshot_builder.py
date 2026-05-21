from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from suishi_north_backtest.snapshot_builder import (
    REQUIRED_SNAPSHOT_FILES,
    SnapshotManifest,
    build_snapshot_from_output_dir,
)


def test_build_snapshot_from_output_dir_copies_required_files_and_manifest(tmp_path: Path) -> None:
    source_output_dir = create_mvp1_output_dir(tmp_path / "outputs" / "mvp1")
    data_dir = tmp_path / "snapshots"

    snapshot_dir = build_snapshot_from_output_dir(
        source_output_dir=source_output_dir,
        data_dir=data_dir,
        snapshot="snapshot-001",
        manifest=SnapshotManifest(
            data_version="a-stock-data-snapshot-001",
            parameter_set="ADR-0002 defaults",
            universe="沪深 A 股核心股票池",
        ),
    )

    assert snapshot_dir == data_dir / "snapshot-001"
    for filename in [*REQUIRED_SNAPSHOT_FILES, "manifest.json"]:
        assert (snapshot_dir / filename).exists(), filename

    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "data_version": "a-stock-data-snapshot-001",
        "parameter_set": "ADR-0002 defaults",
        "universe": "沪深 A 股核心股票池",
    }


def test_build_snapshot_from_output_dir_rejects_missing_source_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="source output directory"):
        build_snapshot_from_output_dir(
            source_output_dir=tmp_path / "missing",
            data_dir=tmp_path / "snapshots",
            snapshot="snapshot-001",
            manifest=SnapshotManifest("v1", "p", "u"),
        )


def test_build_snapshot_from_output_dir_rejects_missing_required_files(tmp_path: Path) -> None:
    source_output_dir = tmp_path / "outputs" / "mvp1"
    source_output_dir.mkdir(parents=True)
    write_json(source_output_dir / "metrics.json", {"name": "test", "initial_cash": 1000000, "ending_equity": 1000000, "total_return": 0.0, "max_drawdown": 0.0, "trade_count": 0})

    with pytest.raises(FileNotFoundError, match="missing required files"):
        build_snapshot_from_output_dir(
            source_output_dir=source_output_dir,
            data_dir=tmp_path / "snapshots",
            snapshot="snapshot-001",
            manifest=SnapshotManifest("v1", "p", "u"),
        )


def test_build_snapshot_from_output_dir_requires_overwrite(tmp_path: Path) -> None:
    source_output_dir = create_mvp1_output_dir(tmp_path / "outputs" / "mvp1")
    data_dir = tmp_path / "snapshots"
    snapshot_dir = data_dir / "snapshot-001"
    snapshot_dir.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="Use --overwrite"):
        build_snapshot_from_output_dir(
            source_output_dir=source_output_dir,
            data_dir=data_dir,
            snapshot="snapshot-001",
            manifest=SnapshotManifest("v1", "p", "u"),
        )

    rebuilt = build_snapshot_from_output_dir(
        source_output_dir=source_output_dir,
        data_dir=data_dir,
        snapshot="snapshot-001",
        manifest=SnapshotManifest("v1", "p", "u"),
        overwrite=True,
    )

    assert rebuilt == snapshot_dir
    assert (snapshot_dir / "manifest.json").exists()


def create_mvp1_output_dir(path: Path) -> Path:
    path.mkdir(parents=True)
    write_csv(path / "equity_curve.csv", ["date", "cash", "equity", "drawdown", "track"], [])
    write_csv(path / "trades.csv", ["symbol", "track"], [])
    write_csv(path / "skipped_trades.csv", ["reason"], [])
    write_csv(path / "candidates.csv", ["signal_date", "symbol"], [])
    write_csv(path / "holdings.csv", ["date", "symbol"], [])
    write_csv(path / "benchmark_comparison.csv", ["period", "benchmark"], [])
    write_csv(path / "track_comparison.csv", ["metric"], [])
    write_csv(path / "sensitivity.csv", ["parameter"], [])
    write_json(path / "metrics.json", {"trade_count": 0})
    return path


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
