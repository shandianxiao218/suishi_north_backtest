"""端到端测试：从 raw snapshot 到策略模块完整串联。

不要求完整盈利逻辑，但必须证明模块可以串联。
不允许条件性跳过核心链路。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from suishi_north_backtest.execution import execute_buy, execute_sell
from suishi_north_backtest.exits import detect_exit_signal
from suishi_north_backtest.mainline import compute_mainlines
from suishi_north_backtest.market_data import load_market_data
from suishi_north_backtest.portfolio import select_candidates
from suishi_north_backtest.raw_data import validate_raw_snapshot
from suishi_north_backtest.signals import find_candidates
from suishi_north_backtest.universe import build_universe


# ---- 辅助函数 ----

STOCK_DAILY_FIELDS = [
    "trade_date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "limit_up",
    "limit_down",
]

INDEX_DAILY_FIELDS = [
    "trade_date",
    "index_code",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]


def _write_csv(
    path: Path, fields: list[str], rows: list[list[str]]
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        writer.writerows(rows)


def _build_raw_snapshot(snapshot_dir: Path) -> None:
    """构建一个必定触发候选信号的 raw snapshot。

    结构设计：
    - A 点 (idx 2, 2024-01-04, close=8.0): 局部低点
    - B 点 (idx 9, 2024-01-15, close=12.0): 局部高点, AB gain=50%
    - C 点 (idx 14, 2024-01-22, close=10.2): 局部低点, BC 回撤=45%
    - 信号日 (idx 16, 2024-01-24, close=10.7): 站上 5 日均线, 距 C 点 4.9%
    """
    manifest = {
        "data_version": "e2e-test-v1",
        "source": "e2e-test",
        "created_at": "2024-01-01T00:00:00+08:00",
        "stock_daily_file": "stock_daily.csv",
        "index_daily_file": "index_daily.csv",
        "industry_map_file": "industry_map.csv",
        "industry_daily_amount_file": "industry_daily_amount.csv",
        "trading_calendar_file": "trading_calendar.csv",
    }
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    # 日线数据：精心构造 A-B-C 结构
    #   idx 0-1: 下跌到 A
    #   idx 2:   A 点 (局部低点, close=8.0)
    #   idx 3-8: 上升到 B
    #   idx 9:   B 点 (局部高点, close=12.0)
    #   idx 10-13: 回落到 C
    #   idx 14:  C 点 (局部低点, close=10.2)
    #   idx 15-16: 转强，信号日 idx 16
    #   idx 17+: 退出检测用数据
    base_prices = [
        # (date, open, high, low, close, volume, amount, limit_up, limit_down)
        ("2024-01-02", "9.5",  "9.8",  "9.0",  "9.5",  "50000",  "475000",  "10.45", "8.55"),     # 0
        ("2024-01-03", "9.2",  "9.5",  "8.8",  "9.0",  "45000",  "405000",  "9.90",  "8.10"),      # 1
        ("2024-01-04", "8.8",  "9.0",  "7.9",  "8.0",  "60000",  "480000",  "8.80",  "7.20"),      # 2  A
        ("2024-01-05", "8.3",  "9.0",  "8.1",  "8.8",  "55000",  "484000",  "9.68",  "7.92"),      # 3
        ("2024-01-08", "9.0",  "9.8",  "8.9",  "9.6",  "70000",  "672000",  "10.56", "8.64"),      # 4
        ("2024-01-09", "9.8",  "10.5", "9.7",  "10.3", "80000",  "824000",  "11.33", "9.27"),      # 5
        ("2024-01-10", "10.5", "11.0", "10.2", "10.8", "85000",  "918000",  "11.88", "9.72"),      # 6
        ("2024-01-11", "10.9", "11.5", "10.8", "11.3", "90000",  "1017000", "12.43", "10.17"),     # 7
        ("2024-01-12", "11.5", "12.2", "11.3", "11.8", "95000",  "1121000", "12.98", "10.62"),     # 8
        ("2024-01-15", "12.0", "12.8", "11.8", "12.0",  "100000", "1200000", "13.20", "10.80"),    # 9  B
        ("2024-01-16", "11.8", "12.0", "11.2", "11.5", "80000",  "920000",  "12.65", "10.35"),     # 10
        ("2024-01-17", "11.3", "11.5", "10.8", "11.0", "75000",  "825000",  "12.10", "9.90"),      # 11
        ("2024-01-18", "10.8", "11.2", "10.5", "10.8", "65000",  "702000",  "11.88", "9.72"),      # 12
        ("2024-01-19", "10.5", "10.8", "10.2", "10.5", "60000",  "630000",  "11.55", "9.45"),      # 13
        ("2024-01-22", "10.3", "10.6", "10.0", "10.2", "55000",  "561000",  "11.22", "9.18"),      # 14 C
        ("2024-01-23", "10.2", "10.8", "10.1", "10.5", "60000",  "630000",  "11.55", "9.45"),      # 15
        ("2024-01-24", "10.5", "10.9", "10.4", "10.7", "65000",  "695500", "11.77", "9.63"),       # 16 signal
        ("2024-01-25", "10.7", "11.0", "10.6", "10.9", "68000",  "741200", "11.99", "9.81"),       # 17
        ("2024-01-26", "10.9", "11.2", "10.8", "11.1", "70000",  "777000", "12.21", "9.99"),       # 18
        ("2024-01-29", "11.1", "11.4", "11.0", "11.3", "72000",  "813600", "12.43", "10.17"),      # 19
        ("2024-01-30", "11.3", "11.6", "11.2", "11.5", "74000",  "851000", "12.65", "10.35"),      # 20
        ("2024-01-31", "11.5", "11.8", "11.4", "11.7", "76000",  "889200", "12.87", "10.53"),      # 21
        ("2024-02-01", "11.7", "12.0", "11.6", "11.9", "78000",  "928200", "13.09", "10.71"),      # 22
        ("2024-02-02", "11.9", "12.2", "11.8", "12.1", "80000",  "968000", "13.31", "10.89"),      # 23
        ("2024-02-05", "12.0", "12.3", "11.9", "12.2", "82000",  "1000400", "13.42", "10.98"),     # 24
        ("2024-02-06", "12.1", "12.4", "12.0", "12.3", "84000",  "1033200", "13.53", "11.07"),     # 25
        ("2024-02-07", "12.2", "12.5", "12.1", "12.4", "86000",  "1066400", "13.64", "11.16"),     # 26
        ("2024-02-08", "12.3", "12.6", "12.2", "12.5", "88000",  "1100000", "13.75", "11.25"),     # 27
        ("2024-02-19", "12.4", "12.7", "12.3", "12.6", "90000",  "1134000", "13.86", "11.34"),     # 28
        ("2024-02-20", "12.5", "12.8", "12.4", "12.7", "92000",  "1168400", "13.97", "11.43"),     # 29
    ]

    rows = []
    for row in base_prices:
        # row = (date, open, high, low, close, volume, amount, limit_up, limit_down)
        rows.append([row[0], "000001", *row[1:]])

    _write_csv(snapshot_dir / "stock_daily.csv", STOCK_DAILY_FIELDS, rows)

    # 指数数据
    _write_csv(
        snapshot_dir / "index_daily.csv",
        INDEX_DAILY_FIELDS,
        [
            ["2024-01-02", "000300", "3500.0", "3520.0", "3490.0", "3510.0", "10000000", "35000000000"],
            ["2024-01-03", "000300", "3510.0", "3530.0", "3505.0", "3525.0", "9500000", "33500000000"],
        ],
    )

    # 行业映射
    _write_csv(
        snapshot_dir / "industry_map.csv",
        ["symbol", "industry_level2"],
        [["000001", "电子"]],
    )

    # 行业日成交额（连续多天电子行业排名第1，触发强主线）
    industry_rows = []
    all_dates = [r[0] for r in base_prices]
    for d in all_dates:
        industry_rows.append([d, "电子", "5000000000"])
        industry_rows.append([d, "银行", "1000000000"])
        industry_rows.append([d, "地产", "800000000"])
        industry_rows.append([d, "医药", "600000000"])
        industry_rows.append([d, "消费", "500000000"])
        industry_rows.append([d, "其他", "400000000"])

    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        industry_rows,
    )

    # 交易日历
    cal_rows = [[d, "1"] for d in all_dates]
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        cal_rows,
    )


def test_raw_to_strategy_modules_minimal_end_to_end_flow(tmp_path: Path) -> None:
    """从 raw snapshot 串联所有策略模块，证明模块可协同工作。

    全链路：raw snapshot -> validate -> load -> universe -> mainline
           -> candidates -> select -> buy -> detect_exit -> sell
    不允许条件性跳过核心链路。
    """

    # Step 1: 创建 raw snapshot
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_raw_snapshot(snapshot_dir)

    # Step 2: validate_raw_snapshot
    manifest = validate_raw_snapshot(snapshot_dir)
    assert manifest.data_version == "e2e-test-v1"

    # Step 3: load_market_data
    md = load_market_data(snapshot_dir, manifest)
    assert len(md.stock_daily) > 0
    assert len(md.trading_calendar) > 0

    # Step 4: build_universe
    universe = build_universe(md, as_of="2024-02-01")
    assert len(universe) > 0
    symbols = {e.symbol for e in universe}
    assert "000001" in symbols

    # Step 5: compute_mainlines
    mainlines = compute_mainlines(md.industry_daily_amount, as_of="2024-02-01")
    assert len(mainlines) > 0
    strong_mainlines = [
        m for m in mainlines
        if m.industry_level2 == "电子"
        and m.status.value == "strong"
    ]
    assert len(strong_mainlines) > 0

    # Step 6: find_candidates（强制断言非空）
    candidates = find_candidates(md.stock_daily, as_of="2024-02-01")
    assert len(candidates) > 0, (
        "find_candidates 必须返回非空候选列表，"
        "测试数据应保证产生候选"
    )
    first_candidate = candidates[0]
    assert first_candidate.symbol == "000001"
    # 验证 AB/BC 结构：A=8.0, B=12.0, C=10.2
    assert first_candidate.a_price < first_candidate.b_price
    assert first_candidate.c_price < first_candidate.b_price

    # Step 7: select_candidates（强制断言有 open action）
    actions = select_candidates(
        candidates=candidates,
        current_holdings=[],
        opened_today=0,
        opened_this_week=0,
    )
    assert len(actions) > 0
    open_actions = [a for a in actions if a.action == "open"]
    assert len(open_actions) >= 1, (
        "select_candidates 必须产生至少一个 open action"
    )
    first_open = open_actions[0]
    assert first_open.candidate is not None

    # Step 8: execute_buy（强制断言成功）
    buy_result = execute_buy(
        candidate=first_open.candidate,
        open_price=10.5,
        cash=1_000_000.0,
        equity=1_000_000.0,
    )
    assert buy_result.executed, (
        f"execute_buy 必须成功，但被跳过：{buy_result.skip_reason}"
    )
    assert buy_result.shares > 0
    assert buy_result.entry_price is not None

    # Step 9: detect_exit_signal（必须实际调用）
    bars_after_entry = [
        b for b in md.stock_daily
        if b.symbol == "000001" and b.trade_date > first_candidate.signal_date
    ]
    assert len(bars_after_entry) >= 1, (
        "信号日之后必须至少有一根 bar 用于退出检测"
    )
    exit_bar = bars_after_entry[0]
    exit_signal = detect_exit_signal(
        bars=[exit_bar],
        entry_price=buy_result.entry_price,
        c_price=first_candidate.c_price,
        highest_close_since_entry=buy_result.entry_price,
        entry_date=first_candidate.signal_date,
        current_date=exit_bar.trade_date,
        trading_days_since_entry=1,
    )
    # 退出信号可能为 None（无触发），但函数必须可正常调用
    assert exit_signal is None or hasattr(exit_signal, "exit_type")

    # Step 10: execute_sell（必须实际调用）
    sell_result = execute_sell(
        symbol="000001",
        open_price=exit_bar.open,
        shares=buy_result.shares,
        high=exit_bar.high,
        low=exit_bar.low,
        close=exit_bar.close,
        limit_down=exit_bar.limit_down,
        is_suspended=exit_bar.is_suspended,
    )
    assert isinstance(sell_result.executed, bool)
    if sell_result.executed:
        assert sell_result.sell_price is not None
        assert sell_result.sell_price < exit_bar.open  # 含卖出滑点
        assert sell_result.cash_proceeds > 0
