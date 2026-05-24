"""测试 output_contract.py 输出协议模块。

验收 Issue #30 要求的核心功能：
- output_contract 覆盖所有 MVP-1 输出
- engine 输出字段与 contract 一致
- AStockDataProvider 校验 CSV header
- mvp1_required_files 按 profile 返回正确文件列表
- validate_output_contract 能报告缺失列
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from suishi_north_backtest.output_contract import (
    CSV_ENCODING,
    CsvOutputSpec,
    JsonOutputSpec,
    mvp1_csv_specs,
    mvp1_json_specs,
    mvp1_required_files,
    validate_csv_header,
    validate_json_required_fields,
    validate_output_contract,
)


class TestOutputContractCoversAllMvp1Outputs:
    """output_contract 必须覆盖所有 MVP-1 输出文件。"""

    def test_csv_specs_cover_all_mvp1_csv_files(self):
        specs = mvp1_csv_specs()
        expected_csv_files = {
            "equity_curve.csv",
            "trades.csv",
            "skipped_trades.csv",
            "candidates.csv",
            "holdings.csv",
            "benchmark_comparison.csv",
            "track_comparison.csv",
            "sensitivity.csv",
        }
        actual_files = {spec.filename for spec in specs}
        assert actual_files == expected_csv_files

    def test_json_specs_cover_all_mvp1_json_files(self):
        specs = mvp1_json_specs()
        expected_json_files = {"run_metadata.json", "metrics.json"}
        actual_files = {spec.filename for spec in specs}
        assert actual_files == expected_json_files

    def test_csv_specs_have_non_empty_required_columns(self):
        for spec in mvp1_csv_specs():
            assert spec.required_columns, f"{spec.filename} 缺少 required_columns"
            assert isinstance(spec.required_columns, list)

    def test_json_specs_have_non_empty_required_fields(self):
        for spec in mvp1_json_specs():
            assert spec.required_fields, f"{spec.filename} 缺少 required_fields"
            assert isinstance(spec.required_fields, list)

    def test_csv_encoding_is_utf8sig(self):
        assert CSV_ENCODING == "utf-8-sig"


class TestEngineOutputsMatchOutputContract:
    """engine.py 写入的 CSV header 必须与 output_contract 一致。"""

    def test_equity_curve_columns_match(self):
        specs = {s.filename: s for s in mvp1_csv_specs()}
        spec = specs["equity_curve.csv"]
        expected = ["date", "cash", "equity", "drawdown", "track"]
        assert spec.required_columns == expected

    def test_trades_columns_match(self):
        specs = {s.filename: s for s in mvp1_csv_specs()}
        spec = specs["trades.csv"]
        assert "trade_id" in spec.required_columns
        assert "entry_date" in spec.required_columns
        assert "exit_date" in spec.required_columns
        assert "exit_reason" in spec.required_columns
        assert "commission" in spec.required_columns
        assert "total_cost" in spec.required_columns
        assert "net_pnl" in spec.required_columns
        assert "audit_note" in spec.required_columns

    def test_skipped_trades_columns_match(self):
        specs = {s.filename: s for s in mvp1_csv_specs()}
        spec = specs["skipped_trades.csv"]
        expected = ["signal_date", "track", "symbol", "reason"]
        assert spec.required_columns == expected

    def test_candidates_columns_match(self):
        specs = {s.filename: s for s in mvp1_csv_specs()}
        spec = specs["candidates.csv"]
        assert "signal_date" in spec.required_columns
        assert "symbol" in spec.required_columns
        assert "failure_reason" in spec.required_columns
        assert "as_of" in spec.required_columns
        assert "signal_rule_version" in spec.required_columns
        assert "score" in spec.required_columns
        assert "score_breakdown" in spec.required_columns
        assert "audit_note" in spec.required_columns

    def test_holdings_columns_match(self):
        specs = {s.filename: s for s in mvp1_csv_specs()}
        spec = specs["holdings.csv"]
        assert "date" in spec.required_columns
        assert "symbol" in spec.required_columns
        assert "shares" in spec.required_columns
        assert "audit_note" in spec.required_columns

    def test_benchmark_comparison_columns_match(self):
        specs = {s.filename: s for s in mvp1_csv_specs()}
        spec = specs["benchmark_comparison.csv"]
        assert "period" in spec.required_columns
        assert "benchmark" in spec.required_columns
        assert "strategy_return" in spec.required_columns

    def test_track_comparison_columns_match(self):
        specs = {s.filename: s for s in mvp1_csv_specs()}
        spec = specs["track_comparison.csv"]
        assert "metric" in spec.required_columns
        assert "pure_structure_track" in spec.required_columns
        assert "mainline_filtered_track" in spec.required_columns

    def test_sensitivity_columns_match(self):
        specs = {s.filename: s for s in mvp1_csv_specs()}
        spec = specs["sensitivity.csv"]
        assert "parameter" in spec.required_columns
        assert "overfit_risk" in spec.required_columns

    def test_run_metadata_required_fields_match(self):
        specs = {s.filename: s for s in mvp1_json_specs()}
        spec = specs["run_metadata.json"]
        for field in [
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
        ]:
            assert field in spec.required_fields, (
                f"run_metadata.json 缺少必填字段：{field}"
            )

    def test_metrics_required_fields_match(self):
        specs = {s.filename: s for s in mvp1_json_specs()}
        spec = specs["metrics.json"]
        for field in [
            "name",
            "initial_cash",
            "ending_equity",
            "total_return",
            "max_drawdown",
            "trade_count",
        ]:
            assert field in spec.required_fields, (
                f"metrics.json 缺少必填字段：{field}"
            )


class TestAStockDataProviderRejectsSnapshotWithMissingRequiredColumns:
    """AStockDataProvider 应校验 CSV header 是否包含必需列。"""

    def test_rejects_csv_with_missing_columns(self, tmp_path):
        from suishi_north_backtest.data import AStockDataProvider
        from suishi_north_backtest.config import BacktestConfig

        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()

        # 写入合法 manifest
        manifest = {
            "data_version": "test-v1",
            "parameter_set": "test-params",
            "universe": "test-universe",
        }
        (snapshot_dir / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        # 写入缺少必需列的 trades.csv
        bad_trades = snapshot_dir / "trades.csv"
        bad_trades.write_text(
            "trade_id,track\nFTR-001,portfolio\n",
            encoding="utf-8-sig",
        )

        # 写入其他合法文件
        for spec in mvp1_csv_specs():
            if spec.filename == "trades.csv":
                continue
            path = snapshot_dir / spec.filename
            if not path.exists():
                header = ",".join(spec.required_columns)
                path.write_text(header + "\n", encoding="utf-8-sig")

        metrics = {"name": "test", "initial_cash": 1000000, "ending_equity": 1034200.0, "total_return": 0.0342, "max_drawdown": 0.0125, "trade_count": 1}
        (snapshot_dir / "metrics.json").write_text(
            json.dumps(metrics), encoding="utf-8"
        )

        config = BacktestConfig(
            data_source="a-stock-data",
            data_snapshot="snap",
            data_dir=str(tmp_path),
            output_dir=str(tmp_path / "out"),
        )
        provider = AStockDataProvider()
        with pytest.raises(ValueError, match="trades.csv.*缺少必需列"):
            provider.load(config)

    def test_accepts_valid_snapshot(self, tmp_path):
        from suishi_north_backtest.data import AStockDataProvider
        from suishi_north_backtest.config import BacktestConfig

        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()

        manifest = {
            "data_version": "test-v1",
            "parameter_set": "test-params",
            "universe": "test-universe",
        }
        (snapshot_dir / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        for spec in mvp1_csv_specs():
            path = snapshot_dir / spec.filename
            header = ",".join(spec.required_columns)
            path.write_text(header + "\n", encoding="utf-8-sig")

        metrics = {"name": "test", "initial_cash": 1000000, "ending_equity": 1034200.0, "total_return": 0.0342, "max_drawdown": 0.0125, "trade_count": 1}
        (snapshot_dir / "metrics.json").write_text(
            json.dumps(metrics), encoding="utf-8"
        )

        config = BacktestConfig(
            data_source="a-stock-data",
            data_snapshot="snap",
            data_dir=str(tmp_path),
            output_dir=str(tmp_path / "out"),
        )
        provider = AStockDataProvider()
        data_set = provider.load(config)
        assert data_set.data_version == "test-v1"


class TestMvp1RequiredFilesByProfile:
    """mvp1_required_files 应按 profile 返回正确的文件列表。"""

    def test_smoke_profile_returns_minimal_files(self):
        files = mvp1_required_files("smoke")
        assert "equity_curve.csv" in files
        assert "trades.csv" in files
        assert "skipped_trades.csv" in files
        assert "run_metadata.json" in files
        # smoke 不应包含 full 才有的文件
        assert "sensitivity.csv" not in files
        assert "candidates.csv" not in files

    def test_full_profile_includes_smoke_plus_extras(self):
        smoke_files = set(mvp1_required_files("smoke"))
        full_files = set(mvp1_required_files("full"))
        assert smoke_files.issubset(full_files)
        assert "metrics.json" in full_files
        assert "candidates.csv" in full_files
        assert "holdings.csv" in full_files
        assert "benchmark_comparison.csv" in full_files
        assert "track_comparison.csv" in full_files
        assert "sensitivity.csv" in full_files

    def test_real_profile_equals_full(self):
        full_files = set(mvp1_required_files("full"))
        real_files = set(mvp1_required_files("real"))
        assert full_files == real_files

    def test_unknown_profile_raises(self):
        with pytest.raises(ValueError, match="未知的验收 profile"):
            mvp1_required_files("unknown")


class TestValidateOutputContractReportsMissingColumns:
    """validate_output_contract 应能报告目录中缺失的列。"""

    def test_reports_missing_csv_columns(self, tmp_path):
        # 写一个缺列的 equity_curve.csv
        bad_csv = tmp_path / "equity_curve.csv"
        bad_csv.write_text("date,cash\n2024-01-01,1000000\n", encoding="utf-8-sig")

        errors = validate_output_contract(tmp_path)
        missing_msgs = [e for e in errors if "equity_curve.csv" in e and "缺少必需列" in e]
        assert missing_msgs, "应报告 equity_curve.csv 缺少必需列"

    def test_reports_missing_required_files(self, tmp_path):
        errors = validate_output_contract(tmp_path, profile="smoke")
        file_missing = [e for e in errors if "缺少必需文件" in e]
        assert file_missing, "应报告缺少必需文件"

    def test_passes_on_valid_directory(self, tmp_path):
        # 构建完整的 valid 目录
        for spec in mvp1_csv_specs():
            path = tmp_path / spec.filename
            header = ",".join(spec.required_columns)
            path.write_text(header + "\n", encoding="utf-8-sig")

        for spec in mvp1_json_specs():
            path = tmp_path / spec.filename
            data = {field: "test" for field in spec.required_fields}
            if spec.filename == "metrics.json":
                data["initial_cash"] = 1000000
                data["total_return"] = 0.0
                data["max_drawdown"] = 0.0
            path.write_text(json.dumps(data), encoding="utf-8")

        errors = validate_output_contract(tmp_path, profile="full")
        assert not errors, f"完整目录不应有错误，但得到：{errors}"

    def test_reports_missing_json_fields(self, tmp_path):
        bad_json = tmp_path / "run_metadata.json"
        bad_json.write_text(json.dumps({"name": "test"}), encoding="utf-8")

        # 也补上 smoke 必需的 CSV
        for spec in mvp1_csv_specs():
            path = tmp_path / spec.filename
            if not path.exists():
                header = ",".join(spec.required_columns)
                path.write_text(header + "\n", encoding="utf-8-sig")

        # 补全 metrics.json
        metrics = {"name": "test", "initial_cash": 1000000, "ending_equity": 1034200.0, "total_return": 0.0342, "max_drawdown": 0.0125, "trade_count": 1}
        (tmp_path / "metrics.json").write_text(
            json.dumps(metrics), encoding="utf-8"
        )

        errors = validate_output_contract(tmp_path, profile="full")
        field_missing = [e for e in errors if "run_metadata.json" in e and "缺少必需字段" in e]
        assert field_missing, "应报告 run_metadata.json 缺少必需字段"


class TestValidateCsvHeader:
    """validate_csv_header 单元测试。"""

    def test_valid_header_passes(self):
        errors = validate_csv_header(
            filename="equity_curve.csv",
            header=["date", "cash", "equity", "drawdown", "track"],
            required=["date", "cash", "equity", "drawdown", "track"],
        )
        assert not errors

    def test_missing_columns_reported(self):
        errors = validate_csv_header(
            filename="equity_curve.csv",
            header=["date", "cash"],
            required=["date", "cash", "equity", "drawdown", "track"],
        )
        assert len(errors) == 1
        assert "equity" in errors[0]
        assert "drawdown" in errors[0]
        assert "track" in errors[0]

    def test_extra_columns_ok(self):
        errors = validate_csv_header(
            filename="trades.csv",
            header=["trade_id", "track", "extra_col"],
            required=["trade_id", "track"],
        )
        assert not errors


class TestValidateJsonRequiredFields:
    """validate_json_required_fields 单元测试。"""

    def test_valid_fields_pass(self):
        errors = validate_json_required_fields(
            filename="run_metadata.json",
            data={"name": "test", "start_date": "2024-01-01"},
            required=["name", "start_date"],
        )
        assert not errors

    def test_missing_fields_reported(self):
        errors = validate_json_required_fields(
            filename="run_metadata.json",
            data={"name": "test"},
            required=["name", "start_date", "end_date"],
        )
        assert len(errors) == 1
        assert "start_date" in errors[0]
        assert "end_date" in errors[0]


class TestMetricsRequiredFieldsIncludeEndingEquityAndTradeCount:
    """metrics.json 必须要求 ending_equity 和 trade_count。"""

    def test_ending_equity_in_required_fields(self):
        specs = {s.filename: s for s in mvp1_json_specs()}
        spec = specs["metrics.json"]
        assert "ending_equity" in spec.required_fields

    def test_trade_count_in_required_fields(self):
        specs = {s.filename: s for s in mvp1_json_specs()}
        spec = specs["metrics.json"]
        assert "trade_count" in spec.required_fields


class TestRunMetadataRequiredFieldsIncludeCreatedAt:
    """run_metadata.json 必须要求 created_at。"""

    def test_created_at_in_required_fields(self):
        specs = {s.filename: s for s in mvp1_json_specs()}
        spec = specs["run_metadata.json"]
        assert "created_at" in spec.required_fields
