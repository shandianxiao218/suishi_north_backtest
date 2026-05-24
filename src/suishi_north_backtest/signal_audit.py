from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from suishi_north_backtest.market_data import StockDaily
from suishi_north_backtest.signals import (
    DEFAULT_AB_MIN_GAIN_PCT,
    DEFAULT_BC_MAX_RETRACEMENT_PCT,
    DEFAULT_C_WINDOW_MAX,
    DEFAULT_C_WINDOW_MIN,
    DEFAULT_SIGNAL_DISTANCE_MAX_PCT,
    _resolve_signal_parameters,
    _scan_signal_findings_for_symbol,
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

    审计只读取 `trade_date <= as_of` 的 bar，并复用 signals.py 的局部
    A/B/C/信号窗口扫描规则，避免审计原因与候选生成逻辑分叉。
    """
    (
        ab_min_gain_pct,
        bc_max_retracement_pct,
        c_window_min,
        c_window_max,
        signal_distance_max_pct,
    ) = _resolve_signal_parameters(
        DEFAULT_AB_MIN_GAIN_PCT,
        DEFAULT_BC_MAX_RETRACEMENT_PCT,
        DEFAULT_C_WINDOW_MIN,
        DEFAULT_C_WINDOW_MAX,
        DEFAULT_SIGNAL_DISTANCE_MAX_PCT,
        parameters,
    )
    visible = sorted(
        [bar for bar in bars if bar.trade_date <= as_of and bar.close is not None],
        key=lambda bar: (bar.symbol, bar.trade_date),
    )
    by_symbol: dict[str, list[StockDaily]] = {}
    for bar in visible:
        by_symbol.setdefault(bar.symbol, []).append(bar)

    rows: list[SignalAuditRow] = []
    for symbol, symbol_bars in by_symbol.items():
        findings = _scan_signal_findings_for_symbol(
            bars=symbol_bars,
            symbol=symbol,
            ab_min_gain_pct=ab_min_gain_pct,
            bc_max_retracement_pct=bc_max_retracement_pct,
            c_window_min=c_window_min,
            c_window_max=c_window_max,
            signal_distance_max_pct=signal_distance_max_pct,
            as_of=as_of,
        )
        rows.extend(
            SignalAuditRow(
                as_of=finding.as_of,
                signal_rule_version=finding.signal_rule_version,
                symbol=finding.symbol,
                trade_date=finding.trade_date,
                stage=finding.stage,
                passed=finding.passed,
                failure_reason=finding.failure_reason,
                weekly_filter_passed=finding.weekly_filter_passed,
                annual_filter_passed=finding.annual_filter_passed,
                audit_note=finding.audit_note,
            )
            for finding in findings
        )
    return rows
