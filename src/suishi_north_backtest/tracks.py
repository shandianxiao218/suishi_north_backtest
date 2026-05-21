"""双轨组合回测模块。

两条独立轨道：
- pure_structure：接受所有结构候选，不使用主线过滤
- mainline_filtered：只接受强主线行业候选

两条轨道共享相同的股票池、成本、执行、退出、参数，
独立维护现金、持仓、交易、净值。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from suishi_north_backtest.execution import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_STAMP_TAX_RATE,
    execute_buy,
    execute_sell,
)
from suishi_north_backtest.exits import ExitType, detect_exit_signal
from suishi_north_backtest.mainline import MainlineStatus
from suishi_north_backtest.market_data import StockDaily
from suishi_north_backtest.signals import CandidateSignal

if TYPE_CHECKING:
    from suishi_north_backtest.parameters import StrategyParameters


@dataclass
class Position:
    symbol: str
    entry_date: str
    entry_price: float
    shares: int
    c_price: float
    highest_close_since_entry: float
    signal_date: str

    @property
    def cost_basis(self) -> float:
        return self.entry_price * self.shares


@dataclass
class TradeRecord:
    trade_id: str
    track: str
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
    first_target_achieved: bool
    audit_note: str


@dataclass
class SkippedTrade:
    signal_date: str
    track: str
    symbol: str
    reason: str


MainlineMap = dict[str, dict[str, tuple[MainlineStatus, int, float]]]


class Track:
    """独立回测轨道，维护独立的现金、持仓、交易和净值。"""

    def __init__(
        self,
        name: str,
        initial_cash: float = 1_000_000.0,
        commission_rate: float = DEFAULT_COMMISSION_RATE,
        slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
        stamp_tax_rate: float = DEFAULT_STAMP_TAX_RATE,
        parameters: StrategyParameters | None = None,
    ) -> None:
        self.name = name
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.stamp_tax_rate = stamp_tax_rate
        self.parameters = parameters

        self.positions: dict[str, Position] = {}
        self.trades: list[TradeRecord] = []
        self.skipped_trades: list[SkippedTrade] = []
        self.equity_curve: list[dict[str, object]] = [
            {
                "date": "",
                "cash": initial_cash,
                "equity": initial_cash,
                "drawdown": "0.0",
                "track": name,
            }
        ]
        self._trade_counter = 0

    def filter_candidates(
        self,
        candidates: list[CandidateSignal],
        mainline_map: MainlineMap,
        signal_date: str,
        industry_map: dict[str, str] | None = None,
    ) -> list[CandidateSignal]:
        """根据轨道类型过滤候选。

        Args:
            industry_map: symbol -> industry_level2 映射，
                          mainline_filtered 轨道需要此映射判断候选行业。
        """
        if self.name == "pure_structure":
            return list(candidates)
        elif self.name == "mainline_filtered":
            return self._filter_mainline(candidates, mainline_map, signal_date, industry_map)
        return list(candidates)

    def _filter_mainline(
        self,
        candidates: list[CandidateSignal],
        mainline_map: MainlineMap,
        signal_date: str,
        industry_map: dict[str, str] | None,
    ) -> list[CandidateSignal]:
        """mainline_filtered 只接受强主线行业候选。"""
        strong_industries = self._get_strong_industries(mainline_map, signal_date)
        if not strong_industries or not industry_map:
            return []

        return [
            c for c in candidates
            if industry_map.get(c.symbol) in strong_industries
        ]

    def _get_strong_industries(
        self, mainline_map: MainlineMap, signal_date: str
    ) -> set[str]:
        date_data = mainline_map.get(signal_date, {})
        return {
            industry
            for industry, (status, _, _) in date_data.items()
            if status == MainlineStatus.STRONG
        }

    def execute_buy(
        self,
        candidate: CandidateSignal,
        open_price: float,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
        limit_up: float | None = None,
    ) -> object:
        """执行买入并更新轨道状态。"""
        equity = self._compute_equity()
        result = execute_buy(
            candidate=candidate,
            open_price=open_price,
            cash=self.cash,
            equity=equity,
            high=high,
            low=low,
            close=close,
            limit_up=limit_up,
            parameters=self.parameters,
        )

        if result.executed:
            self.cash = result.cash_remaining
            self.positions[candidate.symbol] = Position(
                symbol=candidate.symbol,
                entry_date=candidate.signal_date,
                entry_price=result.entry_price,
                shares=result.shares,
                c_price=candidate.c_price,
                highest_close_since_entry=result.entry_price,
                signal_date=candidate.signal_date,
            )

        return result

    def check_and_execute_exit(
        self,
        symbol: str,
        bars: list[StockDaily],
        current_date: str,
        trading_days_since_entry: int,
    ) -> object | None:
        """检测退出信号并执行卖出。"""
        pos = self.positions.get(symbol)
        if pos is None:
            return None

        if not bars:
            return None

        current_bar = bars[-1]
        if current_bar.close is not None and (
            pos.highest_close_since_entry is None
            or current_bar.close > pos.highest_close_since_entry
        ):
            pos.highest_close_since_entry = current_bar.close

        signal = detect_exit_signal(
            bars=bars,
            entry_price=pos.entry_price,
            c_price=pos.c_price,
            highest_close_since_entry=pos.highest_close_since_entry,
            entry_date=pos.entry_date,
            current_date=current_date,
            trading_days_since_entry=trading_days_since_entry,
            parameters=self.parameters,
        )

        if signal is None:
            return None

        # T+1 开盘执行卖出
        sell_result = execute_sell(
            symbol=symbol,
            open_price=current_bar.open,
            shares=pos.shares,
            high=current_bar.high,
            low=current_bar.low,
            close=current_bar.close,
            limit_down=current_bar.limit_down,
            is_suspended=current_bar.is_suspended,
            parameters=self.parameters,
        )

        if sell_result.executed:
            self.cash += sell_result.cash_proceeds
            self._trade_counter += 1
            self.trades.append(
                TradeRecord(
                    trade_id=f"{self.name.upper()[:4]}-{self._trade_counter:04d}",
                    track=self.name,
                    symbol=symbol,
                    entry_signal_date=pos.signal_date,
                    entry_date=pos.entry_date,
                    entry_price=pos.entry_price,
                    entry_shares=pos.shares,
                    exit_trigger_date=signal.signal_date,
                    exit_date=current_date,
                    exit_price=sell_result.sell_price,
                    exit_reason=signal.exit_type.value,
                    commission=sell_result.commission,
                    stamp_tax=sell_result.stamp_tax,
                    slippage_cost=sell_result.slippage,
                    total_cost=sell_result.total_cost,
                    gross_pnl=round(
                        sell_result.sell_price * pos.shares - pos.entry_price * pos.shares, 2
                    ),
                    net_pnl=round(
                        sell_result.cash_proceeds - pos.cost_basis, 2
                    ),
                    first_target_achieved=sell_result.sell_price > pos.entry_price,
                    audit_note=f"{signal.reason}；T+1 开盘卖出",
                )
            )
            del self.positions[symbol]
        elif sell_result.deferred:
            self.skipped_trades.append(
                SkippedTrade(
                    signal_date=current_date,
                    track=self.name,
                    symbol=symbol,
                    reason=f"卖出顺延：{sell_result.skip_reason}",
                )
            )

        return sell_result

    def update_equity(self, date: str, prices: dict[str, float]) -> None:
        """更新某日期的净值曲线。"""
        equity = self._compute_equity(prices)
        peak = max(
            (float(e.get("equity", 0)) for e in self.equity_curve),
            default=self.initial_cash,
        )
        drawdown = (peak - equity) / peak if peak > 0 else 0.0
        self.equity_curve.append({
            "date": date,
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "drawdown": f"{drawdown:.4f}",
            "track": self.name,
        })

    def _compute_equity(self, prices: dict[str, float] | None = None) -> float:
        """计算当前总权益。"""
        market_value = 0.0
        if prices:
            for symbol, pos in self.positions.items():
                if symbol in prices:
                    market_value += prices[symbol] * pos.shares
                else:
                    market_value += pos.cost_basis
        else:
            for pos in self.positions.values():
                market_value += pos.cost_basis
        return self.cash + market_value

    def compute_metrics(self) -> dict[str, object]:
        """计算轨道指标。"""
        if not self.equity_curve:
            return {
                "trade_count": 0,
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "ending_equity": self.initial_cash,
            }

        ending_equity = float(self.equity_curve[-1]["equity"])
        total_return = (ending_equity - self.initial_cash) / self.initial_cash

        max_dd = 0.0
        peak = self.initial_cash
        for entry in self.equity_curve:
            eq = float(entry["equity"])
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        winning = [t for t in self.trades if t.net_pnl > 0]
        win_rate = len(winning) / len(self.trades) if self.trades else 0.0

        return {
            "trade_count": len(self.trades) + len(self.positions),
            "total_return": round(total_return, 6),
            "max_drawdown": round(max_dd, 6),
            "ending_equity": round(ending_equity, 2),
            "win_rate": round(win_rate, 4),
        }


def build_mainline_map(
    industry_mainline: list,
) -> MainlineMap:
    """将 compute_mainlines 的输出转换为信号日 -> 行业 -> (status, rank, amount) 映射。"""
    result: MainlineMap = {}
    for entry in industry_mainline:
        if entry.trade_date not in result:
            result[entry.trade_date] = {}
        result[entry.trade_date][entry.industry_level2] = (
            entry.status,
            entry.rank,
            entry.amount,
        )
    return result


class DualTrackResult:
    """双轨回测结果。"""

    def __init__(
        self,
        pure_structure: Track,
        mainline_filtered: Track,
    ) -> None:
        self.pure_structure = pure_structure
        self.mainline_filtered = mainline_filtered

    def track_comparison_rows(self) -> list[dict[str, object]]:
        """生成 track_comparison.csv 行。"""
        metrics_a = self.pure_structure.compute_metrics()
        metrics_b = self.mainline_filtered.compute_metrics()
        return _build_comparison(metrics_a, metrics_b)

    def to_equity_curve_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        rows.extend(self.pure_structure.equity_curve)
        rows.extend(self.mainline_filtered.equity_curve)
        return rows

    def to_trades_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for t in self.pure_structure.trades:
            rows.append(_trade_to_dict(t))
        for t in self.mainline_filtered.trades:
            rows.append(_trade_to_dict(t))
        return rows

    def to_skipped_trades_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for s in self.pure_structure.skipped_trades:
            rows.append({
                "signal_date": s.signal_date,
                "track": s.track,
                "symbol": s.symbol,
                "reason": s.reason,
            })
        for s in self.mainline_filtered.skipped_trades:
            rows.append({
                "signal_date": s.signal_date,
                "track": s.track,
                "symbol": s.symbol,
                "reason": s.reason,
            })
        return rows


def _trade_to_dict(t: TradeRecord) -> dict[str, object]:
    return {
        "trade_id": t.trade_id,
        "track": t.track,
        "symbol": t.symbol,
        "entry_signal_date": t.entry_signal_date,
        "entry_date": t.entry_date,
        "entry_price": str(t.entry_price),
        "entry_shares": str(t.entry_shares),
        "exit_trigger_date": t.exit_trigger_date,
        "exit_date": t.exit_date,
        "exit_price": str(t.exit_price),
        "exit_reason": t.exit_reason,
        "commission": str(t.commission),
        "stamp_tax": str(t.stamp_tax),
        "slippage_cost": str(t.slippage_cost),
        "total_cost": str(t.total_cost),
        "gross_pnl": str(t.gross_pnl),
        "net_pnl": str(t.net_pnl),
        "first_target_achieved": str(t.first_target_achieved).lower(),
        "audit_note": t.audit_note,
    }


def _build_comparison(
    metrics_a: dict[str, object],
    metrics_b: dict[str, object],
) -> list[dict[str, object]]:
    """构建 track_comparison 行。"""
    rows: list[dict[str, object]] = []
    for metric in ["total_return", "max_drawdown", "trade_count", "win_rate"]:
        val_a = metrics_a.get(metric, 0)
        val_b = metrics_b.get(metric, 0)
        delta = round(float(val_a) - float(val_b), 6) if isinstance(val_a, (int, float)) else 0
        rows.append({
            "metric": metric,
            "pure_structure_track": str(val_a),
            "mainline_filtered_track": str(val_b),
            "delta": str(delta),
            "audit_note": "real track metrics",
        })
    return rows


class run_dual_tracks:
    """双轨回测运行器（命名空间类）。"""

    @staticmethod
    def _build_comparison(
        metrics_a: dict[str, object],
        metrics_b: dict[str, object],
    ) -> list[dict[str, object]]:
        return _build_comparison(metrics_a, metrics_b)
