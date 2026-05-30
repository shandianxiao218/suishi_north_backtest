from __future__ import annotations

import argparse
from pathlib import Path

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.engine import run_mvp1_backtest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行随势向北 MVP-1 回测")
    subparsers = parser.add_subparsers(dest="command")

    # ── run 子命令（默认行为，保持向后兼容）──
    run_parser = subparsers.add_parser("run", help="运行 MVP-1 回测")
    run_parser.add_argument("--name", default="mvp1-skeleton")
    run_parser.add_argument("--start-date", default="2024-01-01")
    run_parser.add_argument("--end-date", default="2024-01-05")
    run_parser.add_argument("--initial-cash", type=int, default=1_000_000)
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/mvp1-skeleton"),
    )
    run_parser.add_argument(
        "--data-source",
        choices=["fixture", "a-stock-data"],
        default="fixture",
        help="数据源。fixture 用于确定性验收；a-stock-data 读取本地快照目录。",
    )
    run_parser.add_argument(
        "--data-snapshot",
        default=None,
        help="数据快照版本。a-stock-data 下对应 data_dir 内的子目录名。",
    )
    run_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/a_stock_data_snapshots"),
        help="a-stock-data 本地快照根目录。",
    )

    # ── audit 子命令 ─────────────────────────────────
    audit_parser = subparsers.add_parser("audit", help="人工抽样审计工具")
    _add_common_data_args(audit_parser)
    audit_parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="抽样数量（默认 10，不足则全部抽样）。",
    )
    audit_parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子（默认 42），保证确定性。",
    )
    audit_parser.add_argument(
        "--audit-output-dir",
        type=Path,
        default=Path("outputs/audit"),
        help="审计输出目录。",
    )

    return parser


def _add_common_data_args(parser: argparse.ArgumentParser) -> None:
    """为子命令添加数据源相关参数。"""
    parser.add_argument(
        "--data-source",
        choices=["fixture", "a-stock-data"],
        default="fixture",
        help="数据源。fixture 用于确定性验收；a-stock-data 读取本地快照目录。",
    )
    parser.add_argument(
        "--data-snapshot",
        default=None,
        help="数据快照版本。",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/a_stock_data_snapshots"),
        help="a-stock-data 本地快照根目录。",
    )


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "audit":
        _run_audit(args)
    else:
        # 默认行为：运行回测（无子命令或 "run"）
        _run_backtest(args)


def _run_backtest(args: argparse.Namespace) -> None:
    config = BacktestConfig(
        name=getattr(args, "name", "mvp1-skeleton"),
        start_date=getattr(args, "start_date", "2024-01-01"),
        end_date=getattr(args, "end_date", "2024-01-05"),
        initial_cash=getattr(args, "initial_cash", 1_000_000),
        output_dir=getattr(args, "output_dir", Path("outputs/mvp1-skeleton")),
        data_source=getattr(args, "data_source", "fixture"),
        data_snapshot=getattr(args, "data_snapshot", None),
        data_dir=getattr(args, "data_dir", Path("data/a_stock_data_snapshots")),
    )
    result = run_mvp1_backtest(config)
    print(f"MVP-1 回测已运行，输出目录：{result.output_dir}")


def _run_audit(args: argparse.Namespace) -> None:
    from suishi_north_backtest.audit import run_audit, write_audit_csv, write_audit_md
    from suishi_north_backtest.data import build_data_provider

    config = BacktestConfig(
        data_source=args.data_source,
        data_snapshot=args.data_snapshot,
        data_dir=args.data_dir,
    )
    provider = build_data_provider(config.data_source)
    data_set = provider.load(config)

    samples = run_audit(
        data_set.trades,
        data_set.candidates,
        sample_size=args.sample_size,
        seed=args.seed,
    )

    output_dir = args.audit_output_dir
    csv_path = write_audit_csv(samples, output_dir)
    md_path = write_audit_md(samples, output_dir)
    print(f"审计完成：{len(samples)} 个样本")
    print(f"  CSV: {csv_path}")
    print(f"  MD:  {md_path}")


if __name__ == "__main__":
    main()
