from __future__ import annotations

import argparse
from pathlib import Path

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.engine import run_mvp1_backtest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行随势向北 MVP-1 回测")
    parser.add_argument("--name", default="mvp1-skeleton")
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2024-01-05")
    parser.add_argument("--initial-cash", type=int, default=1_000_000)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/mvp1-skeleton"))
    parser.add_argument(
        "--data-source",
        choices=["fixture", "a-stock-data"],
        default="fixture",
        help="数据源。fixture 用于确定性验收；a-stock-data 为后续真实数据接入边界。",
    )
    parser.add_argument(
        "--data-snapshot",
        default=None,
        help="数据快照版本。fixture 下可覆盖默认 data_version。",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = BacktestConfig(
        name=args.name,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_cash=args.initial_cash,
        output_dir=args.output_dir,
        data_source=args.data_source,
        data_snapshot=args.data_snapshot,
    )
    result = run_mvp1_backtest(config)
    print(f"MVP-1 回测已运行，输出目录：{result.output_dir}")


if __name__ == "__main__":
    main()
