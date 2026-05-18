import csv
import json
from pathlib import Path

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.engine import run_mvp1_backtest


def test_mvp1_backtest_writes_required_outputs(tmp_path: Path) -> None:
    config = BacktestConfig(
        name="mvp1-fixture-test",
        start_date="2024-01-01",
        end_date="2024-01-05",
        initial_cash=1_000_000,
        output_dir=tmp_path,
    )

    result = run_mvp1_backtest(config)

    assert result.output_dir == tmp_path
    assert (tmp_path / "equity_curve.csv").exists()
    assert (tmp_path / "trades.csv").exists()
    assert (tmp_path / "skipped_trades.csv").exists()
    assert (tmp_path / "run_metadata.json").exists()

    metadata = json.loads((tmp_path / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["name"] == "mvp1-fixture-test"
    assert metadata["start_date"] == "2024-01-01"
    assert metadata["end_date"] == "2024-01-05"
    assert metadata["initial_cash"] == 1_000_000
    assert metadata["data_version"] == "deterministic-fixture-v1-2026-05-18"
    assert metadata["universe"] == "fixture-core-a-share-sample"


def test_mvp1_backtest_records_research_limitation(tmp_path: Path) -> None:
    config = BacktestConfig(output_dir=tmp_path)

    run_mvp1_backtest(config)

    metadata = (tmp_path / "run_metadata.json").read_text(encoding="utf-8")
    assert "日线代理研究系统" in metadata
    assert "不等同于完整实盘交易系统" in metadata


def test_csv_outputs_are_excel_friendly_utf8_sig(tmp_path: Path) -> None:
    config = BacktestConfig(output_dir=tmp_path)

    run_mvp1_backtest(config)

    for filename in ["equity_curve.csv", "trades.csv", "skipped_trades.csv"]:
        content = (tmp_path / filename).read_bytes()
        assert content.startswith(b"\xef\xbb\xbf"), filename


def test_mvp1_backtest_writes_full_acceptance_outputs(tmp_path: Path) -> None:
    config = BacktestConfig(output_dir=tmp_path)

    run_mvp1_backtest(config)

    for filename in [
        "metrics.json",
        "candidates.csv",
        "holdings.csv",
        "benchmark_comparison.csv",
        "track_comparison.csv",
        "sensitivity.csv",
    ]:
        assert (tmp_path / filename).exists(), filename


def test_trade_audit_headers_include_costs_and_track(tmp_path: Path) -> None:
    config = BacktestConfig(output_dir=tmp_path)

    run_mvp1_backtest(config)

    with (tmp_path / "trades.csv").open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        headers = set(reader.fieldnames or [])
        rows = list(reader)

    for field_name in ["track", "commission", "slippage_cost", "total_cost"]:
        assert field_name in headers
    assert rows
    assert rows[0]["symbol"] == "000001.SZ"
    assert rows[0]["track"] == "mainline_filtered"


def test_fixture_outputs_include_real_acceptance_evidence(tmp_path: Path) -> None:
    config = BacktestConfig(output_dir=tmp_path)

    run_mvp1_backtest(config)

    with (tmp_path / "candidates.csv").open("r", encoding="utf-8-sig", newline="") as file:
        candidates = list(csv.DictReader(file))
    with (tmp_path / "benchmark_comparison.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        benchmarks = list(csv.DictReader(file))
    with (tmp_path / "sensitivity.csv").open("r", encoding="utf-8-sig", newline="") as file:
        sensitivity = list(csv.DictReader(file))

    assert candidates
    assert {row["benchmark"] for row in benchmarks} == {"CSI300", "CSI500", "CSI1000"}
    assert {row["period"] for row in benchmarks} == {"sample_in", "sample_out", "recent"}
    assert len(sensitivity) >= 2
    assert {row["parameter"] for row in sensitivity} >= {"baseline", "ab_min_gain"}
