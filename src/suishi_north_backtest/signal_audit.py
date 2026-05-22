from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from suishi_north_backtest.market_data import StockDaily
from suishi_north_backtest.signals import (
    DEFAULT_AB_MIN_GAIN_PCT,
    DEFAULT_BC_MAX_RETRACEMENT_PCT,
    DEFAULT_SIGNAL_DISTANCE_MAX_PCT,
    SIGNAL_RULE_VERSION,
)

if TYPE_CHECKING:
    from suishi_north_backtest.parameters import StrategyParameters


@dataclass(frozen=True)
class SignalAuditRow:
    as_of: str
    signal_rule_version: str
    symbol: str
    trade_date: str
    stage: str
    passed: bool
    failure_reason: str
    weekly_filter_passed: bool = True
    annual_filter_passed: bool = True
    audit_note: str = ""

    def to_row(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "signal_rule_version": self.signal_rule_version,
            "symbol": self.symbol,
            "trade_date": self.trade_date,
            "stage": self.stage,
            "passed": str(self.passed).lower(),
            "failure_reason": self.failure_reason,
            "weekly_filter_passed": str(self.weekly_filter_passed).lower(),
            "annual_filter_passed": str(self.annual_filter_passed).lower(),
            "audit_note": self.audit_note or self.failure_reason,
        }


def audit_signal_candidates(
    bars: list[StockDaily],
    as_of: str,
    parameters: StrategyParameters | None = None,
) -> list[SignalAuditRow]:
    """生成信号审计行，解释候选通过或失败原因。

    审计只读取 `trade_date <= as_of` 的 bar，用于避免未来函数。首版聚焦
    Issue #33 要求的失败原因和过滤器审计；完整 ABCD 细节后续继续深化。
    """
    visible = sorted(
        [bar for bar in bars if bar.trade_date <= as_of and bar.close is not None],
        key=lambda bar: (bar.symbol, bar.trade_date),
    )
    by_symbol: dict[str, list[StockDaily]] = {}
    for bar in visible:
        by_symbol.setdefault(bar.symbol, []).append(bar)

    rows: list[SignalAuditRow] = []
    for symbol, symbol_bars in by_symbol.items():
        rows.extend(_audit_symbol(symbol, symbol_bars, as_of, parameters))
    return rows


def _audit_symbol(
    symbol: str,
    bars: list[StockDaily],
    as_of: str,
    parameters: StrategyParameters | None,
) -> list[SignalAuditRow]:
    if len(bars) < 5:
        return [_fail(as_of, symbol, bars[-1].trade_date if bars else as_of, "insufficient_data", "可用日线不足，无法识别 ABC/C 点结构")]

    ab_min = parameters.ab_min_gain_pct_for_signals if parameters else DEFAULT_AB_MIN_GAIN_PCT
    bc_max = parameters.bc_max_retracement_pct_for_signals if parameters else DEFAULT_BC_MAX_RETRACEMENT_PCT
    distance_max = parameters.signal_distance_to_c_max_pct_for_signals if parameters else DEFAULT_SIGNAL_DISTANCE_MAX_PCT

    lows = sorted(bars, key=lambda bar: bar.close)
    highs = sorted(bars, key=lambda bar: bar.close, reverse=True)
    a_bar = lows[0]
    b_bar = next((bar for bar in highs if bar.trade_date > a_bar.trade_date), None)
    if b_bar is None:
        return [_fail(as_of, symbol, bars[-1].trade_date, "a_b_structure", "未找到 A 点之后的 B 点高点")]

    ab_gain_pct = (b_bar.close - a_bar.close) / a_bar.close * 100
    if ab_gain_pct < ab_min:
        return [_fail(as_of, symbol, b_bar.trade_date, "ab_gain", f"AB 涨幅不足：{ab_gain_pct:.2f}% < {ab_min:.2f}%")]

    after_b = [bar for bar in bars if bar.trade_date > b_bar.trade_date]
    if not after_b:
        return [_fail(as_of, symbol, b_bar.trade_date, "c_window", "B 点后没有可见交易日用于识别 C 点")]
    c_bar = min(after_b, key=lambda bar: bar.close)
    ab_gain = b_bar.close - a_bar.close
    bc_retracement_pct = (b_bar.close - c_bar.close) / ab_gain * 100 if ab_gain else 0.0
    if bc_retracement_pct > bc_max:
        return [_fail(as_of, symbol, c_bar.trade_date, "bc_retracement", f"BC 回撤过深：{bc_retracement_pct:.2f}% > {bc_max:.2f}%")]

    after_c = [bar for bar in bars if bar.trade_date > c_bar.trade_date]
    if not after_c:
        return [_fail(as_of, symbol, c_bar.trade_date, "signal_window", "C 点后没有可见交易日用于确认信号")]
    sig_bar = after_c[0]
    distance_pct = (sig_bar.close - c_bar.close) / c_bar.close * 100
    if distance_pct > distance_max:
        return [_fail(as_of, symbol, sig_bar.trade_date, "distance_to_c", f"信号日距离 C 点过远：{distance_pct:.2f}% > {distance_max:.2f}%")]

    weekly_passed = _weekly_filter_passed(bars, sig_bar.trade_date)
    annual_passed = _annual_filter_passed(bars, sig_bar.trade_date)
    if not weekly_passed:
        return [_fail(as_of, symbol, sig_bar.trade_date, "weekly_filter", "周线方向过滤未通过（日线代理）", weekly=False, annual=annual_passed)]
    if not annual_passed:
        return [_fail(as_of, symbol, sig_bar.trade_date, "annual_filter", "年线弱结构过滤未通过（日线代理）", weekly=weekly_passed, annual=False)]

    return [SignalAuditRow(as_of, SIGNAL_RULE_VERSION, symbol, sig_bar.trade_date, "candidate", True, "", weekly_passed, annual_passed, "候选通过全部 MVP-1 信号审计规则")]


def _weekly_filter_passed(bars: list[StockDaily], trade_date: str) -> bool:
    idx = next((i for i, bar in enumerate(bars) if bar.trade_date == trade_date), len(bars) - 1)
    if idx < 5:
        return True
    return bars[idx].close >= bars[idx - 5].close


def _annual_filter_passed(bars: list[StockDaily], trade_date: str) -> bool:
    idx = next((i for i, bar in enumerate(bars) if bar.trade_date == trade_date), len(bars) - 1)
    if idx < 20:
        return True
    window = bars[max(0, idx - 249) : idx + 1]
    avg_close = sum(bar.close for bar in window) / len(window)
    return bars[idx].close >= avg_close * 0.90


def _fail(
    as_of: str,
    symbol: str,
    trade_date: str,
    stage: str,
    reason: str,
    weekly: bool = True,
    annual: bool = True,
) -> SignalAuditRow:
    return SignalAuditRow(as_of, SIGNAL_RULE_VERSION, symbol, trade_date, stage, False, reason, weekly, annual, reason)
