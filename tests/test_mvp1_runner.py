"""mvp1_runner 测试：raw snapshot -> Mvp1DataSet -> 标准输出目录。

覆盖 4 个必须场景：
1. raw snapshot 能生成 Mvp1DataSet（字段完整）
2. raw runner 能写标准输出目录（所有文件存在、metadata 一致）
3. 无候选时也要有审计
4. 防未来函数
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.engine import write_mvp1_dataset_outputs
from suishi_north_backtest.mvp1_runner import run_mvp1_from_raw_snapshot


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


def _write_csv(path: Path, fields: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        writer.writerows(rows)


def _build_raw_snapshot(snapshot_dir: Path) -> None:
    """构造一个必定触发候选信号的 raw snapshot。

    A 点 (2024-01-04, close=8.0) -> B 点 (2024-01-15, close=12.0, AB gain=50%)
    -> C 点 (2024-01-22, close=10.2, BC 回撤=45%)
    -> 信号日 (2024-01-24, close=10.7, 站上 5 日均线, 距 C 点 4.9%)
    """
    manifest = {
        "data_version": "mvp1-runner-test-v1",
        "source": "mvp1-runner-test",
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

    base_prices = [
        ("2024-01-02", "9.5",  "9.8",  "9.0",  "9.5",  "50000",  "475000",  "10.45", "8.55"),
        ("2024-01-03", "9.2",  "9.5",  "8.8",  "9.0",  "45000",  "405000",  "9.90",  "8.10"),
        ("2024-01-04", "8.8",  "9.0",  "7.9",  "8.0",  "60000",  "480000",  "8.80",  "7.20"),
        ("2024-01-05", "8.3",  "9.0",  "8.1",  "8.8",  "55000",  "484000",  "9.68",  "7.92"),
        ("2024-01-08", "9.0",  "9.8",  "8.9",  "9.6",  "70000",  "672000",  "10.56", "8.64"),
        ("2024-01-09", "9.8",  "10.5", "9.7",  "10.3", "80000",  "824000",  "11.33", "9.27"),
        ("2024-01-10", "10.5", "11.0", "10.2", "10.8", "85000",  "918000",  "11.88", "9.72"),
        ("2024-01-11", "10.9", "11.5", "10.8", "11.3", "90000",  "1017000", "12.43", "10.17"),
        ("2024-01-12", "11.5", "12.2", "11.3", "11.8", "95000",  "1121000", "12.98", "10.62"),
        ("2024-01-15", "12.0", "12.8", "11.8", "12.0",  "100000", "1200000", "13.20", "10.80"),
        ("2024-01-16", "11.8", "12.0", "11.2", "11.5", "80000",  "920000",  "12.65", "10.35"),
        ("2024-01-17", "11.3", "11.5", "10.8", "11.0", "75000",  "825000",  "12.10", "9.90"),
        ("2024-01-18", "10.8", "11.2", "10.5", "10.8", "65000",  "702000",  "11.88", "9.72"),
        ("2024-01-19", "10.5", "10.8", "10.2", "10.5", "60000",  "630000",  "11.55", "9.45"),
        ("2024-01-22", "10.3", "10.6", "10.0", "10.2", "55000",  "561000",  "11.22", "9.18"),
        ("2024-01-23", "10.2", "10.8", "10.1", "10.5", "60000",  "630000",  "11.55", "9.45"),
        ("2024-01-24", "10.5", "10.9", "10.4", "10.7", "65000",  "695500", "11.77", "9.63"),
        ("2024-01-25", "10.7", "11.0", "10.6", "10.9", "68000",  "741200", "11.99", "9.81"),
        ("2024-01-26", "10.9", "11.2", "10.8", "11.1", "70000",  "777000", "12.21", "9.99"),
        ("2024-01-29", "11.1", "11.4", "11.0", "11.3", "72000",  "813600", "12.43", "10.17"),
        ("2024-01-30", "11.3", "11.6", "11.2", "11.5", "74000",  "851000", "12.65", "10.35"),
        ("2024-01-31", "11.5", "11.8", "11.4", "11.7", "76000",  "889200", "12.87", "10.53"),
        ("2024-02-01", "11.7", "12.0", "11.6", "11.9", "78000",  "928200", "13.09", "10.71"),
        ("2024-02-02", "11.9", "12.2", "11.8", "12.1", "80000",  "968000", "13.31", "10.89"),
        ("2024-02-05", "12.0", "12.3", "11.9", "12.2", "82000",  "1000400", "13.42", "10.98"),
        ("2024-02-06", "12.1", "12.4", "12.0", "12.3", "84000",  "1033200", "13.53", "11.07"),
        ("2024-02-07", "12.2", "12.5", "12.1", "12.4", "86000",  "1066400", "13.64", "11.16"),
        ("2024-02-08", "12.3", "12.6", "12.2", "12.5", "88000",  "1100000", "13.75", "11.25"),
        ("2024-02-19", "12.4", "12.7", "12.3", "12.6", "90000",  "1134000", "13.86", "11.34"),
        ("2024-02-20", "12.5", "12.8", "12.4", "12.7", "92000",  "1168400", "13.97", "11.43"),
    ]

    stock_rows = []
    for row in base_prices:
        stock_rows.append([row[0], "000001", *row[1:]])

    _write_csv(snapshot_dir / "stock_daily.csv", STOCK_DAILY_FIELDS, stock_rows)

    _write_csv(
        snapshot_dir / "index_daily.csv",
        INDEX_DAILY_FIELDS,
        [
            ["2024-01-02", "000300", "3500.0", "3520.0", "3490.0", "3510.0", "10000000", "35000000000"],
            ["2024-01-03", "000300", "3510.0", "3530.0", "3505.0", "3525.0", "9500000", "33500000000"],
            ["2024-01-04", "000300", "3520.0", "3540.0", "3515.0", "3530.0", "9800000", "34600000000"],
            ["2024-01-05", "000300", "3530.0", "3550.0", "3525.0", "3540.0", "9700000", "34400000000"],
        ],
    )

    _write_csv(
        snapshot_dir / "industry_map.csv",
        ["symbol", "industry_level2"],
        [["000001", "电子"]],
    )

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

    cal_rows = [[d, "1"] for d in all_dates]
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        cal_rows,
    )


def _make_config(snapshot_dir: Path, output_dir: Path) -> BacktestConfig:
    return BacktestConfig(
        name="mvp1-runner-test",
        start_date="2024-01-01",
        end_date="2024-02-20",
        initial_cash=1_000_000,
        output_dir=output_dir,
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )


def test_run_mvp1_from_raw_snapshot_returns_dataset(tmp_path: Path) -> None:
    """raw snapshot 能生成 Mvp1DataSet，所有关键字段非空。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_raw_snapshot(snapshot_dir)

    config = _make_config(snapshot_dir, tmp_path / "output")
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config)

    assert data_set.data_version == "mvp1-runner-test-v1"
    assert data_set.parameter_set
    assert data_set.universe

    assert len(data_set.candidates) > 0, "候选列表不能为空"

    has_trades = len(data_set.trades) > 0
    has_skips = len(data_set.skipped_trades) > 0
    has_holdings = len(data_set.holdings) > 0
    assert has_trades or has_skips or has_holdings, (
        "trades、skipped_trades 或 holdings 至少一类非空"
    )

    assert "trade_count" in data_set.metrics
    assert "total_return" in data_set.metrics
    assert "max_drawdown" in data_set.metrics

    benchmark_names = {row["benchmark"] for row in data_set.benchmark_comparison}
    for name in ("CSI300", "CSI500", "CSI1000"):
        assert name in benchmark_names, f"benchmark_comparison 缺少 {name}"

    assert len(data_set.sensitivity) >= 2, "sensitivity 至少 baseline + 一个扰动"


def test_raw_runner_can_write_mvp1_output_dir(tmp_path: Path) -> None:
    """raw runner 能写标准 MVP-1 输出目录，所有文件存在且 metadata 一致。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_raw_snapshot(snapshot_dir)

    output_dir = tmp_path / "output"
    config = _make_config(snapshot_dir, output_dir)
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config)
    result = write_mvp1_dataset_outputs(config, data_set)

    expected_files = [
        "equity_curve.csv",
        "trades.csv",
        "skipped_trades.csv",
        "run_metadata.json",
        "metrics.json",
        "candidates.csv",
        "holdings.csv",
        "benchmark_comparison.csv",
        "track_comparison.csv",
        "sensitivity.csv",
    ]
    for filename in expected_files:
        path = result.output_dir / filename
        assert path.exists(), f"输出文件缺失：{filename}"

    metadata = json.loads(
        (result.output_dir / "run_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["data_source"] == "a-stock-data"
    assert metadata["data_version"] == "mvp1-runner-test-v1"
    assert metadata["parameter_set"]
    assert metadata["universe"]


def test_run_mvp1_from_raw_snapshot_outputs_skip_audit_when_no_candidate(
    tmp_path: Path,
) -> None:
    """无候选时不能静默成功，skipped_trades 或 metrics 必须记录无候选原因。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    manifest = {
        "data_version": "empty-test-v1",
        "source": "empty-test",
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

    # 只有几根平缓 bar，不可能触发 AB=20% 涨幅
    flat_rows = []
    for i, d in enumerate(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]):
        price = 10.0 + i * 0.01
        flat_rows.append(
            [d, "000001", f"{price:.2f}", f"{price + 0.1:.2f}",
             f"{price - 0.1:.2f}", f"{price:.2f}", "50000", "500000", "11.00", "9.00"]
        )
    _write_csv(snapshot_dir / "stock_daily.csv", STOCK_DAILY_FIELDS, flat_rows)

    _write_csv(
        snapshot_dir / "index_daily.csv",
        INDEX_DAILY_FIELDS,
        [["2024-01-02", "000300", "3500", "3520", "3490", "3510", "10000", "35000000"]],
    )

    _write_csv(
        snapshot_dir / "industry_map.csv",
        ["symbol", "industry_level2"],
        [["000001", "电子"]],
    )

    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        [["2024-01-02", "电子", "1000000"]],
    )

    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        [["2024-01-02", "1"], ["2024-01-03", "1"], ["2024-01-04", "1"], ["2024-01-05", "1"]],
    )

    config = BacktestConfig(
        name="empty-test",
        start_date="2024-01-01",
        end_date="2024-01-05",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config)

    assert len(data_set.candidates) == 0
    assert len(data_set.skipped_trades) > 0, "无候选时 skipped_trades 不能为空"

    reasons = " ".join(
        str(row.get("reason", "")) for row in data_set.skipped_trades
    )
    assert "未产生候选" in reasons or "候选" in reasons


def test_run_mvp1_from_raw_snapshot_does_not_use_future_data(tmp_path: Path) -> None:
    """防未来函数：截断 as_of 后不应产生额外候选。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_raw_snapshot(snapshot_dir)

    config_early = BacktestConfig(
        name="mvp1-runner-test-early",
        start_date="2024-01-01",
        end_date="2024-01-10",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output-early",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )
    data_early = run_mvp1_from_raw_snapshot(snapshot_dir, config_early)

    config_full = _make_config(snapshot_dir, tmp_path / "output-full")
    data_full = run_mvp1_from_raw_snapshot(snapshot_dir, config_full)

    # 完整周期的候选数应 >= 早期周期的候选数
    # 早期 as_of=2024-01-10 时 AB 结构可能尚未完全形成，候选数应更少
    assert len(data_full.candidates) >= len(data_early.candidates), (
        "早期 as_of 的候选数不应超过完整周期的候选数，否则存在未来函数"
    )


def test_run_mvp1_from_raw_snapshot_excludes_candidates_after_as_of(
    tmp_path: Path,
) -> None:
    """防未来函数：as_of 位于 AB 结构形成前，不应产生任何候选。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_raw_snapshot(snapshot_dir)

    # as_of=2024-01-08：A 点已出现 (01-04)，但 B 点尚未形成 (01-15)
    # 不可能产生完整的 AB-BC-C 候选结构
    config_before_b = BacktestConfig(
        name="before-b-point",
        start_date="2024-01-01",
        end_date="2024-01-08",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output-before-b",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )
    data_before_b = run_mvp1_from_raw_snapshot(snapshot_dir, config_before_b)

    assert len(data_before_b.candidates) == 0, (
        "as_of=2024-01-08 时 B 点尚未形成，不应产生候选，否则存在未来函数"
    )


def test_runner_closed_trade_cash_matches_buy_cash_plus_sell_proceeds(
    tmp_path: Path,
) -> None:
    """断言最终现金等价于 initial_cash - entry_cost - buy_commission + sell_cash_proceeds。

    验证买入佣金不被重复扣除。
    """
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    # 构造一个能快速触发退出的 snapshot：
    # 在信号日之后立即大幅下跌触发应急止损
    manifest = {
        "data_version": "cash-test-v1",
        "source": "cash-test",
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

    # A=8.0 (01-04), B=12.0 (01-15), C=10.2 (01-22)
    # 信号日 01-24, 买入 01-25
    # 买入后应急止损：entry_price 下跌 5% 以上
    # 01-25 买入 entry_price ≈ 10.7*1.0005 = 10.7054
    # 01-26 close=5.0 -> 从 entry_price 下跌超过 5% -> 应急止损信号
    # 01-29 卖出
    base_prices = [
        ("2024-01-02", "9.5",  "9.8",  "9.0",  "9.5",  "50000",  "475000",  "10.45", "8.55"),
        ("2024-01-03", "9.2",  "9.5",  "8.8",  "9.0",  "45000",  "405000",  "9.90",  "8.10"),
        ("2024-01-04", "8.8",  "9.0",  "7.9",  "8.0",  "60000",  "480000",  "8.80",  "7.20"),
        ("2024-01-05", "8.3",  "9.0",  "8.1",  "8.8",  "55000",  "484000",  "9.68",  "7.92"),
        ("2024-01-08", "9.0",  "9.8",  "8.9",  "9.6",  "70000",  "672000",  "10.56", "8.64"),
        ("2024-01-09", "9.8",  "10.5", "9.7",  "10.3", "80000",  "824000",  "11.33", "9.27"),
        ("2024-01-10", "10.5", "11.0", "10.2", "10.8", "85000",  "918000",  "11.88", "9.72"),
        ("2024-01-11", "10.9", "11.5", "10.8", "11.3", "90000",  "1017000", "12.43", "10.17"),
        ("2024-01-12", "11.5", "12.2", "11.3", "11.8", "95000",  "1121000", "12.98", "10.62"),
        ("2024-01-15", "12.0", "12.8", "11.8", "12.0",  "100000", "1200000", "13.20", "10.80"),
        ("2024-01-16", "11.8", "12.0", "11.2", "11.5", "80000",  "920000",  "12.65", "10.35"),
        ("2024-01-17", "11.3", "11.5", "10.8", "11.0", "75000",  "825000",  "12.10", "9.90"),
        ("2024-01-18", "10.8", "11.2", "10.5", "10.8", "65000",  "702000",  "11.88", "9.72"),
        ("2024-01-19", "10.5", "10.8", "10.2", "10.5", "60000",  "630000",  "11.55", "9.45"),
        ("2024-01-22", "10.3", "10.6", "10.0", "10.2", "55000",  "561000",  "11.22", "9.18"),
        ("2024-01-23", "10.2", "10.8", "10.1", "10.5", "60000",  "630000",  "11.55", "9.45"),
        ("2024-01-24", "10.5", "10.9", "10.4", "10.7", "65000",  "695500", "11.77", "9.63"),
        # T+1 买入日：open=10.7
        ("2024-01-25", "10.7", "11.0", "10.6", "10.9", "68000",  "741200", "11.99", "9.81"),
        # 大幅下跌触发应急止损（entry≈10.7054, 跌5%→10.17）
        ("2024-01-26", "6.0",  "6.5",  "5.5",  "5.8",   "100000", "580000",  "6.60",  "5.40"),
        # T+1 卖出日
        ("2024-01-29", "5.8",  "6.2",  "5.5",  "5.9",   "80000",  "472000",  "6.38",  "5.22"),
    ]

    stock_rows = [[r[0], "000001", *r[1:]] for r in base_prices]
    _write_csv(snapshot_dir / "stock_daily.csv", STOCK_DAILY_FIELDS, stock_rows)

    _write_csv(
        snapshot_dir / "index_daily.csv",
        INDEX_DAILY_FIELDS,
        [["2024-01-02", "000300", "3500", "3520", "3490", "3510", "10000", "35000000"]],
    )

    _write_csv(
        snapshot_dir / "industry_map.csv",
        ["symbol", "industry_level2"],
        [["000001", "电子"]],
    )

    industry_rows = []
    for r in base_prices:
        for ind, amt in [("电子", "5000000000"), ("银行", "1000000000"),
                         ("地产", "800000000"), ("医药", "600000000"),
                         ("消费", "500000000"), ("其他", "400000000")]:
            industry_rows.append([r[0], ind, amt])
    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        industry_rows,
    )

    cal_rows = [[r[0], "1"] for r in base_prices]
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        cal_rows,
    )

    config = BacktestConfig(
        name="cash-test",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config)

    assert len(data_set.trades) >= 1, "必须有至少一笔平仓交易"
    trade = data_set.trades[0]
    final_cash = float(data_set.equity_curve[-1]["cash"])

    # 手动计算预期现金：
    # initial_cash - entry_cost - buy_commission + sell_cash_proceeds
    entry_price = float(trade["entry_price"])
    shares = int(trade["entry_shares"])
    exit_price = float(trade["exit_price"])
    buy_commission = float(trade["commission"]) - float(trade.get("stamp_tax", "0"))
    # trade.commission = buy_commission + sell_commission
    # 需要从 ClosedTrade 获取更精确的值

    # 直接从 equity_curve 的最终 cash 值验证
    # 等价公式：cash = initial_cash - shares*entry_price - buy_cost + sell_proceeds
    # 其中 buy_cost 只含买入佣金（滑点已计入 entry_price）
    # sell_proceeds = shares*exit_price*(1-slippage) - sell_commission - stamp_tax

    # 用更直接的方式：最终 cash 不应小于 initial_cash - entry_cost - 2*buy_commission
    # 如果 buy_commission 被重复扣，cash 会比正确值少 buy_commission
    entry_cost = shares * entry_price
    trade_commission = float(trade["commission"])  # buy + sell commission total
    stamp_tax = float(trade["stamp_tax"])

    # 正确公式：cash = initial - entry_cost - buy_commission + sell_proceeds
    # sell_proceeds = shares * exit_price * (1 - slippage_rate) - sell_commission - stamp_tax
    # 近似验证：cash 应约等于 initial + gross_pnl - all_costs
    # 且 gross_pnl = (exit_price - entry_price) * shares
    # all_costs = buy_commission + sell_commission + stamp_tax + slippages
    # 注意 slippages 已计入 entry_price 和 exit_price

    # 精确验证：最终 cash = initial + net_pnl
    # net_pnl = gross_pnl - total_cost (不含重复)
    # 但 net_pnl 在 trade 中记录了扣全部成本后的值
    # 所以 cash = initial + trade.net_pnl (如果现金公式正确)
    net_pnl = float(trade["net_pnl"])
    expected_cash = 1_000_000 + net_pnl

    # 允许 1 元 rounding 误差
    assert abs(final_cash - expected_cash) < 1.0, (
        f"现金不一致：final_cash={final_cash:.2f}, "
        f"expected={expected_cash:.2f}, "
        f"diff={abs(final_cash - expected_cash):.2f}，"
        f"可能买入佣金被重复扣除"
    )
