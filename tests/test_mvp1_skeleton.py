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

    metadata = (tmp_path / "run_metadata.json").read_text(encoding="utf-8")
    assert "mvp1-skeleton-test" in metadata
    assert "2024-01-01" in metadata
    assert "2024-01-05" in metadata
    assert "1000000" in metadata


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
    assert "MVP-1 骨架阶段暂无真实候选" in skipped_trades
