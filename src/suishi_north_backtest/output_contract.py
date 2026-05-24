"""MVP-1 输出协议集中定义。

集中管理 CSV 文件名、CSV 字段、JSON 必填字段、CSV 编码、
smoke/full/real profile 所需文件和 schema 校验。

所有输出协议相关常量和校验函数只在此处定义，
engine.py / data.py / snapshot_builder.py / acceptance_check.py 引用本模块。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CSV_ENCODING = "utf-8-sig"


@dataclass(frozen=True)
class CsvOutputSpec:
    """单个 CSV 输出文件协议。"""

    filename: str
    required_columns: list[str]


@dataclass(frozen=True)
class JsonOutputSpec:
    """单个 JSON 输出文件协议。"""

    filename: str
    required_fields: list[str]


def mvp1_csv_specs() -> list[CsvOutputSpec]:
    """返回所有 MVP-1 CSV 输出协议。"""
    return [
        CsvOutputSpec(
            filename="equity_curve.csv",
            required_columns=["date", "cash", "equity", "drawdown", "track"],
        ),
        CsvOutputSpec(
            filename="trades.csv",
            required_columns=[
                "trade_id",
                "track",
                "symbol",
                "entry_signal_date",
                "entry_date",
                "entry_price",
                "entry_shares",
                "exit_trigger_date",
                "exit_date",
                "exit_price",
                "exit_reason",
                "commission",
                "stamp_tax",
                "slippage_cost",
                "total_cost",
                "gross_pnl",
                "net_pnl",
                "first_target_achieved",
                "audit_note",
            ],
        ),
        CsvOutputSpec(
            filename="skipped_trades.csv",
            required_columns=["signal_date", "track", "symbol", "reason"],
        ),
        CsvOutputSpec(
            filename="candidates.csv",
            required_columns=[
                "signal_date",
                "track",
                "symbol",
                "industry_level2",
                "is_strong_mainline",
                "a_date",
                "a_price",
                "b_date",
                "b_price",
                "c_date",
                "c_price",
                "ab_gain_pct",
                "bc_retracement_pct",
                "distance_to_c_low_pct",
                "weekly_filter_passed",
                "annual_filter_passed",
                "failure_reason",
                "as_of",
                "signal_rule_version",
                "score",
                "score_breakdown",
                "audit_note",
            ],
        ),
        CsvOutputSpec(
            filename="holdings.csv",
            required_columns=[
                "date",
                "track",
                "symbol",
                "shares",
                "cost_basis",
                "market_value",
                "unrealized_pnl",
                "holding_days",
                "highest_close_since_entry",
                "audit_note",
            ],
        ),
        CsvOutputSpec(
            filename="benchmark_comparison.csv",
            required_columns=[
                "period",
                "benchmark",
                "strategy_return",
                "benchmark_return",
                "excess_return",
                "max_drawdown",
                "annualized_return",
                "volatility",
                "win_rate",
                "trade_count",
                "return_drawdown_ratio",
                "audit_note",
            ],
        ),
        CsvOutputSpec(
            filename="track_comparison.csv",
            required_columns=[
                "metric",
                "pure_structure_track",
                "mainline_filtered_track",
                "delta",
                "audit_note",
            ],
        ),
        CsvOutputSpec(
            filename="sensitivity.csv",
            required_columns=[
                "parameter",
                "baseline_value",
                "variant_value",
                "sample_in_metric",
                "sample_out_metric",
                "overfit_risk",
                "accepted",
                "audit_note",
            ],
        ),
    ]


def mvp1_json_specs() -> list[JsonOutputSpec]:
    """返回所有 MVP-1 JSON 输出协议。"""
    return [
        JsonOutputSpec(
            filename="run_metadata.json",
            required_fields=[
                "name",
                "start_date",
                "end_date",
                "initial_cash",
                "code_version",
                "created_at",
                "data_source",
                "data_version",
                "parameter_set",
                "universe",
                "research_limitation",
                "outputs",
            ],
        ),
        JsonOutputSpec(
            filename="metrics.json",
            required_fields=[
                "name",
                "initial_cash",
                "ending_equity",
                "total_return",
                "max_drawdown",
                "trade_count",
            ],
        ),
    ]


def mvp1_required_files(profile: str) -> list[str]:
    """按验收 profile 返回必需文件列表。"""
    smoke_files = [
        "equity_curve.csv",
        "trades.csv",
        "skipped_trades.csv",
        "run_metadata.json",
    ]
    extra_full_files = [
        "metrics.json",
        "candidates.csv",
        "holdings.csv",
        "benchmark_comparison.csv",
        "track_comparison.csv",
        "sensitivity.csv",
    ]

    if profile == "smoke":
        return smoke_files
    elif profile in {"full", "real"}:
        return smoke_files + extra_full_files
    else:
        raise ValueError(f"未知的验收 profile：{profile}")


def validate_csv_header(
    filename: str,
    header: list[str],
    required: list[str],
) -> list[str]:
    """校验 CSV header 是否包含所有必需列。"""
    header_set = set(header)
    missing = [col for col in required if col not in header_set]
    if missing:
        return [f"{filename} 缺少必需列：" + ", ".join(missing)]
    return []


def validate_json_required_fields(
    filename: str,
    data: dict,
    required: list[str],
) -> list[str]:
    """校验 JSON 对象是否包含所有必需字段。"""
    missing = [field for field in required if field not in data]
    if missing:
        return [f"{filename} 缺少必需字段：" + ", ".join(missing)]
    return []


def validate_output_contract(
    output_dir: Path,
    profile: str = "full",
) -> list[str]:
    """校验输出目录是否符合 MVP-1 输出协议。"""
    errors: list[str] = []

    required_files = mvp1_required_files(profile)
    for filename in required_files:
        path = output_dir / filename
        if not path.exists():
            errors.append(f"缺少必需文件：{filename}")

    csv_specs = {s.filename: s for s in mvp1_csv_specs()}
    for filename in required_files:
        if filename in csv_specs:
            spec = csv_specs[filename]
            path = output_dir / filename
            if path.exists():
                import csv as csv_mod

                with path.open("r", encoding=CSV_ENCODING, newline="") as f:
                    reader = csv_mod.reader(f)
                    header = next(reader, [])
                errors.extend(
                    validate_csv_header(spec.filename, header, spec.required_columns)
                )

    json_specs = {s.filename: s for s in mvp1_json_specs()}
    for filename in required_files:
        if filename in json_specs:
            spec = json_specs[filename]
            path = output_dir / filename
            if path.exists():
                import json as json_mod

                try:
                    data = json_mod.loads(path.read_text(encoding="utf-8"))
                    errors.extend(
                        validate_json_required_fields(
                            spec.filename, data, spec.required_fields
                        )
                    )
                except (json_mod.JSONDecodeError, UnicodeDecodeError):
                    errors.append(f"{spec.filename} 不是合法 JSON")

    return errors
