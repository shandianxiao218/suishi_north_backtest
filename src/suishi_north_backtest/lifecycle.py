"""组合交易生命周期深模块。

按交易日驱动，逐日遍历候选、T+1 买入、持仓管理、退出信号检测、T+1 卖出、
停牌/一字跌停顺延、每日估值、现金账本、持仓账本、skipped reason 审计。

mvp1_runner 负责 orchestration（数据加载、主线计算、评分、双轨调度），
lifecycle 负责单条轨道的完整交易生命周期。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from suishi_north_backtest.execution import execute_buy, execute_sell
from suishi_north_backtest.exits import detect_exit_signal
from suishi_north_backtest.market_data import StockDaily
from suishi_north_backtest.portfolio import PortfolioAction, select_candidates
from suishi_north_backtest.signals import CandidateSignal

if TYPE_CHECKING:
    from suishi_north_backtest.parameters import StrategyParameters


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


@dataclass
class PortfolioRunConfig:
    """单条轨道运行所需的配置。"""

    track_name: str
    initial_cash: float
    start_date: str
    end_date: str


@dataclass
class PortfolioRunResult:
    """单条轨道运行的结果。"""

    trades: list[ClosedTrade]
    holdings: list[dict[str, object]]
    skipped_trades: list[dict[str, object]]
    equity_curve: list[dict[str, object]]
    cash_ledger: list[dict[str, object]] = field(default_factory=list)
    position_ledger: list[dict[str, object]] = field(default_factory=list)


def run_portfolio_lifecycle(
    scored_candidates: list[tuple[CandidateSignal, float]],
    bars_by_symbol: dict[str, list[StockDaily]],
    run_config: PortfolioRunConfig,
    parameters: StrategyParameters,
) -> PortfolioRunResult:
    """执行单条轨道的完整交易生命周期（逐日驱动）。

    按交易日推进，每个交易日依次：
    1. 执行待卖持仓（退出信号已触发，T+1 卖出）
    2. 处理当日信号候选（检查组合约束，T+1 买入）
    3. 检测持仓退出信号（基于当日 bar）
    4. 逐日 mark-to-market

    Args:
        scored_candidates: 按 (signal_date, -score, symbol) 预排序的候选列表，
            每个元素为 (candidate, score) 元组。
        bars_by_symbol: 每只股票的日线行情，按日期排序。
        run_config: 轨道运行配置。
        parameters: 策略参数。

    Returns:
        PortfolioRunResult 包含 trades、holdings、skipped_trades、equity_curve、
        cash_ledger、position_ledger。
    """
    track_name = run_config.track_name

    # 收集所有需要处理的日期（交易日 + 候选信号日期）
    all_dates_set: set[str] = set()
    for sym_bars in bars_by_symbol.values():
        for bar in sym_bars:
            if run_config.start_date <= bar.trade_date <= run_config.end_date:
                all_dates_set.add(bar.trade_date)
    for cand, _score in scored_candidates:
        if run_config.start_date <= cand.signal_date <= run_config.end_date:
            all_dates_set.add(cand.signal_date)
    trading_dates = sorted(all_dates_set)

    # 按信号日期索引候选
    candidates_by_date: dict[str, list[tuple[CandidateSignal, float]]] = {}
    for cand, score in scored_candidates:
        candidates_by_date.setdefault(cand.signal_date, []).append((cand, score))

    # ---- 状态 ----
    cash = float(run_config.initial_cash)
    current_positions: dict[str, OpenPosition] = {}
    highest_close_map: dict[str, float] = {}
    pending_exits: dict[str, tuple[str, str]] = {}  # sym -> (exit_signal_date, exit_reason_str)

    # ---- 结果容器 ----
    trades: list[ClosedTrade] = []
    holdings_list: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []
    equity_points: list[dict[str, object]] = []
    cash_ledger: list[dict[str, object]] = []
    position_ledger: list[dict[str, object]] = []

    opened_today_by_date: dict[str, int] = {}
    opened_week_by_key: dict[str, int] = {}

    # 初始状态
    cash_ledger.append({
        "event": "initial_cash",
        "date": run_config.start_date,
        "amount": round(cash, 2),
        "track": track_name,
    })
    equity_points.append({
        "date": run_config.start_date,
        "cash": round(cash, 2),
        "equity": round(cash, 2),
        "drawdown": "0.0000",
        "track": track_name,
    })

    for date in trading_dates:

        # ================================================================
        # Phase 1: 执行待卖持仓（退出信号在先前日期已触发，今日尝试卖出）
        # ================================================================
        sold_symbols: list[str] = []
        for sym, (exit_signal_date, exit_reason_str) in list(pending_exits.items()):
            if date <= exit_signal_date:
                continue
            pos = current_positions.get(sym)
            if pos is None:
                del pending_exits[sym]
                continue
            bar = _get_bar_on_date(bars_by_symbol.get(sym, []), date)
            if bar is None:
                continue
            sell = execute_sell(
                symbol=sym,
                open_price=bar.open,
                shares=pos.shares,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                limit_down=bar.limit_down,
                is_suspended=bar.is_suspended,
                parameters=parameters,
            )
            if not sell.executed:
                continue

            gross_pnl = (float(sell.sell_price or 0.0) - pos.entry_price) * pos.shares
            total_cost = pos.commission + sell.commission + sell.stamp_tax
            slippage_cost = pos.slippage + sell.slippage
            net_pnl = gross_pnl - total_cost
            prefix = "PURE" if track_name == "pure_structure" else "MAIN" if track_name == "mainline_filtered" else "RAW"
            trade = ClosedTrade(
                trade_id=f"{prefix}-{sym}-{pos.entry_date}-{bar.trade_date}",
                symbol=sym,
                entry_signal_date=pos.entry_signal_date,
                entry_date=pos.entry_date,
                entry_price=pos.entry_price,
                entry_shares=pos.shares,
                exit_trigger_date=exit_signal_date,
                exit_date=bar.trade_date,
                exit_price=float(sell.sell_price or 0.0),
                exit_reason=exit_reason_str,
                commission=pos.commission + sell.commission,
                stamp_tax=sell.stamp_tax,
                slippage_cost=slippage_cost,
                total_cost=total_cost,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                sell_cash_proceeds=float(sell.cash_proceeds or 0.0),
            )
            trades.append(trade)
            cash += trade.sell_cash_proceeds
            sold_symbols.append(sym)

            cash_ledger.append({
                "event": "sell_cash_inflow",
                "date": bar.trade_date,
                "symbol": sym,
                "amount": round(trade.sell_cash_proceeds, 2),
                "cash_after": round(cash, 2),
                "track": track_name,
            })
            position_ledger.append({
                "event": "close_position",
                "date": bar.trade_date,
                "symbol": sym,
                "shares": pos.shares,
                "entry_price": pos.entry_price,
                "exit_price": trade.exit_price,
                "exit_reason": exit_reason_str,
                "net_pnl": round(net_pnl, 2),
                "track": track_name,
            })

        for sym in sold_symbols:
            del pending_exits[sym]
            del current_positions[sym]

        # ================================================================
        # Phase 2: 处理当日候选（signal_date == date）
        # ================================================================
        for cand, score in candidates_by_date.get(date, []):
            week_key = cand.signal_date[:7]
            actions = select_candidates(
                candidates=[cand],
                current_holdings=list(current_positions.keys()),
                opened_today=opened_today_by_date.get(cand.signal_date, 0),
                opened_this_week=opened_week_by_key.get(week_key, 0),
                parameters=parameters,
            )
            open_action = _first_open_action(actions)
            if open_action is None:
                skipped_rows.extend(_skip_rows_from_actions(actions, track_name))
                continue

            # T+1 买入
            sym_bars = bars_by_symbol.get(cand.symbol, [])
            entry_bar = _next_bar_after(sym_bars, cand.signal_date)
            if entry_bar is None:
                skipped_rows.append(_skip_row(cand, "缺少 T+1 买入行情，无法成交", track_name))
                continue

            # 计算当前权益（用于仓位管理）
            current_equity = _compute_equity(cash, current_positions, bars_by_symbol, date)

            buy = execute_buy(
                candidate=cand,
                open_price=entry_bar.open,
                cash=cash,
                equity=current_equity,
                high=entry_bar.high,
                low=entry_bar.low,
                close=entry_bar.close,
                limit_up=entry_bar.limit_up,
                parameters=parameters,
            )
            if not buy.executed:
                skipped_rows.append(_skip_row(cand, buy.skip_reason, track_name))
                continue

            old_cash = cash
            cash = buy.cash_remaining
            opened_today_by_date[cand.signal_date] = opened_today_by_date.get(cand.signal_date, 0) + 1
            opened_week_by_key[week_key] = opened_week_by_key.get(week_key, 0) + 1

            position = OpenPosition(
                symbol=cand.symbol,
                shares=buy.shares,
                entry_signal_date=cand.signal_date,
                entry_date=entry_bar.trade_date,
                entry_price=float(buy.entry_price or 0.0),
                c_price=cand.c_price,
                cash_after_entry=cash,
                highest_close_since_entry=float(entry_bar.close or buy.entry_price or 0.0),
                commission=buy.commission,
                slippage=buy.slippage,
            )
            current_positions[cand.symbol] = position
            highest_close_map[cand.symbol] = position.highest_close_since_entry

            cash_ledger.append({
                "event": "buy_cash_outflow",
                "date": entry_bar.trade_date,
                "symbol": cand.symbol,
                "amount": round(old_cash - cash, 2),
                "cash_after": round(cash, 2),
                "track": track_name,
            })
            position_ledger.append({
                "event": "open_position",
                "date": entry_bar.trade_date,
                "symbol": cand.symbol,
                "shares": buy.shares,
                "entry_price": float(buy.entry_price or 0.0),
                "track": track_name,
            })

        # ================================================================
        # Phase 3: 检测持仓退出信号（基于当日 bar）
        # ================================================================
        for sym, pos in list(current_positions.items()):
            if sym in pending_exits:
                continue
            if date <= pos.entry_date:
                continue
            sym_bars = bars_by_symbol.get(sym, [])
            bar = _get_bar_on_date(sym_bars, date)
            if bar is None:
                continue

            # 更新最高收盘价
            if bar.close is not None:
                prev_highest = highest_close_map.get(sym, pos.highest_close_since_entry)
                highest_close_map[sym] = max(prev_highest, float(bar.close))

            trading_days = sum(1 for b in sym_bars if pos.entry_date < b.trade_date <= date)

            signal = detect_exit_signal(
                bars=[bar],
                entry_price=pos.entry_price,
                c_price=pos.c_price,
                highest_close_since_entry=highest_close_map[sym],
                entry_date=pos.entry_date,
                current_date=date,
                trading_days_since_entry=trading_days,
                parameters=parameters,
            )
            if signal is not None:
                pending_exits[sym] = (signal.signal_date, signal.exit_type.value)

        # ================================================================
        # Phase 4: 逐日 mark-to-market
        # ================================================================
        equity = cash
        for sym, pos in current_positions.items():
            bar = _get_bar_on_date(bars_by_symbol.get(sym, []), date)
            if bar is not None and bar.close is not None:
                market_value = pos.shares * float(bar.close)
                equity += market_value
                position_ledger.append({
                    "event": "daily_position_state",
                    "date": date,
                    "symbol": sym,
                    "shares": pos.shares,
                    "close_price": float(bar.close),
                    "market_value": round(market_value, 2),
                    "track": track_name,
                })
            else:
                equity += pos.shares * pos.entry_price

        equity_points.append({
            "date": date,
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "drawdown": f"{_max_drawdown([float(p['equity']) for p in equity_points] + [equity]):.6f}",
            "track": track_name,
        })

    # ---- 收尾 ----
    cash_ledger.append({
        "event": "ending_cash",
        "date": run_config.end_date,
        "amount": round(cash, 2),
        "track": track_name,
    })

    # 未平仓持仓 -> holdings
    for sym, pos in current_positions.items():
        holdings_list.append({
            "date": run_config.end_date,
            "track": track_name,
            "symbol": pos.symbol,
            "shares": str(pos.shares),
            "cost_basis": f"{pos.shares * pos.entry_price:.2f}",
            "market_value": f"{pos.shares * pos.entry_price:.2f}",
            "unrealized_pnl": "0.00",
            "holding_days": "0",
            "highest_close_since_entry": f"{highest_close_map.get(sym, pos.highest_close_since_entry):.4f}",
            "audit_note": "open position not closed by exit rules",
        })

    if not holdings_list:
        holdings_list.append({
            "date": run_config.end_date,
            "track": track_name,
            "symbol": "CASH",
            "shares": "0",
            "cost_basis": "0.00",
            "market_value": f"{cash:.2f}",
            "unrealized_pnl": "0.00",
            "holding_days": "0",
            "highest_close_since_entry": "0.0000",
            "audit_note": "ending cash state",
        })

    if not scored_candidates:
        skipped_rows.append({
            "signal_date": run_config.end_date,
            "track": track_name,
            "symbol": "ALL",
            "reason": "无候选信号",
        })

    return PortfolioRunResult(
        trades=trades,
        holdings=holdings_list,
        skipped_trades=skipped_rows,
        equity_curve=equity_points,
        cash_ledger=cash_ledger,
        position_ledger=position_ledger,
    )


@dataclass
class _CloseResult:
    trade: ClosedTrade | None
    equity_points: list[dict[str, object]]


def close_position_if_possible(
    position: OpenPosition,
    bars: list[StockDaily],
    parameters: StrategyParameters,
    track_name: str = "portfolio",
    equity_points: list[dict[str, object]] | None = None,
) -> _CloseResult:
    """尝试平仓：逐日检测退出信号，T+1 卖出，停牌/一字跌停顺延。"""
    if equity_points is None:
        equity_points = []

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
            return _CloseResult(trade=None, equity_points=equity_points)
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
        return _CloseResult(
            trade=ClosedTrade(
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
            ),
            equity_points=equity_points,
        )
    return _CloseResult(trade=None, equity_points=equity_points)


def bars_by_symbol(bars: list[StockDaily]) -> dict[str, list[StockDaily]]:
    """将日线行情按股票代码分组，每组按日期排序。"""
    result: dict[str, list[StockDaily]] = {}
    for bar in bars:
        result.setdefault(bar.symbol, []).append(bar)
    for symbol_bars in result.values():
        symbol_bars.sort(key=lambda b: b.trade_date)
    return result


def _get_bar_on_date(bars: list[StockDaily], date: str) -> StockDaily | None:
    for bar in bars:
        if bar.trade_date == date:
            return bar
    return None


def _compute_equity(
    cash: float,
    current_positions: dict[str, OpenPosition],
    bars_by_symbol: dict[str, list[StockDaily]],
    date: str,
) -> float:
    equity = cash
    for sym, pos in current_positions.items():
        bar = _get_bar_on_date(bars_by_symbol.get(sym, []), date)
        if bar is not None and bar.close is not None:
            equity += pos.shares * float(bar.close)
        else:
            equity += pos.shares * pos.entry_price
    return equity


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


def _max_drawdown(equity_values: list[float]) -> float:
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    drawdowns = []
    for value in equity_values:
        peak = max(peak, value)
        drawdowns.append(0.0 if peak == 0 else (peak - value) / peak)
    return max(drawdowns) if drawdowns else 0.0
