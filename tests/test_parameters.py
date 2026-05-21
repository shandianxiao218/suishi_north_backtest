"""StrategyParameters 测试：参数集定义、模块接入、runner 记录。"""
from __future__ import annotations

from dataclasses import replace

from suishi_north_backtest.execution import execute_buy, execute_sell
from suishi_north_backtest.exits import detect_exit_signal
from suishi_north_backtest.mainline import compute_mainlines
from suishi_north_backtest.market_data import IndustryDailyAmount, StockDaily
from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
from suishi_north_backtest.portfolio import select_candidates
from suishi_north_backtest.signals import CandidateSignal, find_candidates


def test_default_mvp1_parameters_match_adr_0002() -> None:
    p = default_mvp1_parameters()
    assert p.name == "ADR-0002-defaults"
    assert p.ab_min_gain_pct == 0.20
    assert p.bc_max_retracement_pct == 0.60
    assert p.c_window_min_days == 3
    assert p.c_window_max_days == 20
    assert p.signal_distance_to_c_max_pct == 0.08
    assert p.mainline_top_n == 5
    assert p.strong_mainline_days == 3
    assert p.observation_window_days == 5
    assert p.observation_min_count == 3
    assert p.max_holdings == 3
    assert p.daily_open_limit == 1
    assert p.weekly_open_limit == 2
    assert p.risk_pct == 0.01
    assert p.commission_rate == 0.0003
    assert p.stamp_tax_rate == 0.0005
    assert p.buy_slippage_rate == 0.0005
    assert p.sell_slippage_rate == 0.0005
    assert p.lot_size == 100
    assert p.trend_exit_pct == 0.08
    assert p.max_holding_days == 30


def test_default_parameters_to_metadata() -> None:
    p = default_mvp1_parameters()
    m = p.to_metadata()
    assert m["name"] == "ADR-0002-defaults"
    assert m["ab_min_gain_pct"] == 0.20
    assert "risk_pct" in m


def test_signals_pct_conversion_properties() -> None:
    p = default_mvp1_parameters()
    assert p.ab_min_gain_pct_for_signals == 20.0
    assert p.bc_max_retracement_pct_for_signals == 60.0
    assert p.signal_distance_to_c_max_pct_for_signals == 8.0


def test_find_candidates_uses_strategy_parameters() -> None:
    """默认 20% 产生候选，55% 不产生（AB gain=50%）。"""
    bars = _make_abc_bars()
    default_params = default_mvp1_parameters()
    candidates_default = find_candidates(bars, as_of="2024-02-01", parameters=default_params)
    assert len(candidates_default) > 0

    strict_params = replace(default_mvp1_parameters(), ab_min_gain_pct=0.55)
    candidates_strict = find_candidates(bars, as_of="2024-02-01", parameters=strict_params)
    assert len(candidates_strict) == 0


def test_compute_mainlines_uses_strategy_parameters() -> None:
    """2 天连续 top-1：默认 3 天不强，strong_days=2 则强。"""
    data = _make_mainline_data(days=2)
    default_params = default_mvp1_parameters()
    result_default = compute_mainlines(data, as_of="2024-01-10", parameters=default_params)
    strong_default = [
        e for e in result_default
        if e.industry_level2 == "电子" and e.status.value == "strong"
    ]
    assert len(strong_default) == 0

    relaxed_params = replace(default_mvp1_parameters(), strong_mainline_days=2)
    result_relaxed = compute_mainlines(data, as_of="2024-01-10", parameters=relaxed_params)
    strong_relaxed = [
        e for e in result_relaxed
        if e.industry_level2 == "电子" and e.status.value == "strong"
    ]
    assert len(strong_relaxed) > 0


def test_select_candidates_uses_strategy_parameters() -> None:
    """max_holdings=1 且已满 -> 跳过；max_holdings=3 -> 可开仓。"""
    candidate = _make_candidate("000001")
    default_params = default_mvp1_parameters()

    actions_full = select_candidates(
        candidates=[candidate],
        current_holdings=["600000", "000002"],
        opened_today=0,
        opened_this_week=0,
        parameters=replace(default_params, max_holdings=2),
    )
    assert all(a.action == "skip" for a in actions_full)

    actions_open = select_candidates(
        candidates=[candidate],
        current_holdings=["600000", "000002"],
        opened_today=0,
        opened_this_week=0,
        parameters=replace(default_params, max_holdings=3),
    )
    assert any(a.action == "open" for a in actions_open)


def test_execute_buy_uses_strategy_parameters() -> None:
    """不同 risk_pct 和 commission_rate 影响 shares 和 cash。"""
    candidate = _make_candidate("000001")
    default_params = default_mvp1_parameters()

    buy_default = execute_buy(
        candidate=candidate, open_price=10.0, cash=1_000_000, equity=1_000_000,
        parameters=default_params,
    )
    assert buy_default.executed

    buy_high_risk = execute_buy(
        candidate=candidate, open_price=10.0, cash=1_000_000, equity=1_000_000,
        parameters=replace(default_params, risk_pct=0.02),
    )
    assert buy_high_risk.executed
    assert buy_high_risk.shares > buy_default.shares

    buy_double_commission = execute_buy(
        candidate=candidate, open_price=10.0, cash=1_000_000, equity=1_000_000,
        parameters=replace(default_params, commission_rate=0.001),
    )
    assert buy_double_commission.executed
    assert buy_double_commission.commission > buy_default.commission


def test_detect_exit_signal_uses_strategy_parameters() -> None:
    """trend_exit_pct 影响趋势退出触发。"""
    bars = [
        _make_bar("2024-01-10", close=10.0),
    ]
    # 关闭时间止损以避免干扰趋势退出测试
    no_time_stop = replace(default_mvp1_parameters(), time_stop_days=999)

    # entry=10.0, highest=11.0, close=10.0 -> 回撤 (11-10)/11 = 9.1% > 8%
    signal_default = detect_exit_signal(
        bars=bars,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=11.0,
        entry_date="2024-01-05",
        current_date="2024-01-10",
        trading_days_since_entry=5,
        parameters=no_time_stop,
    )
    assert signal_default is not None
    assert signal_default.exit_type.value == "trend_exit"

    signal_loose = detect_exit_signal(
        bars=bars,
        entry_price=10.0,
        c_price=9.0,
        highest_close_since_entry=11.0,
        entry_date="2024-01-05",
        current_date="2024-01-10",
        trading_days_since_entry=5,
        parameters=replace(no_time_stop, trend_exit_pct=0.15),
    )
    assert signal_loose is None


def test_mvp1_runner_records_strategy_parameters(tmp_path) -> None:
    """runner 传入自定义参数时，data_set 记录参数名和 metadata。"""
    from suishi_north_backtest.config import BacktestConfig
    from suishi_north_backtest.mvp1_runner import run_mvp1_from_raw_snapshot
    from tests.test_mvp1_runner import _build_raw_snapshot

    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_raw_snapshot(snapshot_dir)

    config = BacktestConfig(
        name="param-test",
        start_date="2024-01-01",
        end_date="2024-02-20",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )
    custom = replace(default_mvp1_parameters(), name="test-params", ab_min_gain_pct=0.25)
    data_set = run_mvp1_from_raw_snapshot(snapshot_dir, config, parameters=custom)

    assert data_set.parameter_set == "test-params"
    assert data_set.metrics["parameters"]["name"] == "test-params"
    assert data_set.metrics["parameters"]["ab_min_gain_pct"] == 0.25


# ---- helpers ----

def _make_abc_bars() -> list[StockDaily]:
    """构造 A=8.0 -> B=12.0 (gain=50%) -> C=10.2 的日线数据。"""
    rows = [
        ("2024-01-02", 9.5, 9.8, 9.0, 9.5),
        ("2024-01-03", 9.2, 9.5, 8.8, 9.0),
        ("2024-01-04", 8.8, 9.0, 7.9, 8.0),
        ("2024-01-05", 8.3, 9.0, 8.1, 8.8),
        ("2024-01-08", 9.0, 9.8, 8.9, 9.6),
        ("2024-01-09", 9.8, 10.5, 9.7, 10.3),
        ("2024-01-10", 10.5, 11.0, 10.2, 10.8),
        ("2024-01-11", 10.9, 11.5, 10.8, 11.3),
        ("2024-01-12", 11.5, 12.2, 11.3, 11.8),
        ("2024-01-15", 12.0, 12.8, 11.8, 12.0),
        ("2024-01-16", 11.8, 12.0, 11.2, 11.5),
        ("2024-01-17", 11.3, 11.5, 10.8, 11.0),
        ("2024-01-18", 10.8, 11.2, 10.5, 10.8),
        ("2024-01-19", 10.5, 10.8, 10.2, 10.5),
        ("2024-01-22", 10.3, 10.6, 10.0, 10.2),
        ("2024-01-23", 10.2, 10.8, 10.1, 10.5),
        ("2024-01-24", 10.5, 10.9, 10.4, 10.7),
        ("2024-01-25", 10.7, 11.0, 10.6, 10.9),
        ("2024-01-26", 10.9, 11.2, 10.8, 11.1),
        ("2024-01-29", 11.1, 11.4, 11.0, 11.3),
    ]
    return [
        StockDaily(
            trade_date=d, symbol="000001", open=o, high=h, low=l, close=c,
            volume=50000, amount=500000, is_st=False,
            limit_up=round(c * 1.1, 2), limit_down=round(c * 0.9, 2),
            is_suspended=False,
        )
        for d, o, h, l, c in rows
    ]


def _make_mainline_data(days: int = 3) -> list[IndustryDailyAmount]:
    """构造数据：电子行业只在最后 days 天排名第1进入 top-5。"""
    total_days = days + 3
    data: list[IndustryDailyAmount] = []
    for i in range(total_days):
        d = f"2024-01-{i + 2:02d}"
        # 电子只在最后 days 天进入 top-5（金额最高）
        if i >= total_days - days:
            data.append(IndustryDailyAmount(trade_date=d, industry_level2="电子", amount=5_000_000_000))
        else:
            data.append(IndustryDailyAmount(trade_date=d, industry_level2="电子", amount=100_000_000))
        data.append(IndustryDailyAmount(trade_date=d, industry_level2="银行", amount=1_000_000_000))
        data.append(IndustryDailyAmount(trade_date=d, industry_level2="地产", amount=800_000_000))
        data.append(IndustryDailyAmount(trade_date=d, industry_level2="医药", amount=600_000_000))
        data.append(IndustryDailyAmount(trade_date=d, industry_level2="消费", amount=500_000_000))
        data.append(IndustryDailyAmount(trade_date=d, industry_level2="科技", amount=400_000_000))
    return data


def _make_candidate(symbol: str) -> CandidateSignal:
    return CandidateSignal(
        signal_date="2024-01-24",
        symbol=symbol,
        a_date="2024-01-04",
        a_price=8.0,
        b_date="2024-01-15",
        b_price=12.0,
        c_date="2024-01-22",
        c_price=10.2,
        ab_gain_pct=50.0,
        bc_retracement_pct=45.0,
        distance_to_c_pct=4.9,
    )


def _make_bar(trade_date: str, close: float) -> StockDaily:
    return StockDaily(
        trade_date=trade_date, symbol="000001",
        open=close, high=close + 0.1, low=close - 0.1, close=close,
        volume=50000, amount=500000, is_st=False,
        limit_up=round(close * 1.1, 2), limit_down=round(close * 0.9, 2),
        is_suspended=False,
    )
