"""人工抽样审计工具测试。

验收标准：每个样本必须能回答——
为什么买、为什么卖、是否 T+1、成本如何计入、是否有停牌/一字板影响。
"""

from __future__ import annotations

from pathlib import Path

from suishi_north_backtest.audit import (
    AuditSample,
    run_audit,
    write_audit_csv,
    write_audit_md,
)


# ── 测试 fixture 数据 ─────────────────────────────────────────


def _make_trades() -> list[dict]:
    """创建 6 笔测试交易，覆盖不同轨道、股票和出场原因。"""
    return [
        {
            "trade_id": "FTR-0001",
            "track": "mainline_filtered",
            "symbol": "000001.SZ",
            "entry_signal_date": "2024-01-02",
            "entry_date": "2024-01-03",
            "entry_price": "10.20",
            "entry_shares": "10000",
            "exit_trigger_date": "2024-01-05",
            "exit_date": "2024-01-08",
            "exit_price": "10.80",
            "exit_reason": "trend_exit",
            "commission": "62.99",
            "stamp_tax": "53.98",
            "slippage_cost": "105.00",
            "total_cost": "221.97",
            "gross_pnl": "5905.00",
            "net_pnl": "5683.03",
            "first_target_achieved": "true",
            "audit_note": "T+1 入场，正常趋势出场",
        },
        {
            "trade_id": "FTR-0002",
            "track": "mainline_filtered",
            "symbol": "600036.SH",
            "entry_signal_date": "2024-02-05",
            "entry_date": "2024-02-06",
            "entry_price": "35.50",
            "entry_shares": "3000",
            "exit_trigger_date": "2024-02-20",
            "exit_date": "2024-02-21",
            "exit_price": "34.10",
            "exit_reason": "stop_loss",
            "commission": "21.30",
            "stamp_tax": "30.69",
            "slippage_cost": "35.50",
            "total_cost": "87.49",
            "gross_pnl": "-4200.00",
            "net_pnl": "-4287.49",
            "first_target_achieved": "false",
            "audit_note": "止损出场",
        },
        {
            "trade_id": "FTR-0003",
            "track": "pure_structure",
            "symbol": "300750.SZ",
            "entry_signal_date": "2024-03-10",
            "entry_date": "2024-03-11",
            "entry_price": "180.00",
            "entry_shares": "500",
            "exit_trigger_date": "2024-03-25",
            "exit_date": "2024-03-26",
            "exit_price": "195.00",
            "exit_reason": "trend_exit",
            "commission": "18.75",
            "stamp_tax": "48.75",
            "slippage_cost": "90.00",
            "total_cost": "157.50",
            "gross_pnl": "7500.00",
            "net_pnl": "7342.50",
            "first_target_achieved": "true",
            "audit_note": "",
        },
        {
            "trade_id": "FTR-0004",
            "track": "mainline_filtered",
            "symbol": "002475.SZ",
            "entry_signal_date": "2024-04-15",
            "entry_date": "2024-04-15",
            "entry_price": "25.80",
            "entry_shares": "4000",
            "exit_trigger_date": "2024-04-28",
            "exit_date": "2024-04-29",
            "exit_price": "27.50",
            "exit_reason": "take_profit",
            "commission": "21.32",
            "stamp_tax": "44.00",
            "slippage_cost": "51.60",
            "total_cost": "116.92",
            "gross_pnl": "6800.00",
            "net_pnl": "6683.08",
            "first_target_achieved": "true",
            "audit_note": "同日入场，非 T+1",
        },
        {
            "trade_id": "FTR-0005",
            "track": "mainline_filtered",
            "symbol": "601318.SH",
            "entry_signal_date": "2024-05-06",
            "entry_date": "2024-05-07",
            "entry_price": "42.30",
            "entry_shares": "2000",
            "exit_trigger_date": "2024-05-20",
            "exit_date": "2024-05-21",
            "exit_price": "41.00",
            "exit_reason": "trailing_stop",
            "commission": "16.60",
            "stamp_tax": "32.80",
            "slippage_cost": "42.30",
            "total_cost": "91.70",
            "gross_pnl": "-2600.00",
            "net_pnl": "-2691.70",
            "first_target_achieved": "false",
            "audit_note": "追踪止损出场",
        },
        {
            "trade_id": "FTR-0006",
            "track": "pure_structure",
            "symbol": "000858.SZ",
            "entry_signal_date": "2024-06-03",
            "entry_date": "2024-06-04",
            "entry_price": "150.00",
            "entry_shares": "700",
            "exit_trigger_date": "2024-06-18",
            "exit_date": "2024-06-19",
            "exit_price": "162.00",
            "exit_reason": "trend_exit",
            "commission": "32.76",
            "stamp_tax": "56.70",
            "slippage_cost": "70.00",
            "total_cost": "159.46",
            "gross_pnl": "8400.00",
            "net_pnl": "8240.54",
            "first_target_achieved": "true",
            "audit_note": "",
        },
    ]


def _make_candidates() -> list[dict]:
    """创建与测试交易匹配的候选信号。"""
    return [
        {
            "signal_date": "2024-01-02",
            "track": "mainline_filtered",
            "symbol": "000001.SZ",
            "industry_level2": "bank",
            "is_strong_mainline": "true",
            "a_date": "2023-12-20",
            "a_price": "8.00",
            "b_date": "2023-12-28",
            "b_price": "10.40",
            "c_date": "2024-01-02",
            "c_price": "9.60",
            "ab_gain_pct": "30.00",
            "bc_retracement_pct": "33.33",
            "distance_to_c_low_pct": "4.17",
            "weekly_filter_passed": "true",
            "annual_filter_passed": "true",
            "failure_reason": "",
            "as_of": "2024-01-02",
            "signal_rule_version": "MVP1-SIGNAL-AUDIT-v1",
            "score": "60.90",
            "score_breakdown": "mainline=20.0; total=60.9",
            "audit_note": "fixture candidate",
        },
        {
            "signal_date": "2024-02-05",
            "track": "mainline_filtered",
            "symbol": "600036.SH",
            "industry_level2": "bank",
            "is_strong_mainline": "true",
            "a_date": "2024-01-15",
            "a_price": "32.00",
            "b_date": "2024-01-22",
            "b_price": "38.50",
            "c_date": "2024-02-05",
            "c_price": "35.00",
            "ab_gain_pct": "20.31",
            "bc_retracement_pct": "50.00",
            "distance_to_c_low_pct": "1.43",
            "weekly_filter_passed": "true",
            "annual_filter_passed": "true",
            "failure_reason": "",
            "as_of": "2024-02-05",
            "signal_rule_version": "MVP1-SIGNAL-AUDIT-v1",
            "score": "55.00",
            "score_breakdown": "mainline=20.0; total=55.0",
            "audit_note": "",
        },
        {
            "signal_date": "2024-03-10",
            "track": "pure_structure",
            "symbol": "300750.SZ",
            "industry_level2": "battery",
            "is_strong_mainline": "false",
            "a_date": "2024-02-01",
            "a_price": "160.00",
            "b_date": "2024-02-20",
            "b_price": "195.00",
            "c_date": "2024-03-10",
            "c_price": "178.00",
            "ab_gain_pct": "21.88",
            "bc_retracement_pct": "48.57",
            "distance_to_c_low_pct": "1.12",
            "weekly_filter_passed": "true",
            "annual_filter_passed": "false",
            "failure_reason": "",
            "as_of": "2024-03-10",
            "signal_rule_version": "MVP1-SIGNAL-AUDIT-v1",
            "score": "45.00",
            "score_breakdown": "total=45.0",
            "audit_note": "",
        },
        {
            "signal_date": "2024-04-15",
            "track": "mainline_filtered",
            "symbol": "002475.SZ",
            "industry_level2": "electronics",
            "is_strong_mainline": "true",
            "a_date": "2024-03-20",
            "a_price": "22.00",
            "b_date": "2024-04-05",
            "b_price": "28.00",
            "c_date": "2024-04-15",
            "c_price": "25.50",
            "ab_gain_pct": "27.27",
            "bc_retracement_pct": "41.67",
            "distance_to_c_low_pct": "1.18",
            "weekly_filter_passed": "true",
            "annual_filter_passed": "true",
            "failure_reason": "",
            "as_of": "2024-04-15",
            "signal_rule_version": "MVP1-SIGNAL-AUDIT-v1",
            "score": "58.00",
            "score_breakdown": "mainline=20.0; total=58.0",
            "audit_note": "",
        },
        {
            "signal_date": "2024-05-06",
            "track": "mainline_filtered",
            "symbol": "601318.SH",
            "industry_level2": "insurance",
            "is_strong_mainline": "true",
            "a_date": "2024-04-10",
            "a_price": "40.00",
            "b_date": "2024-04-22",
            "b_price": "46.00",
            "c_date": "2024-05-06",
            "c_price": "42.50",
            "ab_gain_pct": "15.00",
            "bc_retracement_pct": "58.33",
            "distance_to_c_low_pct": "0.47",
            "weekly_filter_passed": "false",
            "annual_filter_passed": "true",
            "failure_reason": "",
            "as_of": "2024-05-06",
            "signal_rule_version": "MVP1-SIGNAL-AUDIT-v1",
            "score": "40.00",
            "score_breakdown": "mainline=20.0; total=40.0",
            "audit_note": "",
        },
        {
            "signal_date": "2024-06-03",
            "track": "pure_structure",
            "symbol": "000858.SZ",
            "industry_level2": "liquor",
            "is_strong_mainline": "false",
            "a_date": "2024-05-10",
            "a_price": "140.00",
            "b_date": "2024-05-20",
            "b_price": "158.00",
            "c_date": "2024-06-03",
            "c_price": "148.00",
            "ab_gain_pct": "12.86",
            "bc_retracement_pct": "55.56",
            "distance_to_c_low_pct": "1.35",
            "weekly_filter_passed": "true",
            "annual_filter_passed": "true",
            "failure_reason": "",
            "as_of": "2024-06-03",
            "signal_rule_version": "MVP1-SIGNAL-AUDIT-v1",
            "score": "42.00",
            "score_breakdown": "total=42.0",
            "audit_note": "",
        },
    ]


# ── 必需测试 ───────────────────────────────────────────────────


def test_audit_sample_links_trade_to_candidate() -> None:
    """每个审计样本能关联到对应的候选信号。"""
    trades = _make_trades()
    candidates = _make_candidates()
    samples = run_audit(trades, candidates, sample_size=len(trades), seed=1)

    assert len(samples) == len(trades)
    for sample in samples:
        assert sample.candidate_matched, (
            f"交易 {sample.trade_id} ({sample.symbol}) 未能关联到候选信号"
        )
        # 验证关联字段一致性：trade 的轨道和股票与 candidate 匹配
        matching_trade = next(t for t in trades if t["trade_id"] == sample.trade_id)
        matching_cand = next(
            c
            for c in candidates
            if c["signal_date"] == matching_trade["entry_signal_date"]
            and c["track"] == matching_trade["track"]
            and c["symbol"] == matching_trade["symbol"]
        )
        assert sample.score == matching_cand["score"]
        assert sample.ab_gain_pct == matching_cand["ab_gain_pct"]


def test_audit_sample_contains_entry_signal() -> None:
    """每个样本包含入场原因（entry_signal），回答"为什么买"。"""
    trades = _make_trades()
    candidates = _make_candidates()
    samples = run_audit(trades, candidates, sample_size=len(trades), seed=1)

    for sample in samples:
        assert sample.entry_signal, f"交易 {sample.trade_id} 缺少入场信号描述"
        # 有候选匹配的样本应包含关键信息
        if sample.candidate_matched:
            assert "评分=" in sample.entry_signal, (
                f"交易 {sample.trade_id} 入场信号缺少评分"
            )


def test_audit_sample_contains_exit_reason() -> None:
    """每个样本包含出场原因，回答"为什么卖"。"""
    trades = _make_trades()
    candidates = _make_candidates()
    samples = run_audit(trades, candidates, sample_size=len(trades), seed=1)

    exit_reasons = {"trend_exit", "stop_loss", "take_profit", "trailing_stop"}
    for sample in samples:
        assert sample.exit_reason, f"交易 {sample.trade_id} 缺少出场原因"
        assert sample.exit_reason in exit_reasons, (
            f"交易 {sample.trade_id} 出场原因 '{sample.exit_reason}' 不在预期集合中"
        )


def test_audit_sample_contains_cost_breakdown() -> None:
    """每个样本包含成本明细，回答"成本如何计入"。"""
    trades = _make_trades()
    candidates = _make_candidates()
    samples = run_audit(trades, candidates, sample_size=len(trades), seed=1)

    for sample in samples:
        # 所有成本字段应非空且可解析为浮点数
        assert sample.commission, f"交易 {sample.trade_id} 缺少佣金"
        assert sample.stamp_tax, f"交易 {sample.trade_id} 缺少印花税"
        assert sample.slippage_cost, f"交易 {sample.trade_id} 缺少滑点成本"
        assert sample.total_cost, f"交易 {sample.trade_id} 缺少总成本"

        commission = float(sample.commission)
        stamp_tax = float(sample.stamp_tax)
        slippage = float(sample.slippage_cost)
        total = float(sample.total_cost)

        # 总成本应接近各分项之和
        assert abs(total - (commission + stamp_tax + slippage)) < 1.0, (
            f"交易 {sample.trade_id} 成本分项之和与总成本不符: "
            f"{commission}+{stamp_tax}+{slippage} != {total}"
        )

        gross = float(sample.gross_pnl)
        net = float(sample.net_pnl)
        assert abs(net - (gross - total)) < 1.0, (
            f"交易 {sample.trade_id} 净利润 != 毛利润 - 总成本: "
            f"{net} != {gross} - {total}"
        )


def test_audit_sample_is_deterministic_with_seed() -> None:
    """相同 seed 产生相同的审计样本，保证确定性。"""
    trades = _make_trades()
    candidates = _make_candidates()

    run1 = run_audit(trades, candidates, sample_size=4, seed=42)
    run2 = run_audit(trades, candidates, sample_size=4, seed=42)

    assert len(run1) == len(run2)
    for s1, s2 in zip(run1, run2):
        assert s1.trade_id == s2.trade_id
        assert s1 == s2, f"seed=42 的两次运行结果不一致: {s1.trade_id}"

    # 不同 seed 应产生不同的样本（至少顺序不同）
    run3 = run_audit(trades, candidates, sample_size=4, seed=99)
    trade_ids_42 = [s.trade_id for s in run1]
    trade_ids_99 = [s.trade_id for s in run3]
    assert trade_ids_42 != trade_ids_99, "不同 seed 应产生不同的抽样结果"


# ── 补充测试 ───────────────────────────────────────────────────


def test_audit_t_plus_1_detection() -> None:
    """正确识别 T+1 入场。"""
    trades = _make_trades()
    candidates = _make_candidates()
    samples = run_audit(trades, candidates, sample_size=len(trades), seed=1)

    # FTR-0004: entry_signal_date == entry_date → 非 T+1
    sample_0004 = next(s for s in samples if s.trade_id == "FTR-0004")
    assert not sample_0004.is_t_plus_1

    # FTR-0001: entry_signal_date < entry_date → T+1
    sample_0001 = next(s for s in samples if s.trade_id == "FTR-0001")
    assert sample_0001.is_t_plus_1


def test_audit_handles_no_match() -> None:
    """交易无匹配候选时，标记为未匹配但仍然产出样本。"""
    trades = _make_trades()[:1]  # 只取一笔
    candidates = []  # 无候选数据
    samples = run_audit(trades, candidates, sample_size=10, seed=1)

    assert len(samples) == 1
    assert not samples[0].candidate_matched
    assert samples[0].entry_signal == "无匹配候选信号"


def test_audit_sample_size_clamps_to_available() -> None:
    """sample_size 超过交易数时，抽样全部交易。"""
    trades = _make_trades()
    candidates = _make_candidates()
    samples = run_audit(trades, candidates, sample_size=100, seed=1)

    assert len(samples) == len(trades)


def test_audit_empty_trades() -> None:
    """无交易时返回空列表。"""
    samples = run_audit([], [], sample_size=10, seed=1)
    assert samples == []


def test_write_audit_csv_roundtrip(tmp_path: Path) -> None:
    """CSV 输出可被读回，字段完整。"""
    trades = _make_trades()
    candidates = _make_candidates()
    samples = run_audit(trades, candidates, sample_size=3, seed=42)

    csv_path = write_audit_csv(samples, tmp_path)
    assert csv_path.exists()
    assert csv_path.name == "audit_samples.csv"

    import csv

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 3
    for row in rows:
        assert "trade_id" in row
        assert "exit_reason" in row
        assert "commission" in row
        assert "is_t_plus_1" in row
        assert "entry_signal" in row
        assert row["candidate_matched"] in ("True", "False")


def test_write_audit_md_contains_key_sections(tmp_path: Path) -> None:
    """Markdown 报告包含关键章节。"""
    trades = _make_trades()
    candidates = _make_candidates()
    samples = run_audit(trades, candidates, sample_size=2, seed=42)

    md_path = write_audit_md(samples, tmp_path)
    assert md_path.exists()
    assert md_path.name == "audit_samples.md"

    content = md_path.read_text(encoding="utf-8")
    assert "# 人工抽样审计报告" in content
    assert "成本明细" in content
    assert "入场原因" in content
    assert "出场原因" in content
    assert "T+1" in content
    assert "候选信号详情" in content


def test_audit_with_fixture_data_provider() -> None:
    """使用 FixtureDataProvider 数据验证审计端到端。"""
    from suishi_north_backtest.config import BacktestConfig
    from suishi_north_backtest.data import FixtureDataProvider

    config = BacktestConfig()
    provider = FixtureDataProvider()
    data_set = provider.load(config)

    samples = run_audit(
        data_set.trades,
        data_set.candidates,
        sample_size=10,
        seed=42,
    )

    assert len(samples) == 1  # fixture 只有 1 笔交易
    sample = samples[0]
    assert sample.trade_id == "FTR-0001"
    assert sample.symbol == "000001.SZ"
    assert sample.exit_reason == "trend_exit"
    assert sample.candidate_matched
    assert sample.is_t_plus_1  # 信号 01-02, 入场 01-03
    assert float(sample.total_cost) > 0
