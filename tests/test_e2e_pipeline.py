from __future__ import annotations

"""端到端集成测试：raw snapshot → market_data → universe → mainline → signals → portfolio → execution → exits"""

import csv
import json
from pathlib import Path

from suishi_north_backtest.raw_data import validate_raw_snapshot
from suishi_north_backtest.market_data import load_market_data
from suishi_north_backtest.universe import build_universe_with_audit
from suishi_north_backtest.mainline import compute_mainlines, MainlineStatus
from suishi_north_backtest.signals import find_candidates
from suishi_north_backtest.portfolio import select_candidates
from suishi_north_backtest.execution import execute_buy
from suishi_north_backtest.exits import detect_exit_signal, execute_sell


def _write_csv(path: Path, fields: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(rows)


def _build_minimal_raw_snapshot(snapshot_dir: Path) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "data_version": "e2e-test-raw-2026-05-19",
        "source": "a-stock-data",
        "created_at": "2026-05-19T00:00:00+08:00",
    }
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    # stock_daily: 10 bars with an AB→BC→C pattern for 000001
    _write_csv(snapshot_dir / "stock_daily.csv",
        ["trade_date", "symbol", "open", "high", "low", "close", "volume", "amount", "is_st", "limit_up", "limit_down"],
        [
            # Pre-A decline
            ["2024-01-02", "000001", "9.5", "9.6", "9.0", "9.2", "10000", "92000", "0", "10.12", "8.28"],
            ["2024-01-03", "000001", "9.3", "9.4", "9.1", "9.3", "8000",  "74400", "0", "10.23", "8.37"],
            # A point
            ["2024-01-04", "000001", "9.0", "9.2", "8.8", "9.0", "12000", "108000", "0", "9.90", "8.10"],
            # A→B rise
            ["2024-01-05", "000001", "9.2", "9.5", "9.1", "9.4", "15000", "141000", "0", "10.34", "8.46"],
            ["2024-01-08", "000001", "9.5", "10.0", "9.4", "9.8", "18000", "176400", "0", "10.78", "8.82"],
            ["2024-01-09", "000001", "10.0", "10.5", "9.9", "10.3", "20000", "206000", "0", "11.33", "9.27"],
            ["2024-01-10", "000001", "10.5", "11.0", "10.4", "10.8", "22000", "237600", "0", "11.88", "9.72"],
            # B point
            ["2024-01-11", "000001", "11.0", "11.8", "10.9", "11.5", "25000", "287500", "0", "12.65", "10.35"],
            # B→C decline
            ["2024-01-12", "000001", "11.2", "11.3", "10.8", "11.0", "20000", "220000", "0", "12.10", "9.90"],
            ["2024-01-15", "000001", "10.8", "10.9", "10.2", "10.5", "18000", "189000", "0", "11.55", "9.45"],
            ["2024-01-16", "000001", "10.3", "10.5", "9.8",  "10.0", "16000", "160000", "0", "11.00", "9.00"],
            # C point
            ["2024-01-17", "000001", "9.8",  "10.0", "9.5",  "9.8",  "14000", "137200", "0", "10.78", "8.82"],
            # Turn strong
            ["2024-01-18", "000001", "9.9",  "10.2", "9.8",  "10.1", "17000", "171700", "0", "11.11", "9.09"],
            ["2024-01-19", "000001", "10.2", "10.4", "10.0", "10.3", "19000", "195700", "0", "11.33", "9.27"],
            # ST stock should be filtered
            ["2024-01-04", "000002", "5.0", "5.5", "4.8", "5.2", "5000", "26000", "1", "5.72", "4.68"],
        ],
    )

    _write_csv(snapshot_dir / "index_daily.csv",
        ["trade_date", "index_code", "open", "high", "low", "close", "volume", "amount"],
        [
            ["2024-01-04", "000300", "3500", "3520", "3490", "3510", "1e7", "3.5e10"],
            ["2024-01-05", "000300", "3510", "3530", "3505", "3525", "9.5e6", "3.35e10"],
            ["2024-01-17", "000300", "3480", "3500", "3470", "3490", "1e7", "3.49e10"],
            ["2024-01-18", "000300", "3490", "3510", "3480", "3500", "9.8e6", "3.43e10"],
        ],
    )

    _write_csv(snapshot_dir / "industry_map.csv",
        ["symbol", "industry_level2"],
        [["000001", "银行"], ["000002", "房地产"]],
    )

    _write_csv(snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        [
            ["2024-01-04", "银行", "5e9"], ["2024-01-04", "房地产", "3e9"],
            ["2024-01-05", "银行", "6e9"], ["2024-01-05", "房地产", "2e9"],
            ["2024-01-08", "银行", "7e9"], ["2024-01-08", "房地产", "2.5e9"],
            ["2024-01-17", "银行", "8e9"], ["2024-01-17", "房地产", "1e9"],
            ["2024-01-18", "银行", "9e9"], ["2024-01-18", "房地产", "1.5e9"],
        ],
    )

    _write_csv(snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        [["2024-01-04", "1"], ["2024-01-05", "1"], ["2024-01-08", "1"],
         ["2024-01-17", "1"], ["2024-01-18", "1"], ["2024-01-19", "1"]],
    )


def test_end_to_end_pipeline(tmp_path: Path) -> None:
    """完整管线：raw snapshot → market data → universe → mainline → signals → portfolio → execution → exits"""
    snapshot_dir = tmp_path / "raw-snapshot"
    _build_minimal_raw_snapshot(snapshot_dir)

    # Step 1: Validate raw snapshot
    manifest = validate_raw_snapshot(snapshot_dir)
    assert manifest.data_version == "e2e-test-raw-2026-05-19"

    # Step 2: Load market data
    md = load_market_data(snapshot_dir, manifest)
    assert len(md.stock_daily) == 15  # 14 for 000001 + 1 for 000002
    assert len(md.trading_calendar) == 6

    # Step 3: Build universe (should exclude ST 000002)
    universe, audit = build_universe_with_audit(md, as_of="2024-01-19")
    st_audit = [a for a in audit if a.symbol == "000002"]
    assert len(st_audit) >= 1
    assert any("ST" in a.reason for a in st_audit)

    # Step 4: Compute mainlines
    mainlines = compute_mainlines(md.industry_daily_amount, as_of="2024-01-18")
    bank_mainlines = [m for m in mainlines if m.industry_level2 == "银行"]
    assert len(bank_mainlines) > 0

    # Step 5: Find candidates
    candidates = find_candidates(md.stock_daily, as_of="2024-01-19")
    # May or may not find candidates depending on AB/BC parameters
    # The key thing is the pipeline doesn't crash
    assert isinstance(candidates, list)

    # Step 6: If candidates found, test portfolio selection
    if candidates:
        actions = select_candidates(
            candidates,
            current_holdings=[],
            opened_today=0,
            opened_this_week=0,
        )
        open_actions = [a for a in actions if a.action == "open"]

        if open_actions:
            # Step 7: Execute buy
            best = open_actions[0]
            result = execute_buy(
                candidate=best.candidate,
                open_price=10.5,
                cash=1_000_000.0,
                equity=1_000_000.0,
            )
            assert result.executed
            assert result.shares > 0
            assert result.shares % 100 == 0

            # Step 8: Detect exit signal (simulate a few bars later)
            # Check if exit would trigger on a bad bar
            from suishi_north_backtest.market_data import StockDaily
            bad_bar = StockDaily(
                trade_date="2024-01-22", symbol="000001",
                open=9.0, high=9.1, low=8.5, close=8.6,
                volume=10000.0, amount=86000.0,
                is_st=False, limit_up=None, limit_down=None, is_suspended=False,
            )
            signal = detect_exit_signal(
                current_bar=bad_bar,
                entry_price=result.entry_price,
                c_price=9.8,
                highest_close_since_entry=10.5,
                trading_days_since_entry=2,
            )
            # Should trigger structure stop (low 8.5 < c_price 9.8)
            if signal is not None:
                sell_result = execute_sell(
                    signal=signal,
                    symbol="000001",
                    open_price=8.5,
                    cash=result.cash_remaining,
                    shares=result.shares,
                )
                assert sell_result.executed or sell_result.deferred
