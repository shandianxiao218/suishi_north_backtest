from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.acceptance_check import (
    AcceptanceReport,
    validate_csv_outputs,
    validate_full_outputs,
    validate_real_outputs,
)


def test_acceptance_report_passed_reflects_errors() -> None:
    report = AcceptanceReport()

    assert report.passed

    report.fail("失败原因")

    assert not report.passed


def test_validate_full_outputs_reports_missing_categories(tmp_path: Path) -> None:
    report = AcceptanceReport()

    validate_full_outputs(tmp_path, report)

    assert not report.passed
    assert any("指标/绩效输出" in error for error in report.errors)
    assert any("参数敏感性输出" in error for error in report.errors)


def test_validate_csv_outputs_accepts_utf8_sig_csv_files(tmp_path: Path) -> None:
    for filename in ["equity_curve.csv", "trades.csv", "skipped_trades.csv"]:
        with (tmp_path / filename).open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["reason"])
            writer.writerow(["中文内容"])

    report = AcceptanceReport()

    validate_csv_outputs(tmp_path, report)

    assert report.passed


def test_validate_csv_outputs_rejects_plain_utf8_csv(tmp_path: Path) -> None:
    for filename in ["equity_curve.csv", "trades.csv", "skipped_trades.csv"]:
        (tmp_path / filename).write_text("reason\n中文内容\n", encoding="utf-8")

    report = AcceptanceReport()

    validate_csv_outputs(tmp_path, report)

    assert not report.passed
    assert len(report.errors) == 3
    assert all("utf-8-sig" in error for error in report.errors)


def test_real_acceptance_rejects_placeholder_outputs(tmp_path: Path) -> None:
    write_json(
        tmp_path / "run_metadata.json",
        {
            "data_version": "acceptance-placeholder",
            "parameter_set": "ADR-0002 defaults",
            "universe": "沪深 A 股核心股票池占位",
        },
    )
    write_csv(tmp_path / "candidates.csv", ["symbol", "audit_note"], [])
    write_csv(tmp_path / "trades.csv", ["symbol"], [])
    write_csv(tmp_path / "skipped_trades.csv", ["reason"], [{"reason": "暂无真实候选"}])
    write_csv(
        tmp_path / "benchmark_comparison.csv",
        ["period", "benchmark"],
        [{"period": "sample_in", "benchmark": "CSI300"}],
    )
    write_csv(
        tmp_path / "sensitivity.csv",
        ["parameter"],
        [{"parameter": "baseline"}],
    )

    report = AcceptanceReport()

    validate_real_outputs(tmp_path, report)

    assert not report.passed
    assert any("acceptance-placeholder" in error for error in report.errors)
    assert any("占位" in error or "暂无真实候选" in error for error in report.errors)


def test_real_acceptance_requires_sensitivity_variants(tmp_path: Path) -> None:
    write_minimal_real_outputs(tmp_path)
    write_csv(
        tmp_path / "sensitivity.csv",
        ["parameter"],
        [{"parameter": "baseline"}],
    )

    report = AcceptanceReport()

    validate_real_outputs(tmp_path, report)

    assert not report.passed
    assert any("至少包含基线和一个参数扰动" in error for error in report.errors)


def test_real_acceptance_passes_for_non_placeholder_evidence(tmp_path: Path) -> None:
    write_minimal_real_outputs(tmp_path)

    report = AcceptanceReport()

    validate_real_outputs(tmp_path, report)

    assert report.passed


def write_minimal_real_outputs(tmp_path: Path) -> None:
    write_json(
        tmp_path / "run_metadata.json",
        {
            "data_version": "baidu-kline-fixture-2026-05-18",
            "parameter_set": "ADR-0002 defaults",
            "universe": "沪深 A 股核心股票池",
        },
    )
    write_csv(
        tmp_path / "candidates.csv",
        ["signal_date", "symbol", "audit_note"],
        [{"signal_date": "2024-01-02", "symbol": "000001", "audit_note": "fixture"}],
    )
    write_csv(tmp_path / "trades.csv", ["symbol"], [])
    write_csv(tmp_path / "skipped_trades.csv", ["reason"], [])
    write_csv(
        tmp_path / "benchmark_comparison.csv",
        ["period", "benchmark"],
        [
            {"period": "sample_in", "benchmark": "CSI300"},
            {"period": "sample_in", "benchmark": "CSI500"},
            {"period": "sample_in", "benchmark": "CSI1000"},
            {"period": "sample_out", "benchmark": "CSI300"},
            {"period": "recent", "benchmark": "CSI300"},
        ],
    )
    write_csv(
        tmp_path / "sensitivity.csv",
        ["parameter"],
        [{"parameter": "baseline"}, {"parameter": "ab_min_gain"}],
    )


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
