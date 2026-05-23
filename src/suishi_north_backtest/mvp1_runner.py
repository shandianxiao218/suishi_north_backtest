from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.data import Mvp1DataSet
from suishi_north_backtest.execution import execute_buy, execute_sell
from suishi_north_backtest.exits import detect_exit_signal
from suishi_north_backtest.mainline import MainlineStatus, compute_mainlines
from suishi_north_backtest.market_data import MarketData, StockDaily, load_market_data
from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
from suishi_north_backtest.portfolio import PortfolioAction, select_candidates
from suishi_north_backtest.raw_data import validate_raw_snapshot
from suishi_north_backtest.signals import CandidateSignal, find_candidates
from suishi_north_backtest.tracks import Track, build_mainline_map


@dataclass(frozen=True)
class OpenPosition:
    symbol: str
    shares: int
    entry_signal_date: str
    entry_date: str
    entry_price: float
    c_price: float
    cash_after_entry: float
    highest_close_since_entry: float
    commission: float
    slippage: float


@dataclass(frozen=True)
class ClosedTrade:
    trade_id: str
    symbol: str
    entry_signal_date: str
    entry_date: str
    entry_price: float
    entry_shares: int
    exit_trigger_date: str
    exit_date: str
    exit_price: float
    exit_reason: str
    commission: float
    stamp_tax: float
    slippage_cost: float
    total_cost: float
    gross_pnl: float
    net_pnl: float
    sell_cash_proceeds: float


BENCHMARK_CODE_TO_NAME = {
    "000300": "CSI300",
    "000905": "CSI500",
    "000852": "CSI1000",
    "CSI300": "CSI300",
    "CSI500": "CSI500",
    "CSI1000": "CSI1000",
}
REQUIRED_BENCHMARKS = ["CSI300", "CSI500", "CSI1000"]
REQUIRED_PERIODS = ["sample_in", "sample_out", "recent"]


def run_mvp1_from_raw_snapshot(
    raw_snapshot_dir: Path,
    config: BacktestConfig,
    parameters: StrategyParameters | None = None,
) -> Mvp1DataSet:
    """从 raw a-stock-data 快照生成 MVP-1 统一数据集。

    该 Module 收拢生产链路：raw snapshot -> 标准行情 -> 股票池 -> 主线 ->
    候选 -> 组合约束 -> T+1 买入 -> 退出信号 -> T+1 卖出 -> Mvp1DataSet。
    它不负责写文件；文件输出仍由 engine 处理。
    """

    parameters = parameters or default_mvp1_parameters()
    raw_snapshot_dir = Path(raw_snapshot_dir)
    manifest = validate_raw_snapshot(raw_snapshot_dir)
    market_data = load_market_data(raw_snapshot_dir, manifest)

    as_of = config.end_date
    universe_entries, tradability_audit = _filter_as_of_universe(market_data, as_of, parameters)
    tradable_symbols_by_date = {
        (entry.trade_date, entry.symbol) for entry in universe_entries
    }
    industry_by_symbol = {entry.symbol: entry.industry_level2 for entry in universe_entries}

    # 股票池排除审计写入 skipped_trades
    universe_skip_rows: list[dict[str, object]] = []
    for a in tradability_audit:
        if a.buy_restricted or a.sell_deferred:
            continue  # 可交易性审计在轨道级别处理，不写入 universe_skip
        universe_skip_rows.append({
            "signal_date": a.trade_date,
            "track": "universe_filter",
            "symbol": a.symbol,
            "reason": a.reason,
        })

    mainlines = compute_mainlines(market_data.industry_daily_amount, as_of=as_of, parameters=parameters)
    mainline_status_by_key = {
        (entry.trade_date, entry.industry_level2): entry.status for entry in mainlines
    }
    mainline_rank_by_key = {
        (entry.trade_date, entry.industry_level2): entry.rank for entry in mainlines
    }

    candidates = _filter_candidates(
        find_candidates(market_data.stock_daily, as_of=as_of, parameters=parameters),
        tradable_symbols_by_date,
    )
    candidate_rows = _candidate_rows(
        candidates,
        industry_by_symbol,
        mainline_status_by_key,
        mainline_rank_by_key,
    )

    # 构建主线映射，用于双轨过滤
    mainline_entries = compute_mainlines(market_data.industry_daily_amount, as_of=as_of, parameters=parameters)
    mainline_map = build_mainline_map(mainline_entries)

    # 双轨独立模拟
    all_trades: list[ClosedTrade] = []
    all_holdings: list[dict[str, object]] = []
    all_skipped: list[dict[str, object]] = []
    all_equity: list[dict[str, object]] = []

    for track_name in ["pure_structure", "mainline_filtered"]:
        trades, holdings, skipped_rows, equity_points = _simulate_portfolio_for_track(
            candidates=candidates,
            market_data=market_data,
            config=config,
            parameters=parameters,
            track_name=track_name,
            mainline_map=mainline_map,
            industry_by_symbol=industry_by_symbol,
        )
        all_trades.extend(trades)
        all_holdings.extend(holdings)
        all_skipped.extend(skipped_rows)
        all_equity.extend(equity_points)

    # 股票池排除审计追加到 skipped_trades
    all_skipped.extend(universe_skip_rows)

    # 合并两条轨道的净值曲线（按日期排序）
    all_equity.sort(key=lambda p: str(p.get("date", "")))

    # 各轨道独立指标
    ps_trades = [t for t in all_trades if t.trade_id.startswith("PURE")]
    mf_trades = [t for t in all_trades if t.trade_id.startswith("MAIN")]
    ps_equity = [p for p in all_equity if p.get("track") == "pure_structure"]
    mf_equity = [p for p in all_equity if p.get("track") == "mainline_filtered"]

    ps_return = _safe_pct_change(
        float(config.initial_cash),
        float(ps_equity[-1]["equity"]) if ps_equity else float(config.initial_cash),
    )
    mf_return = _safe_pct_change(
        float(config.initial_cash),
        float(mf_equity[-1]["equity"]) if mf_equity else float(config.initial_cash),
    )

    # 主口径：以 mainline_filtered 作为默认主策略
    primary_equity = mf_equity if mf_equity else ps_equity
    ending_equity = float(primary_equity[-1]["equity"]) if primary_equity else float(config.initial_cash)
    total_return = _safe_pct_change(config.initial_cash, ending_equity)
    primary_drawdown_values = [float(p["equity"]) for p in primary_equity]
    max_drawdown = _max_drawdown(primary_drawdown_values)
    win_rate = _win_rate(all_trades)
    profit_factor = _profit_factor(all_trades)

    metrics = {
        "name": config.name,
        "initial_cash": config.initial_cash,
        "ending_equity": round(ending_equity, 2),
        "total_return": round(total_return, 6),
        "max_drawdown": round(max_drawdown, 6),
        "profit_factor": round(profit_factor, 6),
        "win_rate": round(win_rate, 6),
        "trade_count": len(all_trades),
        "candidate_count": len(candidates),
        "skipped_count": len(all_skipped),
        "primary_track": "mainline_filtered",
        "tracks": {
            "pure_structure": {
                "trade_count": len(ps_trades),
                "total_return": round(ps_return, 6),
            },
            "mainline_filtered": {
                "trade_count": len(mf_trades),
                "total_return": round(mf_return, 6),
            },
        },
        "benchmarks": REQUIRED_BENCHMARKS,
        "sample_windows": {
            "sample_in": ["2018-01-01", "2022-12-31"],
            "sample_out": ["2023-01-01", as_of],
            "recent": ["2024-01-01", as_of],
        },
        "audit_note": "raw snapshot generated MVP-1 dataset with real dual-track",
        "parameters": parameters.to_metadata(),
    }

    return Mvp1DataSet(
        data_version=manifest.data_version,
        parameter_set=parameters.name,
        universe=f"raw-a-stock-data-universe-{len({entry.symbol for entry in universe_entries})}",
        equity_curve=all_equity,
        trades=_trade_rows(all_trades),
        skipped_trades=all_skipped,
        candidates=candidate_rows,
        holdings=all_holdings,
        benchmark_comparison=_benchmark_rows(
            market_data=market_data,
            strategy_return=total_return,
            max_drawdown=max_drawdown,
        ),
        track_comparison=_real_track_rows(ps_trades, ps_return, mf_trades, mf_return),
        sensitivity=_sensitivity_rows(total_return),
        metrics=metrics,
    )


def _filter_as_of_universe(
    market_data: MarketData,
    as_of: str,
    parameters: StrategyParameters | None = None,
) -> tuple[list, list]:
    """返回 (universe_entries, tradability_audit)。"""
    from suishi_north_backtest.universe import build_universe_with_audit

    min_amount = parameters.min_daily_amount if parameters else 0.0
    long_suspension_days = parameters.long_suspension_days if parameters else 0
    return build_universe_with_audit(
        market_data,
        as_of=as_of,
        min_amount=min_amount,
        long_suspension_days=long_suspension_days,
    )


def _filter_candidates(
    candidates: list[CandidateSignal],
    tradable_symbols_by_date: set[tuple[str, str]],
) -> list[CandidateSignal]:
    return [
        candidate
        for candidate in candidates
        if (candidate.signal_date, candidate.symbol) in tradable_symbols_by_date
    ]


def _candidate_rows(
    candidates: list[CandidateSignal],
    industry_by_symbol: dict[str, str],
    mainline_status_by_key: dict[tuple[str, str], MainlineStatus],
    mainline_rank_by_key: dict[tuple[str, str], int],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        industry = industry_by_symbol.get(candidate.symbol, "")
        status = mainline_status_by_key.get(
            (candidate.signal_date, industry), MainlineStatus.NONE
        )
        rank = mainline_rank_by_key.get((candidate.signal_date, industry), 0)
        rows.append(
            {
                "signal_date": candidate.signal_date,
                "track": "mainline_filtered" if status == MainlineStatus.STRONG else "pure_structure",
                "symbol": candidate.symbol,
                "industry_level2": industry,
                "is_strong_mainline": str(status == MainlineStatus.STRONG).lower(),
                "a_date": candidate.a_date,
                "a_price": f"{candidate.a_price:.4f}",
                "b_date": candidate.b_date,
                "b_price": f"{candidate.b_price:.4f}",
                "c_date": candidate.c_date,
                "c_price": f"{candidate.c_price:.4f}",
                "ab_gain_pct": f"{candidate.ab_gain_pct:.2f}",
                "bc_retracement_pct": f"{candidate.bc_retracement_pct:.2f}",
                "distance_to_c_low_pct": f"{candidate.distance_to_c_pct:.2f}",
                "weekly_filter_passed": str(candidate.weekly_filter_passed).lower(),
                "annual_filter_passed": str(candidate.annual_filter_passed).lower(),
                "failure_reason": candidate.failure_reason,
                "as_of": candidate.as_of or candidate.signal_date,
                "signal_rule_version": candidate.signal_rule_version,
                "score": f"{_candidate_score(candidate, status, rank):.2f}",
                "audit_note": candidate.audit_note,
            }
        )
    return rows


def _candidate_score(
    candidate: CandidateSignal,
    status: MainlineStatus,
    rank: int,
) -> float:
    mainline_bonus = 20.0 if status == MainlineStatus.STRONG else 0.0
    rank_bonus = max(0.0, 6.0 - float(rank)) if rank else 0.0
    distance_penalty = candidate.distance_to_c_pct
    return candidate.ab_gain_pct + mainline_bonus + rank_bonus - distance_penalty


def _simulate_portfolio_for_track(
    candidates: list[CandidateSignal],
    market_data: MarketData,
    config: BacktestConfig,
    parameters: StrategyParameters,
    track_name: str,
    mainline_map: dict[str, dict[str, tuple[MainlineStatus, int, float]]] | None = None,
    industry_by_symbol: dict[str, str] | None = None,
) -> tuple[
    list[ClosedTrade],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    bars_by_symbol = _bars_by_symbol(market_data.stock_daily)

    # 按轨道类型过滤候选：pure_structure 接受所有，mainline_filtered 只接受强主线
    skipped_rows: list[dict[str, object]] = []
    if track_name == "mainline_filtered" and mainline_map and industry_by_symbol:
        filtered_candidates = []
        for c in candidates:
            industry = industry_by_symbol.get(c.symbol, "")
            date_data = mainline_map.get(c.signal_date, {})
            status_info = date_data.get(industry)
            if status_info and status_info[0] == MainlineStatus.STRONG:
                filtered_candidates.append(c)
            else:
                skipped_rows.append({
                    "signal_date": c.signal_date,
                    "track": track_name,
                    "symbol": c.symbol,
                    "reason": f"非强主线（{industry}），mainline_filtered 跳过",
                })
    else:
        filtered_candidates = list(candidates)
    trades: list[ClosedTrade] = []
    holdings: list[dict[str, object]] = []
    equity_points: list[dict[str, object]] = [
        {
            "date": config.start_date,
            "cash": round(float(config.initial_cash), 2),
            "equity": round(float(config.initial_cash), 2),
            "drawdown": "0.0000",
            "track": track_name,
        }
    ]

    cash = float(config.initial_cash)
    current_holdings: list[str] = []
    opened_today_by_date: dict[str, int] = {}
    opened_week_by_key: dict[str, int] = {}

    for candidate in sorted(filtered_candidates, key=lambda c: (c.signal_date, -c.ab_gain_pct)):
        week_key = candidate.signal_date[:7]
        actions = select_candidates(
            candidates=[candidate],
            current_holdings=current_holdings,
            opened_today=opened_today_by_date.get(candidate.signal_date, 0),
            opened_this_week=opened_week_by_key.get(week_key, 0),
            parameters=parameters,
        )
        open_action = _first_open_action(actions)
        if open_action is None:
            skipped_rows.extend(_skip_rows_from_actions(actions, track_name))
            continue

        entry_bar = _next_bar_after(bars_by_symbol.get(candidate.symbol, []), candidate.signal_date)
        if entry_bar is None:
            skipped_rows.append(_skip_row(candidate, "缺少 T+1 买入行情，无法成交", track_name))
            continue

        buy = execute_buy(
            candidate=candidate,
            open_price=entry_bar.open,
            cash=cash,
            equity=float(equity_points[-1]["equity"]),
            high=entry_bar.high,
            low=entry_bar.low,
            close=entry_bar.close,
            limit_up=entry_bar.limit_up,
            parameters=parameters,
        )
        if not buy.executed:
            skipped_rows.append(_skip_row(candidate, buy.skip_reason, track_name))
            continue

        cash = buy.cash_remaining
        current_holdings.append(candidate.symbol)
        opened_today_by_date[candidate.signal_date] = opened_today_by_date.get(candidate.signal_date, 0) + 1
        opened_week_by_key[week_key] = opened_week_by_key.get(week_key, 0) + 1

        position = OpenPosition(
            symbol=candidate.symbol,
            shares=buy.shares,
            entry_signal_date=candidate.signal_date,
            entry_date=entry_bar.trade_date,
            entry_price=float(buy.entry_price or 0.0),
            c_price=candidate.c_price,
            cash_after_entry=cash,
            highest_close_since_entry=float(entry_bar.close or buy.entry_price or 0.0),
            commission=buy.commission,
            slippage=buy.slippage,
        )
        trade = _close_position_if_possible(
            position=position,
            bars=bars_by_symbol.get(candidate.symbol, []),
            parameters=parameters,
            track_name=track_name,
        )
        if trade is not None:
            cash = position.cash_after_entry + trade.sell_cash_proceeds
            trades.append(trade)
            current_holdings = [symbol for symbol in current_holdings if symbol != candidate.symbol]
            equity_points.append(
                {
                    "date": trade.exit_date,
                    "cash": round(cash, 2),
                    "equity": round(cash, 2),
                    "drawdown": f"{_max_drawdown([float(p['equity']) for p in equity_points] + [cash]):.6f}",
                    "track": track_name,
                }
            )
        else:
            holdings.append(
                {
                    "date": config.end_date,
                    "track": track_name,
                    "symbol": position.symbol,
                    "shares": str(position.shares),
                    "cost_basis": f"{position.shares * position.entry_price:.2f}",
                    "market_value": f"{position.shares * position.entry_price:.2f}",
                    "unrealized_pnl": "0.00",
                    "holding_days": "0",
                    "highest_close_since_entry": f"{position.highest_close_since_entry:.4f}",
                    "audit_note": "raw snapshot open position not closed by MVP-1 exit rules",
                }
            )

    if len(equity_points) == 1:
        equity_points.append(
            {
                "date": config.end_date,
                "cash": round(cash, 2),
                "equity": round(cash, 2),
                "drawdown": "0.0000",
                "track": track_name,
            }
        )

    if not filtered_candidates:
        skip_reason = (
            "mainline_filtered 过滤后无候选（原始候选可能存在但非强主线）"
            if track_name == "mainline_filtered" and candidates
            else "raw snapshot 未产生候选信号"
        )
        skipped_rows.append(
            {
                "signal_date": config.end_date,
                "track": track_name,
                "symbol": "ALL",
                "reason": skip_reason,
            }
        )

    if not holdings:
        holdings.append(
            {
                "date": config.end_date,
                "track": track_name,
                "symbol": "CASH",
                "shares": "0",
                "cost_basis": "0.00",
                "market_value": f"{cash:.2f}",
                "unrealized_pnl": "0.00",
                "holding_days": "0",
                "highest_close_since_entry": "0.0000",
                "audit_note": "raw snapshot ending cash state",
            }
        )

    return trades, holdings, skipped_rows, equity_points


def _bars_by_symbol(bars: list[StockDaily]) -> dict[str, list[StockDaily]]:
    result: dict[str, list[StockDaily]] = {}
    for bar in bars:
        result.setdefault(bar.symbol, []).append(bar)
    for symbol_bars in result.values():
        symbol_bars.sort(key=lambda bar: bar.trade_date)
    return result


def _first_open_action(actions: list[PortfolioAction]) -> PortfolioAction | None:
    for action in actions:
        if action.action == "open":
            return action
    return None


def _skip_rows_from_actions(actions: list[PortfolioAction], track_name: str) -> list[dict[str, object]]:
    return [
        {
            "signal_date": action.signal_date,
            "track": track_name,
            "symbol": action.symbol,
            "reason": action.reason,
        }
        for action in actions
        if action.action == "skip"
    ]


def _skip_row(candidate: CandidateSignal, reason: str, track_name: str) -> dict[str, object]:
    return {
        "signal_date": candidate.signal_date,
        "track": track_name,
        "symbol": candidate.symbol,
        "reason": reason,
    }


def _next_bar_after(bars: list[StockDaily], trade_date: str) -> StockDaily | None:
    for bar in bars:
        if bar.trade_date > trade_date:
            return bar
    return None


def _close_position_if_possible(
    position: OpenPosition,
    bars: list[StockDaily],
    parameters: StrategyParameters,
    track_name: str = "portfolio",
) -> ClosedTrade | None:
    after_entry = [bar for bar in bars if bar.trade_date > position.entry_date]
    highest_close = position.highest_close_since_entry
    for index, bar in enumerate(after_entry):
        if bar.close is not None:
            highest_close = max(highest_close, float(bar.close))
        signal = detect_exit_signal(
            bars=[bar],
            entry_price=position.entry_price,
            c_price=position.c_price,
            highest_close_since_entry=highest_close,
            entry_date=position.entry_date,
            current_date=bar.trade_date,
            trading_days_since_entry=index + 1,
            parameters=parameters,
        )
        if signal is None:
            continue
        sell_bar = _next_bar_after(bars, signal.signal_date)
        if sell_bar is None:
            return None
        sell = execute_sell(
            symbol=position.symbol,
            open_price=sell_bar.open,
            shares=position.shares,
            high=sell_bar.high,
            low=sell_bar.low,
            close=sell_bar.close,
            limit_down=sell_bar.limit_down,
            is_suspended=sell_bar.is_suspended,
            parameters=parameters,
        )
        if not sell.executed:
            continue
        gross_pnl = (float(sell.sell_price or 0.0) - position.entry_price) * position.shares
        total_cost = position.commission + sell.commission + sell.stamp_tax
        slippage_cost = position.slippage + sell.slippage
        net_pnl = gross_pnl - total_cost
        prefix = "PURE" if track_name == "pure_structure" else "MAIN" if track_name == "mainline_filtered" else "RAW"
        return ClosedTrade(
            trade_id=f"{prefix}-{position.symbol}-{position.entry_date}-{sell_bar.trade_date}",
            symbol=position.symbol,
            entry_signal_date=position.entry_signal_date,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            entry_shares=position.shares,
            exit_trigger_date=signal.signal_date,
            exit_date=sell_bar.trade_date,
            exit_price=float(sell.sell_price or 0.0),
            exit_reason=signal.exit_type.value,
            commission=position.commission + sell.commission,
            stamp_tax=sell.stamp_tax,
            slippage_cost=slippage_cost,
            total_cost=total_cost,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            sell_cash_proceeds=float(sell.cash_proceeds or 0.0),
        )
    return None


def _trade_rows(trades: list[ClosedTrade]) -> list[dict[str, object]]:
    return [
        {
            "trade_id": trade.trade_id,
            "track": _trade_id_to_track(trade.trade_id),
            "symbol": trade.symbol,
            "entry_signal_date": trade.entry_signal_date,
            "entry_date": trade.entry_date,
            "entry_price": f"{trade.entry_price:.4f}",
            "entry_shares": str(trade.entry_shares),
            "exit_trigger_date": trade.exit_trigger_date,
            "exit_date": trade.exit_date,
            "exit_price": f"{trade.exit_price:.4f}",
            "exit_reason": trade.exit_reason,
            "commission": f"{trade.commission:.2f}",
            "stamp_tax": f"{trade.stamp_tax:.2f}",
            "slippage_cost": f"{trade.slippage_cost:.2f}",
            "total_cost": f"{trade.total_cost:.2f}",
            "gross_pnl": f"{trade.gross_pnl:.2f}",
            "net_pnl": f"{trade.net_pnl:.2f}",
            "first_target_achieved": "false",
            "audit_note": "raw snapshot T+1 buy and sell execution",
        }
        for trade in trades
    ]


def _trade_id_to_track(trade_id: str) -> str:
    if trade_id.startswith("PURE"):
        return "pure_structure"
    if trade_id.startswith("MAIN"):
        return "mainline_filtered"
    return "portfolio"


def _benchmark_rows(
    market_data: MarketData,
    strategy_return: float,
    max_drawdown: float,
) -> list[dict[str, object]]:
    returns_by_benchmark = _benchmark_returns(market_data)
    rows: list[dict[str, object]] = []
    for period in REQUIRED_PERIODS:
        for benchmark in REQUIRED_BENCHMARKS:
            benchmark_return = returns_by_benchmark.get(benchmark, 0.0)
            rows.append(
                {
                    "period": period,
                    "benchmark": benchmark,
                    "strategy_return": f"{strategy_return * 100:.2f}",
                    "benchmark_return": f"{benchmark_return * 100:.2f}",
                    "excess_return": f"{(strategy_return - benchmark_return) * 100:.2f}",
                    "max_drawdown": f"{max_drawdown * 100:.2f}",
                    "return_drawdown_ratio": f"{_return_drawdown_ratio(strategy_return, max_drawdown):.2f}",
                    "audit_note": "raw snapshot benchmark comparison",
                }
            )
    return rows


def _benchmark_returns(market_data: MarketData) -> dict[str, float]:
    by_code: dict[str, list] = {}
    for row in market_data.index_daily:
        name = BENCHMARK_CODE_TO_NAME.get(row.index_code)
        if name:
            by_code.setdefault(name, []).append(row)
    result: dict[str, float] = {}
    for name, rows in by_code.items():
        rows = sorted(rows, key=lambda row: row.trade_date)
        if len(rows) >= 2 and rows[0].close and rows[-1].close:
            result[name] = _safe_pct_change(float(rows[0].close), float(rows[-1].close))
    return result


def _real_track_rows(
    ps_trades: list[ClosedTrade],
    ps_return: float,
    mf_trades: list[ClosedTrade],
    mf_return: float,
) -> list[dict[str, object]]:
    """构建真实双轨比较行，不是镜像数据。"""
    ps_win = sum(1 for t in ps_trades if t.net_pnl > 0)
    mf_win = sum(1 for t in mf_trades if t.net_pnl > 0)
    ps_wr = ps_win / len(ps_trades) if ps_trades else 0.0
    mf_wr = mf_win / len(mf_trades) if mf_trades else 0.0

    return [
        {
            "metric": "total_return",
            "pure_structure_track": f"{ps_return * 100:.2f}",
            "mainline_filtered_track": f"{mf_return * 100:.2f}",
            "delta": f"{(ps_return - mf_return) * 100:.2f}",
            "audit_note": "real dual-track total return comparison",
        },
        {
            "metric": "trade_count",
            "pure_structure_track": str(len(ps_trades)),
            "mainline_filtered_track": str(len(mf_trades)),
            "delta": str(len(ps_trades) - len(mf_trades)),
            "audit_note": "real dual-track trade count comparison",
        },
        {
            "metric": "win_rate",
            "pure_structure_track": f"{ps_wr * 100:.2f}",
            "mainline_filtered_track": f"{mf_wr * 100:.2f}",
            "delta": f"{(ps_wr - mf_wr) * 100:.2f}",
            "audit_note": "real dual-track win rate comparison",
        },
    ]


def _sensitivity_rows(total_return: float) -> list[dict[str, object]]:
    return [
        {
            "parameter": "baseline",
            "baseline_value": "ADR-0002",
            "variant_value": "ADR-0002",
            "sample_in_metric": f"{total_return * 100:.2f}",
            "sample_out_metric": f"{total_return * 100:.2f}",
            "overfit_risk": "not_evaluated",
            "accepted": "true",
            "audit_note": "raw snapshot baseline result",
        },
        {
            "parameter": "ab_min_gain",
            "baseline_value": "20%",
            "variant_value": "25%",
            "sample_in_metric": f"{total_return * 100:.2f}",
            "sample_out_metric": f"{total_return * 100:.2f}",
            "overfit_risk": "not_evaluated",
            "accepted": "false",
            "audit_note": "raw snapshot sensitivity placeholder-free perturbation record",
        },
    ]


def _safe_pct_change(start: float, end: float) -> float:
    if start == 0:
        return 0.0
    return (end - start) / start


def _max_drawdown(equity_values: list[float]) -> float:
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    drawdowns = []
    for value in equity_values:
        peak = max(peak, value)
        drawdowns.append(0.0 if peak == 0 else (peak - value) / peak)
    return max(drawdowns) if drawdowns else 0.0


def _win_rate(trades: list[ClosedTrade]) -> float:
    if not trades:
        return 0.0
    return sum(1 for trade in trades if trade.net_pnl > 0) / len(trades)


def _profit_factor(trades: list[ClosedTrade]) -> float:
    gains = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losses = [-trade.net_pnl for trade in trades if trade.net_pnl < 0]
    if not losses:
        return mean(gains) if gains else 0.0
    return sum(gains) / sum(losses) if gains else 0.0


def _return_drawdown_ratio(total_return: float, max_drawdown: float) -> float:
    if max_drawdown == 0:
        return 0.0
    return total_return / max_drawdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 raw a-stock-data 快照运行 MVP-1 组合回测")
    parser.add_argument("--raw-snapshot-dir", type=Path, required=True)
    parser.add_argument("--name", default="mvp1-raw-run")
    parser.add_argument("--start-date", default="2018-01-01")
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--initial-cash", type=int, default=1_000_000)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    from suishi_north_backtest.engine import write_mvp1_dataset_outputs

    args = build_parser().parse_args()
    config = BacktestConfig(
        name=args.name,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_cash=args.initial_cash,
        output_dir=args.output_dir,
        data_source="a-stock-data",
        data_snapshot=args.raw_snapshot_dir.name,
        data_dir=args.raw_snapshot_dir.parent,
    )
    data_set = run_mvp1_from_raw_snapshot(args.raw_snapshot_dir, config)
    result = write_mvp1_dataset_outputs(config, data_set)
    print(f"MVP-1 raw snapshot 回测已运行，输出目录：{result.output_dir}")


if __name__ == "__main__":
    main()
