"""测试 lifecycle.py 组合交易生命周期深模块。

覆盖 Issue #35 要求的 8 个测试：
- test_lifecycle_t_plus_1_buy
- test_lifecycle_t_plus_1_sell
- test_lifecycle_defer_sell_on_suspension
- test_lifecycle_defer_sell_on_one_word_limit_down
- test_lifecycle_cash_never_negative
- test_lifecycle_daily_mark_to_market
- test_lifecycle_max_holdings
- test_lifecycle_weekly_open_limit
"""
from __future__ import annotations

from suishi_north_backtest.lifecycle import (
    ClosedTrade,
    OpenPosition,
    PortfolioRunConfig,
    PortfolioRunResult,
    bars_by_symbol,
    close_position_if_possible,
    run_portfolio_lifecycle,
)
from suishi_north_backtest.market_data import StockDaily
from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
from suishi_north_backtest.signals import CandidateSignal


def _bar(
    trade_date: str,
    symbol: str = "000001",
    open: float = 10.0,
    high: float = 10.5,
    low: float = 9.5,
    close: float = 10.2,
    volume: float = 50000,
    amount: float = 500000,
    limit_up: float = 11.0,
    limit_down: float = 9.0,
    is_suspended: bool = False,
) -> StockDaily:
    return StockDaily(
        trade_date=trade_date,
        symbol=symbol,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        amount=amount,
        is_st=False,
        limit_up=limit_up,
        limit_down=limit_down,
        is_suspended=is_suspended,
    )


def _candidate(
    signal_date: str = "2024-01-15",
    symbol: str = "000001",
    ab_gain_pct: float = 30.0,
    bc_retracement_pct: float = 30.0,
    distance_to_c_pct: float = 4.0,
    c_price: float = 9.5,
) -> CandidateSignal:
    return CandidateSignal(
        signal_date=signal_date,
        symbol=symbol,
        a_date="2024-01-02",
        a_price=8.0,
        b_date="2024-01-10",
        b_price=10.4,
        c_date="2024-01-13",
        c_price=c_price,
        ab_gain_pct=ab_gain_pct,
        bc_retracement_pct=bc_retracement_pct,
        distance_to_c_pct=distance_to_c_pct,
    )


def _params(**overrides) -> StrategyParameters:
    import dataclasses
    return dataclasses.replace(default_mvp1_parameters(), **overrides)


class TestLifecycleTPlus1Buy:
    """买入在 T+1 开盘执行，不是 T 日收盘。"""

    def test_buy_uses_next_day_open_price(self) -> None:
        candidate = _candidate(signal_date="2024-01-15")
        bars = [
            _bar("2024-01-15", close=10.0),
            _bar("2024-01-16", open=10.5, close=10.8),  # T+1
        ]
        result = run_portfolio_lifecycle(
            scored_candidates=[(candidate, 50.0)],
            bars_by_symbol={"000001": bars},
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=_params(),
        )
        assert len(result.trades) >= 1 or len(result.holdings) > 0, "应有交易或持仓"
        # 买入价应接近 T+1 open=10.5（含滑点），不是 T 日 close=10.0
        if result.trades:
            assert result.trades[0].entry_price > 10.4, (
                f"买入价 {result.trades[0].entry_price} 应基于 T+1 open=10.5"
            )
        else:
            hold = result.holdings[0]
            assert float(hold["cost_basis"]) > 0

    def test_no_bar_after_signal_means_skip(self) -> None:
        candidate = _candidate(signal_date="2024-01-15")
        bars = [
            _bar("2024-01-15", close=10.0),
            # 没有 T+1 行情
        ]
        result = run_portfolio_lifecycle(
            scored_candidates=[(candidate, 50.0)],
            bars_by_symbol={"000001": bars},
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=_params(),
        )
        assert len(result.trades) == 0
        skip_reasons = [s["reason"] for s in result.skipped_trades]
        assert any("T+1" in str(r) or "买入行情" in str(r) for r in skip_reasons)


class TestLifecycleTPlus1Sell:
    """卖出在退出信号 T+1 开盘执行。"""

    def test_sell_on_day_after_exit_signal(self) -> None:
        params = _params(emergency_stop_pct=0.05)
        candidate = _candidate(signal_date="2024-01-10", c_price=9.0)
        bars = [
            _bar("2024-01-10", close=10.0),
            _bar("2024-01-11", open=10.5, close=10.8),  # T+1 买入
            _bar("2024-01-12", open=6.0, high=6.5, low=5.5, close=5.8, amount=580000, limit_down=5.22),  # 应急止损触发
            _bar("2024-01-15", open=5.8, high=6.2, low=5.5, close=5.9, amount=472000, limit_down=5.22),  # T+1 卖出
        ]
        result = run_portfolio_lifecycle(
            scored_candidates=[(candidate, 50.0)],
            bars_by_symbol={"000001": bars},
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=params,
        )
        assert len(result.trades) == 1, f"应有 1 笔平仓交易，实际 {len(result.trades)}"
        trade = result.trades[0]
        # 退出信号在 01-12，卖出在 01-15（T+1）
        assert trade.exit_trigger_date == "2024-01-12"
        assert trade.exit_date == "2024-01-15"


class TestLifecycleDeferSellOnSuspension:
    """停牌时卖出顺延到复牌日。"""

    def test_defer_sell_when_suspended(self) -> None:
        params = _params(emergency_stop_pct=0.05)
        candidate = _candidate(signal_date="2024-01-10", c_price=3.0)
        bars = [
            _bar("2024-01-10", close=10.0),
            _bar("2024-01-11", open=10.5, close=10.8),
            _bar("2024-01-12", open=6.0, high=6.5, low=5.5, close=5.8, amount=580000, limit_down=5.22),  # 触发止损
            _bar("2024-01-15", is_suspended=True),  # 停牌，无法卖出
            _bar("2024-01-16", open=5.7, high=6.0, low=5.4, close=5.8, amount=464000, limit_down=5.22),  # 复牌
            _bar("2024-01-17", open=5.6, high=5.9, low=5.3, close=5.7, amount=456000, limit_down=5.22),  # T+1 卖出
        ]
        result = run_portfolio_lifecycle(
            scored_candidates=[(candidate, 50.0)],
            bars_by_symbol={"000001": bars},
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=params,
        )
        assert len(result.trades) == 1
        trade = result.trades[0]
        # 卖出应顺延到 01-16，不是停牌的 01-15
        # 01-12 触发止损，01-15 停牌跳过，01-16 或 01-17 才能卖出
        assert trade.exit_date in ("2024-01-16", "2024-01-17"), (
            f"停牌日应顺延卖出，实际 exit_date={trade.exit_date}"
        )


class TestLifecycleDeferSellOnOneWordLimitDown:
    """一字跌停时卖出顺延。"""

    def test_defer_sell_on_one_word_limit_down(self) -> None:
        params = _params(emergency_stop_pct=0.05)
        candidate = _candidate(signal_date="2024-01-10", c_price=9.0)
        bars = [
            _bar("2024-01-10", close=10.0),
            _bar("2024-01-11", open=10.5, close=10.8),
            _bar("2024-01-12", open=6.0, high=6.5, low=5.5, close=5.8, amount=580000, limit_down=5.22),  # 触发止损
            _bar("2024-01-15", open=5.22, high=5.22, low=5.22, close=5.22, amount=522000, limit_down=5.22),  # 一字跌停
            _bar("2024-01-16", open=5.5, high=5.8, low=5.3, close=5.6, amount=448000, limit_down=4.70),  # 正常卖出
        ]
        result = run_portfolio_lifecycle(
            scored_candidates=[(candidate, 50.0)],
            bars_by_symbol={"000001": bars},
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=params,
        )
        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.exit_date == "2024-01-16", (
            f"一字跌停应顺延卖出，实际 exit_date={trade.exit_date}"
        )


class TestLifecycleCashNeverNegative:
    """现金永不为负。"""

    def test_cash_never_negative_single_candidate(self) -> None:
        candidate = _candidate(signal_date="2024-01-10")
        bars = [
            _bar("2024-01-10", close=10.0),
            _bar("2024-01-11", open=10.5, close=10.8),
        ]
        result = run_portfolio_lifecycle(
            scored_candidates=[(candidate, 50.0)],
            bars_by_symbol={"000001": bars},
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=_params(),
        )
        for point in result.equity_curve:
            cash = float(point["cash"])
            assert cash >= 0, f"现金为负：{cash}"

    def test_cash_never_negative_multiple_candidates(self) -> None:
        params = _params(max_holdings=5, daily_open_limit=5, weekly_open_limit=5)
        candidates = [
            (_candidate(signal_date="2024-01-10", symbol="000001"), 50.0),
            (_candidate(signal_date="2024-01-10", symbol="000002"), 40.0),
            (_candidate(signal_date="2024-01-10", symbol="000003"), 30.0),
        ]
        bars = {}
        for sym in ["000001", "000002", "000003"]:
            bars[sym] = [
                _bar("2024-01-10", symbol=sym, close=10.0),
                _bar("2024-01-11", symbol=sym, open=10.5, close=10.8),
            ]
        result = run_portfolio_lifecycle(
            scored_candidates=candidates,
            bars_by_symbol=bars,
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=params,
        )
        for point in result.equity_curve:
            assert float(point["cash"]) >= 0


class TestLifecycleDailyMarkToMarket:
    """权益曲线每日盯市。"""

    def test_equity_curve_has_start_and_end(self) -> None:
        candidate = _candidate(signal_date="2024-01-10")
        bars = [
            _bar("2024-01-10", close=10.0),
            _bar("2024-01-11", open=10.5, close=10.8),
        ]
        result = run_portfolio_lifecycle(
            scored_candidates=[(candidate, 50.0)],
            bars_by_symbol={"000001": bars},
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=_params(),
        )
        assert len(result.equity_curve) >= 2
        assert result.equity_curve[0]["date"] == "2024-01-01"
        # 最后一条应该是 end_date 或最终交易日期
        assert result.equity_curve[-1]["date"] >= "2024-01-11"

    def test_equity_includes_track_name(self) -> None:
        candidate = _candidate(signal_date="2024-01-10")
        bars = [
            _bar("2024-01-10", close=10.0),
            _bar("2024-01-11", open=10.5, close=10.8),
        ]
        result = run_portfolio_lifecycle(
            scored_candidates=[(candidate, 50.0)],
            bars_by_symbol={"000001": bars},
            run_config=PortfolioRunConfig(
                track_name="my_track",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=_params(),
        )
        for point in result.equity_curve:
            assert point["track"] == "my_track"


class TestLifecycleMaxHoldings:
    """最大持仓限制。"""

    def test_respects_max_holdings(self) -> None:
        params = _params(max_holdings=2, daily_open_limit=3, weekly_open_limit=5)
        candidates = [
            (_candidate(signal_date="2024-01-10", symbol="000001"), 50.0),
            (_candidate(signal_date="2024-01-10", symbol="000002"), 40.0),
            (_candidate(signal_date="2024-01-10", symbol="000003"), 30.0),
        ]
        bars = {}
        for sym in ["000001", "000002", "000003"]:
            bars[sym] = [
                _bar("2024-01-10", symbol=sym, close=10.0),
                _bar("2024-01-11", symbol=sym, open=10.5, close=10.8),
            ]
        result = run_portfolio_lifecycle(
            scored_candidates=candidates,
            bars_by_symbol=bars,
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=params,
        )
        # 第三只应被跳过（满仓）
        skip_reasons = [str(s.get("reason", "")) for s in result.skipped_trades]
        full_skip = [r for r in skip_reasons if "满仓" in r]
        assert len(full_skip) >= 1, f"应有满仓跳过记录，实际：{skip_reasons}"

    def test_max_holdings_1_only_one_position(self) -> None:
        params = _params(max_holdings=1, daily_open_limit=3, weekly_open_limit=5)
        candidates = [
            (_candidate(signal_date="2024-01-10", symbol="000001"), 50.0),
            (_candidate(signal_date="2024-01-10", symbol="000002"), 40.0),
        ]
        bars = {}
        for sym in ["000001", "000002"]:
            bars[sym] = [
                _bar("2024-01-10", symbol=sym, close=10.0),
                _bar("2024-01-11", symbol=sym, open=10.5, close=10.8),
            ]
        result = run_portfolio_lifecycle(
            scored_candidates=candidates,
            bars_by_symbol=bars,
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=params,
        )
        opened = [t for t in result.trades] + [h for h in result.holdings if h.get("symbol") != "CASH"]
        assert len(opened) <= 1


class TestLifecycleWeeklyOpenLimit:
    """周开仓上限。"""

    def test_respects_weekly_limit(self) -> None:
        params = _params(max_holdings=5, daily_open_limit=5, weekly_open_limit=2)
        candidates = [
            (_candidate(signal_date="2024-01-10", symbol="000001"), 50.0),
            (_candidate(signal_date="2024-01-10", symbol="000002"), 40.0),
            (_candidate(signal_date="2024-01-10", symbol="000003"), 30.0),
        ]
        bars = {}
        for sym in ["000001", "000002", "000003"]:
            bars[sym] = [
                _bar("2024-01-10", symbol=sym, close=10.0),
                _bar("2024-01-11", symbol=sym, open=10.5, close=10.8),
            ]
        result = run_portfolio_lifecycle(
            scored_candidates=candidates,
            bars_by_symbol=bars,
            run_config=PortfolioRunConfig(
                track_name="test",
                initial_cash=1_000_000,
                start_date="2024-01-01",
                end_date="2024-01-20",
            ),
            parameters=params,
        )
        skip_reasons = [str(s.get("reason", "")) for s in result.skipped_trades]
        week_skip = [r for r in skip_reasons if "周开仓上限" in r]
        assert len(week_skip) >= 1, f"应有周上限跳过记录，实际：{skip_reasons}"


class TestClosePositionIfPossible:
    """close_position_if_possible 单元测试。"""

    def test_close_on_emergency_stop(self) -> None:
        params = _params(emergency_stop_pct=0.05)
        position = OpenPosition(
            symbol="000001",
            shares=1000,
            entry_signal_date="2024-01-10",
            entry_date="2024-01-11",
            entry_price=10.7054,
            c_price=3.0,  # 低 C 点，不会触发 structure_stop
            cash_after_entry=9892894.6,
            highest_close_since_entry=10.8,
            commission=32.12,
            slippage=5.35,
        )
        bars = [
            _bar("2024-01-11", close=10.8),
            _bar("2024-01-12", open=6.0, high=6.5, low=5.5, close=5.8, amount=580000, limit_down=5.22),
            _bar("2024-01-15", open=5.8, high=6.2, low=5.5, close=5.9, amount=472000, limit_down=5.22),
        ]
        result = close_position_if_possible(position, bars, params, "test")
        assert result.trade is not None
        assert "emergency_stop" in result.trade.exit_reason

    def test_no_close_when_no_exit_signal(self) -> None:
        params = _params()
        position = OpenPosition(
            symbol="000001",
            shares=1000,
            entry_signal_date="2024-01-10",
            entry_date="2024-01-11",
            entry_price=10.5,
            c_price=9.0,
            cash_after_entry=9895000.0,
            highest_close_since_entry=10.8,
            commission=31.5,
            slippage=5.25,
        )
        bars = [
            _bar("2024-01-11", close=10.8),
            _bar("2024-01-12", close=11.0),
            _bar("2024-01-15", close=11.2),
        ]
        result = close_position_if_possible(position, bars, params, "test")
        assert result.trade is None


class TestBarsBySymbol:
    def test_groups_and_sorts(self) -> None:
        raw = [
            _bar("2024-01-15", symbol="000002"),
            _bar("2024-01-10", symbol="000001"),
            _bar("2024-01-12", symbol="000001"),
        ]
        grouped = bars_by_symbol(raw)
        assert list(grouped.keys()) == ["000002", "000001"]
        assert [b.trade_date for b in grouped["000001"]] == ["2024-01-10", "2024-01-12"]
