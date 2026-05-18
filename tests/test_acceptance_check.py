from __future__ import annotations

import csv
from pathlib import Path

from scripts.acceptance_check import (
    AcceptanceReport,
    validate_csv_outputs,
    validate_full_outputs,
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
