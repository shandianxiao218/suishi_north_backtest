from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REQUIRED_SMOKE_OUTPUTS = [
    "equity_curve.csv",
    "trades.csv",
    "skipped_trades.csv",
    "run_metadata.json",
]

FULL_OUTPUT_CATEGORIES = {
    "指标/绩效输出": [
        "metrics.json",
        "performance_metrics.json",
        "summary_metrics.json",
        "performance_summary.json",
    ],
    "候选/信号审计输出": [
        "candidates.csv",
        "signals.csv",
        "candidate_signals.csv",
        "audit_candidates.csv",
    ],
    "持仓/组合状态输出": [
        "holdings.csv",
        "positions.csv",
        "portfolio_positions.csv",
    ],
    "指数基准对比输出": [
        "benchmark_comparison.csv",
        "benchmarks.csv",
        "benchmark_metrics.json",
    ],
    "双轨组合对比输出": [
        "track_comparison.csv",
        "strategy_tracks.csv",
        "track_metrics.json",
    ],
    "参数敏感性输出": [
        "sensitivity.csv",
        "parameter_sensitivity.csv",
        "sensitivity_report.json",
    ],
}

CSV_OUTPUTS = ["equity_curve.csv", "trades.csv", "skipped_trades.csv"]
RESEARCH_LIMITATION_TEXT = "MVP-1 是日线代理研究系统"
PLACEHOLDER_MARKERS = [
    "acceptance-placeholder",
    "验收骨架",
    "占位",
    "暂无真实候选",
    "后续接入",
    "后续数据",
    "后续信号",
    "后续完整数据",
    "由后续",
]
REQUIRED_BENCHMARKS = {"CSI300", "CSI500", "CSI1000"}
REQUIRED_PERIODS = {"sample_in", "sample_out", "recent"}


@dataclass
class AcceptanceReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)

    @property
    def passed(self) -> bool:
        return not self.errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 MVP-1 总体验收检查")
    parser.add_argument(
        "--profile",
        choices=["smoke", "full", "real"],
        default="full",
        help=(
            "smoke 检查最小骨架；full 检查完整输出协议；"
            "real 额外拒绝占位输出并检查真实回测证据。"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/acceptance-mvp1"),
        help="验收输出目录。默认：outputs/acceptance-mvp1",
    )
    parser.add_argument("--skip-pytest", action="store_true", help="跳过 pytest。")
    parser.add_argument(
        "--keep-output",
        action="store_true",
        help="不清理已有输出目录。若 CSV 被 Excel 占用，不建议使用。",
    )
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2024-01-05")
    parser.add_argument("--initial-cash", default="1000000")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    report = AcceptanceReport()

    ensure_repo_shape(repo_root, report)
    if not args.skip_pytest:
        run_pytest(repo_root, report)

    prepare_output_dir(args.output_dir, args.keep_output, report)
    if not report.errors:
        run_cli(repo_root, args, report)

    validate_smoke_outputs(args.output_dir, report)
    validate_metadata(args.output_dir / "run_metadata.json", args, report)
    validate_csv_outputs(args.output_dir, report)

    if args.profile in {"full", "real"}:
        validate_full_outputs(args.output_dir, report)
        validate_audit_headers(args.output_dir, report)

    if args.profile == "real":
        validate_real_outputs(args.output_dir, report)

    print_report(report, args)
    return 0 if report.passed else 1


def ensure_repo_shape(repo_root: Path, report: AcceptanceReport) -> None:
    required_paths = [
        repo_root / "AGENTS.md",
        repo_root / "CONTEXT.md",
        repo_root / "docs" / "adr" / "0002-mvp-1-daily-close-backtest-scope.md",
        repo_root / "pyproject.toml",
        repo_root / "src" / "suishi_north_backtest",
    ]
    for path in required_paths:
        if not path.exists():
            report.fail(f"缺少仓库关键文件或目录：{path}")


def run_pytest(repo_root: Path, report: AcceptanceReport) -> None:
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=repo_root)
    if result.returncode != 0:
        report.fail(
            "pytest 未通过。请先执行 `python -m pip install -e \".[dev]\"`，"
            "然后重新运行验收。"
        )
    else:
        report.note("pytest 通过。")


def prepare_output_dir(output_dir: Path, keep_output: bool, report: AcceptanceReport) -> None:
    if keep_output:
        output_dir.mkdir(parents=True, exist_ok=True)
        return

    if output_dir.exists():
        try:
            shutil.rmtree(output_dir)
        except PermissionError:
            report.fail(
                f"无法清理输出目录 {output_dir}。请关闭 Excel/WPS/预览窗格中"
                "打开的 CSV 文件，或换一个 --output-dir。"
            )
            return
    output_dir.mkdir(parents=True, exist_ok=True)


def run_cli(repo_root: Path, args: argparse.Namespace, report: AcceptanceReport) -> None:
    env = os.environ.copy()
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    command = [
        sys.executable,
        "-m",
        "suishi_north_backtest.cli",
        "--name",
        f"acceptance-{args.profile}",
        "--start-date",
        args.start_date,
        "--end-date",
        args.end_date,
        "--initial-cash",
        str(args.initial_cash),
        "--output-dir",
        str(args.output_dir),
    ]
    result = subprocess.run(command, cwd=repo_root, env=env)
    if result.returncode != 0:
        report.fail("MVP-1 CLI 运行失败。请查看上方 traceback 或错误输出。")
    else:
        report.note("MVP-1 CLI 运行成功。")


def validate_smoke_outputs(output_dir: Path, report: AcceptanceReport) -> None:
    for filename in REQUIRED_SMOKE_OUTPUTS:
        path = output_dir / filename
        if not path.exists():
            report.fail(f"缺少必需输出文件：{path}")
        elif path.stat().st_size == 0:
            report.fail(f"输出文件为空：{path}")


def validate_metadata(path: Path, args: argparse.Namespace, report: AcceptanceReport) -> None:
    if not path.exists():
        return
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        report.fail(f"run_metadata.json 不是合法 JSON：{error}")
        return

    required_fields = [
        "name",
        "start_date",
        "end_date",
        "initial_cash",
        "code_version",
        "research_limitation",
        "outputs",
    ]
    for field_name in required_fields:
        if field_name not in metadata:
            report.fail(f"run_metadata.json 缺少字段：{field_name}")

    if metadata.get("start_date") != args.start_date:
        report.fail("run_metadata.json 的 start_date 与验收参数不一致。")
    if metadata.get("end_date") != args.end_date:
        report.fail("run_metadata.json 的 end_date 与验收参数不一致。")
    if str(metadata.get("initial_cash")) != str(args.initial_cash):
        report.fail("run_metadata.json 的 initial_cash 与验收参数不一致。")

    limitation = str(metadata.get("research_limitation", ""))
    if RESEARCH_LIMITATION_TEXT not in limitation:
        report.fail("run_metadata.json 没有标注 MVP-1 日线代理研究限制。")


def validate_csv_outputs(output_dir: Path, report: AcceptanceReport) -> None:
    for filename in CSV_OUTPUTS:
        path = output_dir / filename
        if not path.exists():
            continue
        content = path.read_bytes()
        if not content.startswith(b"\xef\xbb\xbf"):
            report.fail(f"CSV 未使用 utf-8-sig，Windows/Excel 可能乱码：{path}")
        try:
            rows = list(csv.reader(path.open("r", encoding="utf-8-sig", newline="")))
        except UnicodeDecodeError as error:
            report.fail(f"CSV 无法按 utf-8-sig 读取：{path}，错误：{error}")
            continue
        if not rows:
            report.fail(f"CSV 缺少表头：{path}")


def validate_full_outputs(output_dir: Path, report: AcceptanceReport) -> None:
    for category, candidates in FULL_OUTPUT_CATEGORIES.items():
        if not any((output_dir / filename).exists() for filename in candidates):
            report.fail(
                f"full 验收缺少{category}。接受的文件名之一："
                + ", ".join(candidates)
            )


def validate_audit_headers(output_dir: Path, report: AcceptanceReport) -> None:
    trades_path = output_dir / "trades.csv"
    if trades_path.exists():
        headers = read_csv_headers(trades_path)
        expected_groups = [
            {"entry_date", "entry_price"},
            {"exit_date", "exit_price", "exit_reason"},
            {"commission", "slippage_cost", "total_cost"},
            {"track", "symbol"},
        ]
        for group in expected_groups:
            missing = group.difference(headers)
            if missing:
                report.warn(
                    "trades.csv 审计字段可能不足，缺少：" + ", ".join(sorted(missing))
                )

    skipped_path = output_dir / "skipped_trades.csv"
    if skipped_path.exists():
        headers = read_csv_headers(skipped_path)
        if "reason" not in headers:
            report.fail("skipped_trades.csv 缺少跳过原因字段：reason")


def validate_real_outputs(output_dir: Path, report: AcceptanceReport) -> None:
    validate_no_placeholder_markers(output_dir, report)
    validate_real_metadata(output_dir / "run_metadata.json", report)
    validate_real_signal_audit(output_dir, report)
    validate_real_benchmarks(output_dir, report)
    validate_real_sensitivity(output_dir, report)


def validate_no_placeholder_markers(output_dir: Path, report: AcceptanceReport) -> None:
    for path in output_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".md"}:
            continue
        content = path.read_text(encoding="utf-8-sig" if path.suffix == ".csv" else "utf-8")
        for marker in PLACEHOLDER_MARKERS:
            if marker in content:
                report.fail(f"real 验收不允许占位标记 `{marker}`：{path}")


def validate_real_metadata(path: Path, report: AcceptanceReport) -> None:
    if not path.exists():
        return
    metadata = json.loads(path.read_text(encoding="utf-8"))
    data_version = str(metadata.get("data_version", ""))
    if not data_version:
        report.fail("real 验收要求 run_metadata.json 记录真实 data_version。")
    if data_version == "acceptance-placeholder":
        report.fail("real 验收不允许 data_version=acceptance-placeholder。")

    parameter_set = str(metadata.get("parameter_set", ""))
    if not parameter_set:
        report.fail("real 验收要求 run_metadata.json 记录参数集。")

    universe = str(metadata.get("universe", ""))
    if not universe:
        report.fail("real 验收要求 run_metadata.json 记录股票池。")


def validate_real_signal_audit(output_dir: Path, report: AcceptanceReport) -> None:
    candidates = read_csv_dicts(first_existing(output_dir, ["candidates.csv", "signals.csv"]))
    skipped = read_csv_dicts(output_dir / "skipped_trades.csv")
    trades = read_csv_dicts(output_dir / "trades.csv")

    has_candidate = bool(candidates)
    has_trade = bool(trades)
    has_real_skip = any(row.get("reason") for row in skipped)
    if not (has_candidate or has_trade or has_real_skip):
        report.fail("real 验收要求候选、交易或跳过审计至少有一类真实记录。")


def validate_real_benchmarks(output_dir: Path, report: AcceptanceReport) -> None:
    path = first_existing(output_dir, ["benchmark_comparison.csv", "benchmarks.csv"])
    rows = read_csv_dicts(path)
    benchmarks = {row.get("benchmark", "") for row in rows}
    periods = {row.get("period", "") for row in rows}

    missing_benchmarks = REQUIRED_BENCHMARKS.difference(benchmarks)
    if missing_benchmarks:
        report.fail("real 验收缺少指数基准：" + ", ".join(sorted(missing_benchmarks)))

    missing_periods = REQUIRED_PERIODS.difference(periods)
    if missing_periods:
        report.fail("real 验收缺少样本区间：" + ", ".join(sorted(missing_periods)))


def validate_real_sensitivity(output_dir: Path, report: AcceptanceReport) -> None:
    path = first_existing(output_dir, ["sensitivity.csv", "parameter_sensitivity.csv"])
    rows = read_csv_dicts(path)
    if len(rows) < 2:
        report.fail("real 验收要求 sensitivity 输出至少包含基线和一个参数扰动。")
        return

    parameters = {row.get("parameter", "") for row in rows}
    if parameters == {"baseline"}:
        report.fail("real 验收要求 sensitivity 不只包含 baseline。")


def first_existing(output_dir: Path, filenames: list[str]) -> Path:
    for filename in filenames:
        path = output_dir / filename
        if path.exists():
            return path
    return output_dir / filenames[0]


def read_csv_dicts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_csv_headers(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        return set(next(reader, []))


def print_report(report: AcceptanceReport, args: argparse.Namespace) -> None:
    print("\n=== MVP-1 验收结果 ===")
    print(f"验收模式：{args.profile}")
    print(f"输出目录：{args.output_dir}")

    print("\n[NOTES]")
    for note in report.notes or ["无"]:
        print(f"- {note}")

    print("\n[WARNINGS]")
    for warning in report.warnings or ["无"]:
        print(f"- {warning}")

    print("\n[ERRORS]")
    for error in report.errors or ["无"]:
        print(f"- {error}")

    print("\n结论：" + ("通过" if report.passed else "不通过"))


if __name__ == "__main__":
    raise SystemExit(main())
