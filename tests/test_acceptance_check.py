from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from unittest.mock import patch

from scripts.acceptance_check import (
    AcceptanceReport,
    parse_args,
    run_cli,
    validate_csv_outputs,
    validate_full_outputs,
    validate_metadata,
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
    assert any("metrics.json" in error for error in report.errors)
    assert any("sensitivity.csv" in error for error in report.errors)


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


# ---- 阶段 M：数据源参数测试 ----


def test_parse_args_default_data_source_is_fixture(monkeypatch: object) -> None:
    monkeypatch.setattr(sys, "argv", ["acceptance_check.py", "--profile", "real"])
    args = parse_args()

    assert args.data_source == "fixture"
    assert args.data_snapshot is None
    assert args.data_dir == Path("data/a_stock_data_snapshots")


def test_parse_args_accepts_data_source_a_stock_data(monkeypatch: object) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "acceptance_check.py",
            "--profile",
            "real",
            "--data-source",
            "a-stock-data",
        ],
    )
    args = parse_args()

    assert args.data_source == "a-stock-data"


def test_parse_args_accepts_data_snapshot(monkeypatch: object) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "acceptance_check.py",
            "--profile",
            "real",
            "--data-snapshot",
            "snapshot-2026-05-18",
        ],
    )
    args = parse_args()

    assert args.data_snapshot == "snapshot-2026-05-18"


def test_parse_args_accepts_data_dir(monkeypatch: object) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "acceptance_check.py",
            "--profile",
            "real",
            "--data-dir",
            "custom/data/dir",
        ],
    )
    args = parse_args()

    assert args.data_dir == Path("custom/data/dir")


def test_run_cli_passes_data_source_to_subprocess(
    monkeypatch: object, tmp_path: Path
) -> None:
    captured_command: list[str] = []

    def mock_run(command: list[str], **kwargs: object) -> object:
        captured_command.extend(command)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.acceptance_check.subprocess.run", mock_run)
    monkeypatch.setattr(sys, "argv", ["acceptance_check.py", "--profile", "real"])
    args = parse_args()
    args.output_dir = tmp_path
    report = AcceptanceReport()

    run_cli(Path.cwd(), args, report)

    assert "--data-source" in captured_command
    idx = captured_command.index("--data-source")
    assert captured_command[idx + 1] == "fixture"
    assert report.passed


def test_run_cli_passes_a_stock_data_params_to_subprocess(
    monkeypatch: object, tmp_path: Path
) -> None:
    captured_command: list[str] = []

    def mock_run(command: list[str], **kwargs: object) -> object:
        captured_command.extend(command)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.acceptance_check.subprocess.run", mock_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "acceptance_check.py",
            "--profile",
            "real",
            "--data-source",
            "a-stock-data",
            "--data-snapshot",
            "snapshot-2026-05-18",
            "--data-dir",
            "data/a_stock_data_snapshots",
        ],
    )
    args = parse_args()
    args.output_dir = tmp_path
    report = AcceptanceReport()

    run_cli(Path.cwd(), args, report)

    assert "--data-source" in captured_command
    idx = captured_command.index("--data-source")
    assert captured_command[idx + 1] == "a-stock-data"

    assert "--data-snapshot" in captured_command
    idx = captured_command.index("--data-snapshot")
    assert captured_command[idx + 1] == "snapshot-2026-05-18"

    assert "--data-dir" in captured_command
    idx = captured_command.index("--data-dir")
    assert captured_command[idx + 1] == str(Path("data/a_stock_data_snapshots"))


def test_run_cli_does_not_pass_snapshot_when_none(
    monkeypatch: object, tmp_path: Path
) -> None:
    captured_command: list[str] = []

    def mock_run(command: list[str], **kwargs: object) -> object:
        captured_command.extend(command)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.acceptance_check.subprocess.run", mock_run)
    monkeypatch.setattr(sys, "argv", ["acceptance_check.py", "--profile", "real"])
    args = parse_args()
    args.output_dir = tmp_path
    report = AcceptanceReport()

    run_cli(Path.cwd(), args, report)

    assert "--data-snapshot" not in captured_command


def test_run_cli_missing_snapshot_reports_cli_failure(
    monkeypatch: object, tmp_path: Path
) -> None:
    def mock_run(command: list[str], **kwargs: object) -> object:
        return type("Result", (), {"returncode": 1})()

    monkeypatch.setattr("scripts.acceptance_check.subprocess.run", mock_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "acceptance_check.py",
            "--profile",
            "real",
            "--data-source",
            "a-stock-data",
            "--data-snapshot",
            "nonexistent-snapshot",
        ],
    )
    args = parse_args()
    args.output_dir = tmp_path
    report = AcceptanceReport()

    run_cli(Path.cwd(), args, report)

    assert not report.passed
    assert any("CLI 运行失败" in error for error in report.errors)


# ---- data_source metadata 校验测试 ----


def test_validate_metadata_checks_data_source_consistency(monkeypatch: object, tmp_path: Path) -> None:
    """run_metadata.json 的 data_source 必须与验收请求参数一致。"""
    metadata = {
        "name": "test",
        "start_date": "2024-01-01",
        "end_date": "2024-01-05",
        "initial_cash": 1000000,
        "code_version": "0.1.0",
        "research_limitation": "MVP-1 是日线代理研究系统",
        "outputs": [],
        "data_source": "fixture",
        "data_version": "test-v1",
        "parameter_set": "ADR-0002 defaults",
        "universe": "沪深 A 股核心股票池",
    }
    metadata_path = tmp_path / "run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    # data_source 一致时通过
    monkeypatch.setattr(sys, "argv", ["acceptance_check.py", "--profile", "real"])
    args = parse_args()
    report = AcceptanceReport()
    validate_metadata(metadata_path, args, report)
    assert report.passed


def test_validate_metadata_fails_on_data_source_mismatch(monkeypatch: object, tmp_path: Path) -> None:
    """data_source 不一致时报错。"""
    metadata = {
        "name": "test",
        "start_date": "2024-01-01",
        "end_date": "2024-01-05",
        "initial_cash": 1000000,
        "code_version": "0.1.0",
        "research_limitation": "MVP-1 是日线代理研究系统",
        "outputs": [],
        "data_source": "a-stock-data",
        "data_version": "test-v1",
        "parameter_set": "ADR-0002 defaults",
        "universe": "沪深 A 股核心股票池",
    }
    metadata_path = tmp_path / "run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["acceptance_check.py", "--profile", "real"])
    args = parse_args()  # default data_source = fixture
    report = AcceptanceReport()
    validate_metadata(metadata_path, args, report)

    assert not report.passed
    assert any("data_source" in error and "不一致" in error for error in report.errors)


def test_validate_metadata_requires_new_fields(monkeypatch: object, tmp_path: Path) -> None:
    """run_metadata.json 必须包含 data_source, data_version, parameter_set, universe。"""
    metadata = {
        "name": "test",
        "start_date": "2024-01-01",
        "end_date": "2024-01-05",
        "initial_cash": 1000000,
        "code_version": "0.1.0",
        "research_limitation": "MVP-1 是日线代理研究系统",
        "outputs": [],
    }
    metadata_path = tmp_path / "run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["acceptance_check.py", "--profile", "real"])
    args = parse_args()
    report = AcceptanceReport()
    validate_metadata(metadata_path, args, report)

    assert not report.passed
    assert any("data_source" in error for error in report.errors)
    assert any("data_version" in error for error in report.errors)
    assert any("parameter_set" in error for error in report.errors)
    assert any("universe" in error for error in report.errors)
