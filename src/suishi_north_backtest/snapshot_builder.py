from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from suishi_north_backtest.output_contract import mvp1_csv_specs


def _required_snapshot_files() -> list[str]:
    return [spec.filename for spec in mvp1_csv_specs()] + ["metrics.json"]


REQUIRED_SNAPSHOT_FILES = _required_snapshot_files()


@dataclass(frozen=True)
class SnapshotManifest:
    """a-stock-data 本地快照 manifest。"""

    data_version: str
    parameter_set: str
    universe: str

    def to_dict(self) -> dict[str, str]:
        return {
            "data_version": self.data_version,
            "parameter_set": self.parameter_set,
            "universe": self.universe,
        }


def build_snapshot_from_output_dir(
    source_output_dir: Path,
    data_dir: Path,
    snapshot: str,
    manifest: SnapshotManifest,
    *,
    overwrite: bool = False,
) -> Path:
    """把 MVP-1 输出目录转换为 a-stock-data 本地快照目录。"""

    source_output_dir = Path(source_output_dir)
    data_dir = Path(data_dir)
    snapshot_dir = data_dir / snapshot

    _validate_source_output_dir(source_output_dir)
    _prepare_snapshot_dir(snapshot_dir, overwrite=overwrite)

    for filename in REQUIRED_SNAPSHOT_FILES:
        shutil.copy2(source_output_dir / filename, snapshot_dir / filename)

    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return snapshot_dir


def _validate_source_output_dir(source_output_dir: Path) -> None:
    if not source_output_dir.exists():
        raise FileNotFoundError(f"source output directory does not exist: {source_output_dir}")
    if not source_output_dir.is_dir():
        raise NotADirectoryError(f"source output path is not a directory: {source_output_dir}")

    missing = [
        filename
        for filename in REQUIRED_SNAPSHOT_FILES
        if not (source_output_dir / filename).exists()
    ]
    if missing:
        raise FileNotFoundError(
            "source output directory missing required files: " + ", ".join(missing)
        )


def _prepare_snapshot_dir(snapshot_dir: Path, *, overwrite: bool) -> None:
    if snapshot_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"snapshot directory already exists: {snapshot_dir}. Use --overwrite to replace it."
            )
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 MVP-1 输出目录构建 a-stock-data 本地快照")
    parser.add_argument(
        "--source-output-dir",
        type=Path,
        required=True,
        help="已有 MVP-1 输出目录，例如 outputs/mvp1-skeleton。",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/a_stock_data_snapshots"),
        help="a-stock-data 本地快照根目录。",
    )
    parser.add_argument("--snapshot", required=True, help="快照子目录名称。")
    parser.add_argument(
        "--data-version",
        default=None,
        help="manifest.data_version。默认使用 a-stock-data-<snapshot>。",
    )
    parser.add_argument(
        "--parameter-set",
        default="ADR-0002 defaults",
        help="manifest.parameter_set。",
    )
    parser.add_argument(
        "--universe",
        default="沪深 A 股核心股票池",
        help="manifest.universe。",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="如果快照目录已存在，则删除后重建。",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    manifest = SnapshotManifest(
        data_version=args.data_version or f"a-stock-data-{args.snapshot}",
        parameter_set=args.parameter_set,
        universe=args.universe,
    )
    snapshot_dir = build_snapshot_from_output_dir(
        source_output_dir=args.source_output_dir,
        data_dir=args.data_dir,
        snapshot=args.snapshot,
        manifest=manifest,
        overwrite=args.overwrite,
    )
    print(f"a-stock-data 本地快照已生成：{snapshot_dir}")


if __name__ == "__main__":
    main()
