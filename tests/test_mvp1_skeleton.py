import csv
import json
from pathlib import Path

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.engine import run_mvp1_backtest


def test_mvp1_backtest_writes_required_outputs(tmp_path: Path) -> None:
    config = BacktestConfig(
        name="mvp1-skeleton-test",
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
    assert metadata["name"] == "mvp1-skeleton-test"
    assert metadata["start_date"] == "2024-01-01"
    assert metadata["end_date"] == "2024-01-05"
    assert metadata["initial_cash"] == 1_000_000


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

    skipped_trades = (tmp_path / "skipped_trades.csv").read_text(
        encoding="utf-8-sig"
    )
    assert "MVP-1 当前为验收骨架" in skipped_trades


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
        headers = set(next(csv.reader(file)))

    for field_name in ["track", "commission", "slippage_cost", "total_cost"]:
        assert field_name in headers
