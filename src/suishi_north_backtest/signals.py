from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from suishi_north_backtest.market_data import StockDaily

if TYPE_CHECKING:
    from suishi_north_backtest.parameters import StrategyParameters


SIGNAL_RULE_VERSION = "MVP1-SIGNAL-AUDIT-v1"


@dataclass
class CandidateSignal:
    signal_date: str
    symbol: str
    a_date: str
    a_price: float
    b_date: str
    b_price: float
    c_date: str
    c_price: float
    ab_gain_pct: float
    bc_retracement_pct: float
    distance_to_c_pct: float
    weekly_filter_passed: bool = True
    annual_filter_passed: bool = True
    failure_reason: str = ""
    as_of: str = ""
    signal_rule_version: str = SIGNAL_RULE_VERSION
    audit_note: str = "candidate passed MVP-1 signal audit"


@dataclass(frozen=True)
class SignalAuditFinding:
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
    candidate: CandidateSignal | None = None


DEFAULT_AB_MIN_GAIN_PCT = 20.0
DEFAULT_BC_MAX_RETRACEMENT_PCT = 60.0
DEFAULT_C_WINDOW_MIN = 3
DEFAULT_C_WINDOW_MAX = 20
DEFAULT_SIGNAL_DISTANCE_MAX_PCT = 8.0


def find_candidates(
    bars: list[StockDaily],
    as_of: str | None = None,
    ab_min_gain_pct: float = DEFAULT_AB_MIN_GAIN_PCT,
    bc_max_retracement_pct: float = DEFAULT_BC_MAX_RETRACEMENT_PCT,
    c_window_min: int = DEFAULT_C_WINDOW_MIN,
    c_window_max: int = DEFAULT_C_WINDOW_MAX,
    signal_distance_max_pct: float = DEFAULT_SIGNAL_DISTANCE_MAX_PCT,
    parameters: StrategyParameters | None = None,
) -> list[CandidateSignal]:
    (
        ab_min_gain_pct,
        bc_max_retracement_pct,
        c_window_min,
        c_window_max,
        signal_distance_max_pct,
    ) = _resolve_signal_parameters(
        ab_min_gain_pct,
        bc_max_retracement_pct,
        c_window_min,
        c_window_max,
        signal_distance_max_pct,
        parameters,
    )

    if len(bars) < 5:
        return []

    if as_of:
        bars = [b for b in bars if b.trade_date <= as_of]

    if len(bars) < 5:
        return []

    bars = sorted(bars, key=lambda b: b.trade_date)
    bars = [b for b in bars if b.close is not None]

    by_symbol: dict[str, list[StockDaily]] = {}
    for b in bars:
        by_symbol.setdefault(b.symbol, []).append(b)

    candidates: list[CandidateSignal] = []

    for symbol, symbol_bars in by_symbol.items():
        symbol_candidates = _find_candidates_for_symbol(
            symbol_bars,
            symbol,
            ab_min_gain_pct,
            bc_max_retracement_pct,
            c_window_min,
            c_window_max,
            signal_distance_max_pct,
            as_of=as_of,
        )
        candidates.extend(symbol_candidates)

    return candidates


def _resolve_signal_parameters(
    ab_min_gain_pct: float = DEFAULT_AB_MIN_GAIN_PCT,
    bc_max_retracement_pct: float = DEFAULT_BC_MAX_RETRACEMENT_PCT,
    c_window_min: int = DEFAULT_C_WINDOW_MIN,
    c_window_max: int = DEFAULT_C_WINDOW_MAX,
    signal_distance_max_pct: float = DEFAULT_SIGNAL_DISTANCE_MAX_PCT,
    parameters: StrategyParameters | None = None,
) -> tuple[float, float, int, int, float]:
    if parameters is not None:
        return (
            parameters.ab_min_gain_pct_for_signals,
            parameters.bc_max_retracement_pct_for_signals,
            parameters.c_window_min_days,
            parameters.c_window_max_days,
            parameters.signal_distance_to_c_max_pct_for_signals,
        )
    return (
        ab_min_gain_pct,
        bc_max_retracement_pct,
        c_window_min,
        c_window_max,
        signal_distance_max_pct,
    )


def _find_candidates_for_symbol(
    bars: list[StockDaily],
    symbol: str,
    ab_min_gain_pct: float,
    bc_max_retracement_pct: float,
    c_window_min: int,
    c_window_max: int,
    signal_distance_max_pct: float,
    as_of: str | None = None,
) -> list[CandidateSignal]:
    findings = _scan_signal_findings_for_symbol(
        bars=bars,
        symbol=symbol,
        ab_min_gain_pct=ab_min_gain_pct,
        bc_max_retracement_pct=bc_max_retracement_pct,
        c_window_min=c_window_min,
        c_window_max=c_window_max,
        signal_distance_max_pct=signal_distance_max_pct,
        as_of=as_of,
    )
    return [finding.candidate for finding in findings if finding.candidate is not None]


def _scan_signal_findings_for_symbol(
    bars: list[StockDaily],
    symbol: str,
    ab_min_gain_pct: float,
    bc_max_retracement_pct: float,
    c_window_min: int,
    c_window_max: int,
    signal_distance_max_pct: float,
    as_of: str | None = None,
) -> list[SignalAuditFinding]:
    findings: list[SignalAuditFinding] = []
    audit_as_of = as_of or (bars[-1].trade_date if bars else "")

    if len(bars) < 5:
        return [
            _audit_finding(
                audit_as_of,
                symbol,
                bars[-1].trade_date if bars else audit_as_of,
                "insufficient_data",
                False,
                "可用日线不足，无法识别 ABC/C 点结构",
            )
        ]

    for b_idx in range(2, len(bars) - 2):
        b_bar = bars[b_idx]

        if b_bar.close <= bars[b_idx - 1].close or b_bar.close <= bars[b_idx + 1].close:
            continue

        a_idx, a_bar = _find_a_point(bars, b_idx)
        if a_idx is None or a_bar is None:
            findings.append(
                _audit_finding(
                    audit_as_of,
                    symbol,
                    b_bar.trade_date,
                    "a_b_structure",
                    False,
                    "局部 B 点之前未找到合法局部 A 点",
                )
            )
            continue

        ab_gain_pct = (b_bar.close - a_bar.close) / a_bar.close * 100
        if ab_gain_pct < ab_min_gain_pct:
            findings.append(
                _audit_finding(
                    audit_as_of,
                    symbol,
                    b_bar.trade_date,
                    "ab_gain",
                    False,
                    f"AB 涨幅不足：{ab_gain_pct:.2f}% < {ab_min_gain_pct:.2f}%",
                )
            )
            continue

        c_window_found = False
        for c_offset in range(c_window_min, min(c_window_max + 1, len(bars) - b_idx)):
            c_idx = b_idx + c_offset
            if c_idx >= len(bars):
                break

            c_bar = bars[c_idx]

            if c_idx > 0 and c_idx < len(bars) - 1:
                if c_bar.close > bars[c_idx - 1].close or c_bar.close > bars[c_idx + 1].close:
                    continue
            c_window_found = True

            bc_drop = b_bar.close - c_bar.close
            ab_gain = b_bar.close - a_bar.close
            if ab_gain == 0:
                continue

            bc_retracement_pct = bc_drop / ab_gain * 100
            if bc_retracement_pct > bc_max_retracement_pct:
                findings.append(
                    _audit_finding(
                        audit_as_of,
                        symbol,
                        c_bar.trade_date,
                        "bc_retracement",
                        False,
                        f"BC 回撤过深：{bc_retracement_pct:.2f}% > {bc_max_retracement_pct:.2f}%",
                    )
                )
                continue

            turn_strong_found = False
            for sig_idx in range(c_idx + 1, min(c_idx + 6, len(bars))):
                sig_bar = bars[sig_idx]

                if not _is_turn_strong(bars, sig_idx, c_idx):
                    continue
                turn_strong_found = True

                distance_pct = (sig_bar.close - c_bar.close) / c_bar.close * 100
                if distance_pct > signal_distance_max_pct:
                    findings.append(
                        _audit_finding(
                            audit_as_of,
                            symbol,
                            sig_bar.trade_date,
                            "distance_to_c",
                            False,
                            f"信号日距离 C 点过远：{distance_pct:.2f}% > {signal_distance_max_pct:.2f}%",
                        )
                    )
                    continue

                weekly_passed = _is_weekly_filter_passed(bars, sig_idx)
                annual_passed = _is_annual_filter_passed(bars, sig_idx)
                failure_reason = _filter_failure_reason(weekly_passed, annual_passed)
                if not weekly_passed or not annual_passed:
                    stage = "weekly_filter" if not weekly_passed else "annual_filter"
                    findings.append(
                        _audit_finding(
                            audit_as_of,
                            symbol,
                            sig_bar.trade_date,
                            stage,
                            False,
                            failure_reason,
                            weekly_passed,
                            annual_passed,
                        )
                    )
                    continue

                candidate = CandidateSignal(
                    signal_date=sig_bar.trade_date,
                    symbol=symbol,
                    a_date=a_bar.trade_date,
                    a_price=a_bar.close,
                    b_date=b_bar.trade_date,
                    b_price=b_bar.close,
                    c_date=c_bar.trade_date,
                    c_price=c_bar.close,
                    ab_gain_pct=round(ab_gain_pct, 2),
                    bc_retracement_pct=round(bc_retracement_pct, 2),
                    distance_to_c_pct=round(distance_pct, 2),
                    weekly_filter_passed=True,
                    annual_filter_passed=True,
                    failure_reason="",
                    as_of=audit_as_of,
                    signal_rule_version=SIGNAL_RULE_VERSION,
                    audit_note=(
                        "passed structural ABC/C checks; "
                        "weekly/annual filter status recorded for audit"
                    ),
                )
                findings.append(
                    SignalAuditFinding(
                        as_of=audit_as_of,
                        signal_rule_version=SIGNAL_RULE_VERSION,
                        symbol=symbol,
                        trade_date=sig_bar.trade_date,
                        stage="candidate",
                        passed=True,
                        failure_reason="",
                        weekly_filter_passed=True,
                        annual_filter_passed=True,
                        audit_note="候选通过全部 MVP-1 信号审计规则",
                        candidate=candidate,
                    )
                )
                break
            if not turn_strong_found:
                findings.append(
                    _audit_finding(
                        audit_as_of,
                        symbol,
                        c_bar.trade_date,
                        "turn_strong",
                        False,
                        "C 点后 5 日内未出现止跌转强确认",
                    )
                )
        if not c_window_found:
            findings.append(
                _audit_finding(
                    audit_as_of,
                    symbol,
                    b_bar.trade_date,
                    "c_window",
                    False,
                    "B 点后窗口内未找到合法局部 C 点",
                )
            )

    if findings:
        return findings
    return [
        _audit_finding(
            audit_as_of,
            symbol,
            bars[-1].trade_date,
            "a_b_structure",
            False,
            "未找到合法局部 B 点，无法形成 ABC/C 点候选",
        )
    ]


def _audit_finding(
    as_of: str,
    symbol: str,
    trade_date: str,
    stage: str,
    passed: bool,
    failure_reason: str,
    weekly_filter_passed: bool = True,
    annual_filter_passed: bool = True,
) -> SignalAuditFinding:
    return SignalAuditFinding(
        as_of=as_of,
        signal_rule_version=SIGNAL_RULE_VERSION,
        symbol=symbol,
        trade_date=trade_date,
        stage=stage,
        passed=passed,
        failure_reason=failure_reason,
        weekly_filter_passed=weekly_filter_passed,
        annual_filter_passed=annual_filter_passed,
        audit_note=failure_reason,
    )


def _filter_failure_reason(weekly_passed: bool, annual_passed: bool) -> str:
    reasons = []
    if not weekly_passed:
        reasons.append("周线方向过滤未通过")
    if not annual_passed:
        reasons.append("年线弱结构过滤未通过")
    return "；".join(reasons)


def _find_a_point(
    bars: list[StockDaily], b_idx: int
) -> tuple[int | None, StockDaily | None]:
    best_idx = None
    best_low = None

    for i in range(max(0, b_idx - 25), b_idx):
        if i < 1 or i >= len(bars) - 1:
            continue
        if bars[i].close <= bars[i - 1].close and bars[i].close <= bars[i + 1].close:
            if best_low is None or bars[i].close < best_low:
                best_low = bars[i].close
                best_idx = i

    if best_idx is not None:
        return best_idx, bars[best_idx]
    return None, None


def _is_turn_strong(bars: list[StockDaily], sig_idx: int, c_idx: int) -> bool:
    if sig_idx >= 4:
        ma5 = sum(bars[i].close for i in range(sig_idx - 4, sig_idx + 1)) / 5
        if bars[sig_idx].close > ma5:
            return True

    if sig_idx >= c_idx + 2:
        last_two = bars[sig_idx - 1 : sig_idx + 1]
        c_close = bars[c_idx].close
        if all(b.close >= c_close for b in last_two):
            if bars[sig_idx].close >= bars[sig_idx - 1].close:
                return True

    return False


def _is_weekly_filter_passed(bars: list[StockDaily], sig_idx: int) -> bool:
    """日线代理的周线方向过滤。"""
    if sig_idx < 5:
        return True
    current = bars[sig_idx].close
    five_days_ago = bars[sig_idx - 5].close
    recent_lows = [b.close for b in bars[max(0, sig_idx - 4) : sig_idx + 1]]
    return current >= five_days_ago and current >= min(recent_lows)


def _is_annual_filter_passed(bars: list[StockDaily], sig_idx: int) -> bool:
    """日线代理的年线弱结构过滤。"""
    if sig_idx < 20:
        return True
    window = bars[max(0, sig_idx - 249) : sig_idx + 1]
    avg_close = sum(b.close for b in window) / len(window)
    return bars[sig_idx].close >= avg_close * 0.90
