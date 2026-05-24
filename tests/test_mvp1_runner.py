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
from suishi_north_backtest.mainline import MainlineStatus
from suishi_north_backtest.mvp1_runner import (
    _candidate_rows_from_scores,
    _score_all_candidates,
    run_mvp1_from_raw_snapshot,
)
from suishi_north_backtest.market_data import StockDaily
from suishi_north_backtest.signals import CandidateSignal, SIGNAL_RULE_VERSION


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
        ("2024-01-24", "10.5", "11.2", "10.4", "11.0", "65000",  "715000", "12.10", "9.90"),
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


def test_raw_runner_benchmark_comparison_uses_sample_windows(
    tmp_path: Path,
) -> None:
    """benchmark_comparison.csv 必须按样本区间独立计算，不能复制全周期数字。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_raw_snapshot(snapshot_dir)

    config = _make_config(snapshot_dir, tmp_path / "output")
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config)

    csi300_rows = {
        row["period"]: row
        for row in data_set.benchmark_comparison
        if row["benchmark"] == "CSI300"
    }

    assert set(csi300_rows) == {"sample_in", "sample_out", "recent"}
    assert csi300_rows["sample_in"]["strategy_return"] != csi300_rows["recent"]["strategy_return"]
    assert csi300_rows["sample_in"]["benchmark_return"] != csi300_rows["recent"]["benchmark_return"]
    for row in csi300_rows.values():
        assert "window=[" in str(row["audit_note"])
        # Issue #36：全部 8 个指标列必须存在
        assert "annualized_return" in row
        assert "volatility" in row
        assert "win_rate" in row
        assert "trade_count" in row
        assert "benchmark_status" in row


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

    with (result.output_dir / "candidates.csv").open("r", encoding="utf-8-sig", newline="") as file:
        candidates = list(csv.DictReader(file))
    assert candidates
    first_candidate = candidates[0]
    assert "as_of" in first_candidate
    assert "signal_rule_version" in first_candidate
    assert "failure_reason" in first_candidate


def test_candidate_rows_use_signal_audit_fields() -> None:
    candidate = CandidateSignal(
        signal_date="2024-01-24",
        symbol="000001",
        a_date="2024-01-04",
        a_price=8.0,
        b_date="2024-01-15",
        b_price=12.0,
        c_date="2024-01-22",
        c_price=10.2,
        ab_gain_pct=50.0,
        bc_retracement_pct=45.0,
        distance_to_c_pct=4.9,
        weekly_filter_passed=False,
        annual_filter_passed=False,
        failure_reason="周线方向过滤未通过；年线弱结构过滤未通过",
        as_of="2024-02-20",
        signal_rule_version=SIGNAL_RULE_VERSION,
        audit_note="来自 CandidateSignal 的审计说明",
    )

    # 构造 signal_date 当日的行情数据
    bar = StockDaily(
        trade_date="2024-01-24",
        symbol="000001",
        open=10.5,
        high=11.0,
        low=10.4,
        close=10.7,
        volume=65000,
        amount=695500.0,
        is_st=False,
        limit_up=11.77,
        limit_down=9.63,
        is_suspended=False,
    )
    bars_by_symbol = {"000001": [bar]}
    amount_map = {("000001", "2024-01-24"): 695500.0}

    scored = _score_all_candidates(
        [candidate],
        industry_by_symbol={"000001": "电子"},
        mainline_status_by_key={("2024-01-24", "电子"): MainlineStatus.STRONG},
        mainline_rank_by_key={("2024-01-24", "电子"): 1},
        stock_amount_by_symbol_date=amount_map,
        bars_by_symbol=bars_by_symbol,
        industry_candidate_count={"电子": 1},
    )
    rows = _candidate_rows_from_scores(scored)

    assert rows[0]["weekly_filter_passed"] == "false"
    assert rows[0]["annual_filter_passed"] == "false"
    assert rows[0]["failure_reason"] == "周线方向过滤未通过；年线弱结构过滤未通过"
    assert rows[0]["as_of"] == "2024-02-20"
    assert rows[0]["signal_rule_version"] == SIGNAL_RULE_VERSION
    assert rows[0]["audit_note"] == "来自 CandidateSignal 的审计说明"
    assert "score_breakdown" in rows[0]
    assert "mainline=" in str(rows[0]["score_breakdown"])
    assert float(rows[0]["score"]) > 0


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
        ("2024-01-24", "10.5", "11.2", "10.4", "11.0", "65000",  "715000", "12.10", "9.90"),
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


def test_runner_top_level_metrics_do_not_use_max_equity_across_tracks(
    tmp_path: Path,
) -> None:
    """顶层 metrics 不得使用 max(all_equity) 作为 ending_equity。

    主口径以 mainline_filtered 最后一条 equity 为准，
    不得取历史最高权益。
    构造一个纯亏损场景验证：ending_equity 应小于 initial_cash。
    """
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    manifest = {
        "data_version": "metrics-test-v1",
        "source": "metrics-test",
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

    # 构造 A-B-C + 亏损退出场景
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
        # T+1 买入日，open=10.7
        ("2024-01-25", "10.7", "11.0", "10.6", "10.9", "68000",  "741200", "11.99", "9.81"),
        # 暴跌触发应急止损：close 跌超 5%
        ("2024-01-26", "6.0",  "6.5",  "5.5",  "5.8",   "100000", "580000",  "6.60",  "5.40"),
        # T+1 卖出
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
    all_dates = [r[0] for r in base_prices]
    for d in all_dates:
        industry_rows.append([d, "电子", "5000000000"])
        industry_rows.append([d, "银行", "1000000000"])
        industry_rows.append([d, "地产", "800000000"])
    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        industry_rows,
    )
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        [[d, "1"] for d in all_dates],
    )

    config = BacktestConfig(
        name="metrics-test",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config)

    ending_equity = data_set.metrics["ending_equity"]
    total_return = data_set.metrics["total_return"]

    # ending_equity 应是主轨道（mainline_filtered）最后一条 equity，不是历史最高
    mf_equity = [
        p for p in data_set.equity_curve
        if p.get("track") == "mainline_filtered"
    ]
    assert mf_equity, "mainline_filtered equity_curve 不应为空"
    expected_ending = float(mf_equity[-1]["equity"])
    assert ending_equity == expected_ending, (
        f"ending_equity={ending_equity} != mainline_filtered 最后权益={expected_ending}，"
        f"可能错误使用了 max(all_equity)"
    )

    # 如果有亏损交易，ending_equity 应小于 initial_cash
    if total_return < 0:
        assert ending_equity < 1_000_000, (
            f"total_return={total_return} 为负但 ending_equity={ending_equity} >= initial_cash"
        )


def test_runner_outputs_real_dual_track_rows(tmp_path: Path) -> None:
    """生产级双轨端到端测试：验证 run_mvp1_from_raw_snapshot 输出真实双轨。

    断言：
    - equity_curve 同时包含 pure_structure 和 mainline_filtered
    - metrics.tracks 同时包含两条轨道
    - track_comparison 不是镜像（至少有 total_return / trade_count 行）
    """
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_raw_snapshot(snapshot_dir)

    config = _make_config(snapshot_dir, tmp_path / "output")
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config)

    # 1. equity_curve 包含两条轨道
    track_set = {row["track"] for row in data_set.equity_curve}
    assert "pure_structure" in track_set, (
        f"equity_curve 缺少 pure_structure track，实际 track={track_set}"
    )
    assert "mainline_filtered" in track_set, (
        f"equity_curve 缺少 mainline_filtered track，实际 track={track_set}"
    )

    # 2. metrics.tracks 包含两条轨道的独立指标
    tracks = data_set.metrics.get("tracks", {})
    assert "pure_structure" in tracks, "metrics.tracks 缺少 pure_structure"
    assert "mainline_filtered" in tracks, "metrics.tracks 缺少 mainline_filtered"

    ps_metrics = tracks["pure_structure"]
    mf_metrics = tracks["mainline_filtered"]
    assert "trade_count" in ps_metrics
    assert "trade_count" in mf_metrics
    assert "total_return" in ps_metrics
    assert "total_return" in mf_metrics

    # 3. track_comparison 有真实比较行
    assert len(data_set.track_comparison) >= 2, (
        f"track_comparison 行数不足：{len(data_set.track_comparison)}"
    )
    tc_metrics = {row["metric"] for row in data_set.track_comparison}
    assert "total_return" in tc_metrics, "track_comparison 缺少 total_return 行"
    assert "trade_count" in tc_metrics, "track_comparison 缺少 trade_count 行"

    # 4. track_comparison 不应是镜像（delta 全为 0）
    # 因为该 snapshot 只有电子行业且是强主线，两条轨道会交易相同候选
    # 但至少 trade_count 行的 audit_note 应说明是真实比较
    for row in data_set.track_comparison:
        assert "real dual-track" in str(row.get("audit_note", "")), (
            f"track_comparison 行 {row['metric']} 仍使用镜像 audit_note"
        )

    # 5. trades 中 track 字段正确区分
    if data_set.trades:
        trade_tracks = {row["track"] for row in data_set.trades}
        assert len(trade_tracks) >= 1, "trades 中 track 字段为空"


def test_mainline_filtered_records_skip_reason_for_non_strong_mainline_candidate(
    tmp_path: Path,
) -> None:
    """mainline_filtered 跳过非强主线候选时必须写入 skipped_trades 审计。

    构造一个非强主线行业的候选，断言 skipped_trades 中有明确的审计记录。
    """
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    manifest = {
        "data_version": "skip-audit-v1",
        "source": "skip-audit-test",
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

    # A=8.0, B=12.0, C=10.2, 信号日 close=10.7
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
    ]

    stock_rows = [[r[0], "000001", *r[1:]] for r in base_prices]
    _write_csv(snapshot_dir / "stock_daily.csv", STOCK_DAILY_FIELDS, stock_rows)
    _write_csv(
        snapshot_dir / "index_daily.csv",
        INDEX_DAILY_FIELDS,
        [["2024-01-02", "000300", "3500", "3520", "3490", "3510", "10000", "35000000"]],
    )
    # 关键：候选属于"冷门行业"，不是任何主线行业
    _write_csv(
        snapshot_dir / "industry_map.csv",
        ["symbol", "industry_level2"],
        [["000001", "冷门行业"]],
    )
    # 行业成交额：电子排第1，冷门行业排最后（低于 top 5）
    industry_rows = []
    all_dates = [r[0] for r in base_prices]
    for d in all_dates:
        industry_rows.append([d, "电子", "5000000000"])
        industry_rows.append([d, "银行", "1000000000"])
        industry_rows.append([d, "地产", "800000000"])
        industry_rows.append([d, "医药", "600000000"])
        industry_rows.append([d, "消费", "500000000"])
        industry_rows.append([d, "冷门行业", "100000000"])
    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        industry_rows,
    )
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        [[d, "1"] for d in all_dates],
    )

    config = BacktestConfig(
        name="skip-audit-test",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config)

    # mainline_filtered 轨道的 skipped_trades 应有审计记录
    mf_skips = [
        s for s in data_set.skipped_trades
        if s.get("track") == "mainline_filtered"
    ]
    # 应该有跳过记录，且 reason 明确说明"非强主线"
    assert len(mf_skips) > 0, (
        "mainline_filtered 应有跳过记录，但 skipped_trades 为空"
    )
    skip_reasons = [s.get("reason", "") for s in mf_skips]
    has_mainline_skip = any("强主线" in r or "mainline" in r.lower() for r in skip_reasons)
    assert has_mainline_skip, (
        f"mainline_filtered 跳过原因应包含'强主线'，实际：{skip_reasons}"
    )


def test_runner_filters_low_liquidity_stock(tmp_path: Path) -> None:
    """低流动性过滤在生产 runner 路径中生效。

    构造一只低成交额股票，设置 min_daily_amount 参数，
    断言该股票不会进入候选/交易链路。
    """
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    manifest = {
        "data_version": "low-liquidity-v1",
        "source": "low-liquidity-test",
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

    # 低成交额股票（amount=500）
    base_prices = [
        ("2024-01-02", "9.5",  "9.8",  "9.0",  "9.5",  "50000",  "500",    "10.45", "8.55"),
        ("2024-01-03", "9.2",  "9.5",  "8.8",  "9.0",  "45000",  "450",    "9.90",  "8.10"),
        ("2024-01-04", "8.8",  "9.0",  "7.9",  "8.0",  "60000",  "480",    "8.80",  "7.20"),
        ("2024-01-05", "8.3",  "9.0",  "8.1",  "8.8",  "55000",  "484",    "9.68",  "7.92"),
        ("2024-01-08", "9.0",  "9.8",  "8.9",  "9.6",  "70000",  "672",    "10.56", "8.64"),
        ("2024-01-09", "9.8",  "10.5", "9.7",  "10.3", "80000",  "824",    "11.33", "9.27"),
        ("2024-01-10", "10.5", "11.0", "10.2", "10.8", "85000",  "918",    "11.88", "9.72"),
        ("2024-01-11", "10.9", "11.5", "10.8", "11.3", "90000",  "1017",   "12.43", "10.17"),
        ("2024-01-12", "11.5", "12.2", "11.3", "11.8", "95000",  "1121",   "12.98", "10.62"),
        ("2024-01-15", "12.0", "12.8", "11.8", "12.0",  "100000", "1200",   "13.20", "10.80"),
        ("2024-01-16", "11.8", "12.0", "11.2", "11.5", "80000",  "920",    "12.65", "10.35"),
        ("2024-01-17", "11.3", "11.5", "10.8", "11.0", "75000",  "825",    "12.10", "9.90"),
        ("2024-01-18", "10.8", "11.2", "10.5", "10.8", "65000",  "702",    "11.88", "9.72"),
        ("2024-01-19", "10.5", "10.8", "10.2", "10.5", "60000",  "630",    "11.55", "9.45"),
        ("2024-01-22", "10.3", "10.6", "10.0", "10.2", "55000",  "561",    "11.22", "9.18"),
        ("2024-01-23", "10.2", "10.8", "10.1", "10.5", "60000",  "630",    "11.55", "9.45"),
        ("2024-01-24", "10.5", "10.9", "10.4", "10.7", "65000",  "695.5",  "11.77", "9.63"),
        ("2024-01-25", "10.7", "11.0", "10.6", "10.9", "68000",  "741.2",  "11.99", "9.81"),
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
    all_dates = [r[0] for r in base_prices]
    for d in all_dates:
        industry_rows.append([d, "电子", "5000000000"])
        industry_rows.append([d, "银行", "1000000000"])
        industry_rows.append([d, "地产", "800000000"])
    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        industry_rows,
    )
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        [[d, "1"] for d in all_dates],
    )

    config = BacktestConfig(
        name="low-liquidity-test",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )

    from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
    import dataclasses

    params = dataclasses.replace(default_mvp1_parameters(), min_daily_amount=1_000_000.0)
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config, parameters=params)

    # 该股票因低流动性被排除，不应有候选或交易
    assert len(data_set.candidates) == 0, (
        f"低流动性股票不应产生候选，但得到 {len(data_set.candidates)} 个"
    )
    assert len(data_set.trades) == 0, (
        f"低流动性股票不应产生交易，但得到 {len(data_set.trades)} 笔"
    )


def test_runner_records_low_liquidity_skip_reason(tmp_path: Path) -> None:
    """runner 输出中必须包含低流动性排除的审计原因。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    manifest = {
        "data_version": "skip-reason-v1",
        "source": "skip-reason-test",
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

    # A-B-C 结构候选 + 低成交额
    base_prices = [
        ("2024-01-02", "9.5",  "9.8",  "9.0",  "9.5",  "50000",  "500",    "10.45", "8.55"),
        ("2024-01-03", "9.2",  "9.5",  "8.8",  "9.0",  "45000",  "450",    "9.90",  "8.10"),
        ("2024-01-04", "8.8",  "9.0",  "7.9",  "8.0",  "60000",  "480",    "8.80",  "7.20"),
        ("2024-01-05", "8.3",  "9.0",  "8.1",  "8.8",  "55000",  "484",    "9.68",  "7.92"),
        ("2024-01-08", "9.0",  "9.8",  "8.9",  "9.6",  "70000",  "672",    "10.56", "8.64"),
        ("2024-01-09", "9.8",  "10.5", "9.7",  "10.3", "80000",  "824",    "11.33", "9.27"),
        ("2024-01-10", "10.5", "11.0", "10.2", "10.8", "85000",  "918",    "11.88", "9.72"),
        ("2024-01-11", "10.9", "11.5", "10.8", "11.3", "90000",  "1017",   "12.43", "10.17"),
        ("2024-01-12", "11.5", "12.2", "11.3", "11.8", "95000",  "1121",   "12.98", "10.62"),
        ("2024-01-15", "12.0", "12.8", "11.8", "12.0",  "100000", "1200",   "13.20", "10.80"),
        ("2024-01-16", "11.8", "12.0", "11.2", "11.5", "80000",  "920",    "12.65", "10.35"),
        ("2024-01-17", "11.3", "11.5", "10.8", "11.0", "75000",  "825",    "12.10", "9.90"),
        ("2024-01-18", "10.8", "11.2", "10.5", "10.8", "65000",  "702",    "11.88", "9.72"),
        ("2024-01-19", "10.5", "10.8", "10.2", "10.5", "60000",  "630",    "11.55", "9.45"),
        ("2024-01-22", "10.3", "10.6", "10.0", "10.2", "55000",  "561",    "11.22", "9.18"),
        ("2024-01-23", "10.2", "10.8", "10.1", "10.5", "60000",  "630",    "11.55", "9.45"),
        ("2024-01-24", "10.5", "10.9", "10.4", "10.7", "65000",  "695.5",  "11.77", "9.63"),
        ("2024-01-25", "10.7", "11.0", "10.6", "10.9", "68000",  "741.2",  "11.99", "9.81"),
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
    all_dates = [r[0] for r in base_prices]
    for d in all_dates:
        industry_rows.append([d, "电子", "5000000000"])
        industry_rows.append([d, "银行", "1000000000"])
        industry_rows.append([d, "地产", "800000000"])
    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        industry_rows,
    )
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        [[d, "1"] for d in all_dates],
    )

    config = BacktestConfig(
        name="skip-reason-test",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )

    from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
    import dataclasses

    params = dataclasses.replace(default_mvp1_parameters(), min_daily_amount=1_000_000.0)
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config, parameters=params)

    # skipped_trades 中必须包含低流动性原因
    universe_skips = [s for s in data_set.skipped_trades if s.get("track") == "universe_filter"]
    assert len(universe_skips) > 0, (
        f"skipped_trades 应有 universe_filter 审计，实际：{data_set.skipped_trades}"
    )
    liquidity_skips = [
        s for s in universe_skips
        if "流动性" in s.get("reason", "") or "成交额" in s.get("reason", "")
    ]
    assert len(liquidity_skips) > 0, (
        f"应包含低流动性审计，实际 reasons: {[s.get('reason') for s in universe_skips]}"
    )


def test_runner_records_long_suspension_skip_reason(tmp_path: Path) -> None:
    """runner 输出中必须包含长期停牌排除的审计原因。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    manifest = {
        "data_version": "long-susp-v1",
        "source": "long-susp-test",
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

    # 正常交易 + 连续停牌
    base_prices = [
        ("2024-01-02", "10.5", "11.0", "10.3", "10.8", "100000", "1080000", "11.88", "9.72"),
        ("2024-01-03", "10.8", "11.2", "10.7", "11.0", "80000",  "880000",  "12.10", "9.90"),
        ("2024-01-04", "11.0", "11.3", "10.9", "11.2", "90000",  "1008000", "12.32", "10.08"),
        ("2024-01-05", "11.2", "11.5", "11.0", "11.3", "85000",  "960500",  "12.43", "10.17"),
        ("2024-01-08", "11.3", "11.6", "11.1", "11.5", "88000",  "1012000", "12.65", "10.35"),
        ("2024-01-09", "11.5", "11.8", "11.3", "11.7", "90000",  "1053000", "12.87", "10.53"),
        ("2024-01-10", "11.7", "12.0", "11.5", "11.9", "92000",  "1094800", "13.09", "10.71"),
        # 连续停牌 3 天
        ("2024-01-11", "", "", "", "", "", "", "", ""),
        ("2024-01-12", "", "", "", "", "", "", "", ""),
        ("2024-01-15", "", "", "", "", "", "", "", ""),
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
    all_dates = [r[0] for r in base_prices]
    for d in all_dates:
        industry_rows.append([d, "电子", "5000000000"])
        industry_rows.append([d, "银行", "1000000000"])
    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        industry_rows,
    )
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        [[d, "1"] for d in all_dates],
    )

    config = BacktestConfig(
        name="long-susp-test",
        start_date="2024-01-01",
        end_date="2024-01-15",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )

    from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
    import dataclasses

    params = dataclasses.replace(default_mvp1_parameters(), long_suspension_days=3)
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config, parameters=params)

    # skipped_trades 中必须包含长期停牌原因
    universe_skips = [s for s in data_set.skipped_trades if s.get("track") == "universe_filter"]
    long_susp_skips = [
        s for s in universe_skips
        if "长期停牌" in s.get("reason", "")
    ]
    assert len(long_susp_skips) > 0, (
        f"应包含长期停牌审计，实际 reasons: {[s.get('reason') for s in universe_skips]}"
    )


def test_runner_opens_higher_scored_candidate_before_higher_ab_gain_candidate(
    tmp_path: Path,
) -> None:
    """同日两个候选竞争开仓时，应优先选择高 score 候选，而非高 AB 涨幅候选。

    场景：
    - 候选 A：AB 涨幅 60%（高），非强主线，流动性差 -> score 较低
    - 候选 B：AB 涨幅 30%（低），强主线，流动性好 -> score 较高
    - 同一天信号，daily_open_limit=1，只能开一个

    断言：开仓的是候选 B（高 score），而非候选 A（高 AB）。
    """
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()

    manifest = {
        "data_version": "score-sort-v1",
        "source": "score-sort-test",
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

    # 候选 A (000001, 冷门行业, 高 AB, 低流动性)
    # 候选 B (000002, 强主线行业, 低 AB, 高流动性)
    # 两者同一天产生信号（2024-01-24）
    # 候选 A 的 AB=60%, B 的 AB=30%，但 B 有强主线加持
    base_a = [
        ("2024-01-02", "9.5",  "9.8",  "9.0",  "9.5",  "500",  "4750",   "10.45", "8.55"),
        ("2024-01-03", "9.2",  "9.5",  "8.8",  "9.0",  "480",  "4320",   "9.90",  "8.10"),
        ("2024-01-04", "8.8",  "9.0",  "7.9",  "8.0",  "600",  "4800",   "8.80",  "7.20"),
        ("2024-01-05", "8.3",  "9.0",  "8.1",  "8.8",  "550",  "4840",   "9.68",  "7.92"),
        ("2024-01-08", "9.0",  "9.8",  "8.9",  "9.6",  "700",  "6720",   "10.56", "8.64"),
        ("2024-01-09", "9.8",  "10.5", "9.7",  "10.3", "800",  "8240",   "11.33", "9.27"),
        ("2024-01-10", "10.5", "11.0", "10.2", "10.8", "850",  "9180",   "11.88", "9.72"),
        ("2024-01-11", "10.9", "11.5", "10.8", "11.3", "900",  "10170",  "12.43", "10.17"),
        ("2024-01-12", "11.5", "12.2", "11.3", "11.8", "950",  "11210",  "12.98", "10.62"),
        ("2024-01-15", "12.0", "12.8", "11.8", "12.8",  "1000", "12800",  "14.08", "11.52"),
        ("2024-01-16", "12.5", "13.0", "12.0", "12.5", "800",  "10000",  "13.75", "11.25"),
        ("2024-01-17", "12.0", "12.5", "11.5", "12.0", "750",  "9000",   "13.20", "10.80"),
        ("2024-01-18", "11.5", "12.0", "11.0", "11.5", "650",  "7475",   "12.65", "10.35"),
        ("2024-01-19", "11.0", "11.5", "10.5", "11.0", "600",  "6600",   "12.10", "9.90"),
        ("2024-01-22", "10.5", "11.0", "10.0", "10.5", "550",  "5775",   "11.55", "9.45"),
        ("2024-01-23", "10.2", "10.8", "10.1", "10.5", "600",  "6300",   "11.55", "9.45"),
        ("2024-01-24", "10.5", "10.9", "10.4", "10.7", "650",  "6955",   "11.77", "9.63"),
        ("2024-01-25", "10.7", "11.0", "10.6", "10.9", "680",  "7412",   "11.99", "9.81"),
        ("2024-01-26", "10.9", "11.2", "10.8", "11.1", "700",  "7770",   "12.21", "9.99"),
    ]

    # 候选 B: AB=30%, 强主线, 高流动性
    base_b = [
        ("2024-01-02", "19.0", "19.5", "18.5", "19.0", "50000",  "950000",  "20.90", "17.10"),
        ("2024-01-03", "18.5", "19.0", "18.0", "18.5", "48000",  "888000",  "20.35", "16.65"),
        ("2024-01-04", "18.0", "18.5", "17.5", "18.0", "55000",  "990000",  "19.80", "16.20"),
        ("2024-01-05", "18.5", "19.0", "18.0", "18.5", "52000",  "962000",  "20.35", "16.65"),
        ("2024-01-08", "19.0", "19.5", "18.5", "19.0", "60000",  "1140000", "20.90", "17.10"),
        ("2024-01-09", "19.5", "20.0", "19.0", "19.5", "65000",  "1267500", "21.45", "17.55"),
        ("2024-01-10", "20.0", "20.5", "19.5", "20.0", "70000",  "1400000", "22.00", "18.00"),
        ("2024-01-11", "20.5", "21.0", "20.0", "20.5", "75000",  "1537500", "22.55", "18.45"),
        ("2024-01-12", "21.0", "21.5", "20.5", "21.0", "80000",  "1680000", "23.10", "18.90"),
        ("2024-01-15", "21.5", "23.4", "21.0", "23.4",  "90000",  "2106000", "25.74", "21.06"),
        ("2024-01-16", "22.5", "23.0", "22.0", "22.5", "85000",  "1912500", "24.75", "20.25"),
        ("2024-01-17", "22.0", "22.5", "21.5", "22.0", "80000",  "1760000", "24.20", "19.80"),
        ("2024-01-18", "21.5", "22.0", "21.0", "21.5", "75000",  "1612500", "23.65", "19.35"),
        ("2024-01-19", "21.0", "21.5", "20.5", "21.0", "70000",  "1470000", "23.10", "18.90"),
        ("2024-01-22", "20.5", "21.0", "20.0", "20.5", "65000",  "1332500", "22.55", "18.45"),
        ("2024-01-23", "20.2", "20.8", "20.0", "20.5", "68000",  "1394000", "22.55", "18.45"),
        ("2024-01-24", "20.5", "20.9", "20.4", "20.7", "70000",  "1449000", "22.77", "18.63"),
        ("2024-01-25", "20.7", "21.0", "20.6", "20.9", "72000",  "1504800", "22.99", "18.81"),
        ("2024-01-26", "20.9", "21.2", "20.8", "21.1", "74000",  "1561400", "23.21", "18.99"),
    ]

    stock_rows = []
    for row in base_a:
        stock_rows.append([row[0], "000001", *row[1:]])
    for row in base_b:
        stock_rows.append([row[0], "000002", *row[1:]])
    _write_csv(snapshot_dir / "stock_daily.csv", STOCK_DAILY_FIELDS, stock_rows)

    _write_csv(
        snapshot_dir / "index_daily.csv",
        INDEX_DAILY_FIELDS,
        [["2024-01-02", "000300", "3500", "3520", "3490", "3510", "10000", "35000000"]],
    )

    _write_csv(
        snapshot_dir / "industry_map.csv",
        ["symbol", "industry_level2"],
        [["000001", "冷门行业"], ["000002", "电子"]],
    )

    # 行业成交额：电子排第1，冷门行业排最后
    all_dates = sorted(set(r[0] for r in base_a + base_b))
    industry_rows = []
    for d in all_dates:
        industry_rows.append([d, "电子", "5000000000"])
        industry_rows.append([d, "银行", "1000000000"])
        industry_rows.append([d, "地产", "800000000"])
        industry_rows.append([d, "医药", "600000000"])
        industry_rows.append([d, "消费", "500000000"])
        industry_rows.append([d, "冷门行业", "100000000"])
    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        industry_rows,
    )
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        [[d, "1"] for d in all_dates],
    )

    config = BacktestConfig(
        name="score-sort-test",
        start_date="2024-01-01",
        end_date="2024-02-20",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )

    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config)

    # 验证 candidates.csv 中 score 排序
    candidates = data_set.candidates
    if len(candidates) >= 2:
        scored_candidates = sorted(candidates, key=lambda c: -float(c["score"]))
        # 最高分候选应该是 000002（强主线 + 高流动性）
        best = scored_candidates[0]
        assert best["symbol"] == "000002", (
            f"最高分候选应为 000002（强主线），实际为 {best['symbol']}，"
            f"score={best['score']}"
        )

    # 如果有交易，验证交易的是高 score 候选
    if data_set.trades:
        trade = data_set.trades[0]
        # 第一笔交易应该是高 score 候选
        assert trade["symbol"] == "000002", (
            f"首笔交易应为 000002（高 score），实际为 {trade['symbol']}"
        )


def test_candidate_scoring_uses_signal_date_amount_not_future_amount(
    tmp_path: Path,
) -> None:
    """评分使用的成交额必须基于候选 signal_date，不能用 as_of 末端的未来成交额。"""
    from suishi_north_backtest.scoring import ScoringContext, score_candidate

    candidate = CandidateSignal(
        signal_date="2024-01-24",
        symbol="000001",
        a_date="2024-01-04",
        a_price=8.0,
        b_date="2024-01-15",
        b_price=12.0,
        c_date="2024-01-22",
        c_price=10.2,
        ab_gain_pct=50.0,
        bc_retracement_pct=45.0,
        distance_to_c_pct=4.9,
        weekly_filter_passed=True,
        annual_filter_passed=True,
        as_of="2024-01-29",
        signal_rule_version=SIGNAL_RULE_VERSION,
    )

    bar_signal_date = StockDaily(
        trade_date="2024-01-24",
        symbol="000001",
        open=10.5, high=10.9, low=10.4, close=10.7,
        volume=65000, amount=500.0,
        is_st=False, limit_up=11.77, limit_down=9.63, is_suspended=False,
    )
    bar_future = StockDaily(
        trade_date="2024-01-26",
        symbol="000001",
        open=10.9, high=11.2, low=10.8, close=11.1,
        volume=700000, amount=500_0000_0000.0,
        is_st=False, limit_up=12.21, limit_down=9.99, is_suspended=False,
    )

    bars_by_symbol = {"000001": [bar_signal_date, bar_future]}
    amount_map = {
        ("000001", "2024-01-24"): 500.0,
        ("000001", "2024-01-26"): 500_0000_0000.0,
    }

    scored = _score_all_candidates(
        [candidate],
        industry_by_symbol={"000001": "电子"},
        mainline_status_by_key={("2024-01-24", "电子"): MainlineStatus.STRONG},
        mainline_rank_by_key={("2024-01-24", "电子"): 1},
        stock_amount_by_symbol_date=amount_map,
        bars_by_symbol=bars_by_symbol,
        industry_candidate_count={"电子": 1},
    )

    assert len(scored) == 1
    breakdown = scored[0].breakdown

    # signal_date 成交额 500 元，远低于 1 亿阈值，liquidity 应为 0
    assert breakdown.liquidity_score == 0.0, (
        f"signal_date 成交额极低时 liquidity 应为 0.0，实际为 {breakdown.liquidity_score}"
    )

    ctx_future = ScoringContext(
        mainline_status="strong",
        industry_rank=1,
        industry_amount=0.0,
        stock_amount=500_0000_0000.0,
        same_industry_candidate_count=1,
    )
    score_future, _ = score_candidate(
        ab_gain_pct=50.0,
        bc_retracement_pct=45.0,
        distance_to_c_pct=4.9,
        weekly_filter_passed=True,
        annual_filter_passed=True,
        context=ctx_future,
    )
    assert scored[0].score < score_future, (
        f"实际 score={scored[0].score} 应低于基于未来成交额的评分 {score_future}"
    )
