"""人工抽样审计工具。

从已完成交易中随机抽样，关联候选信号，生成结构化审计样本，
用于人工核验交易质量：为什么买、为什么卖、是否 T+1、成本如何计入、
是否有停牌/一字板影响。
"""

from __future__ import annotations

import csv
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from suishi_north_backtest.output_contract import CSV_ENCODING


@dataclass(frozen=True)
class AuditSample:
    """单个审计样本，关联交易与候选信号。"""

    # ── 交易基本信息 ──────────────────────────────────
    trade_id: str
    track: str
    symbol: str
    entry_signal_date: str
    entry_date: str
    entry_price: str
    entry_shares: str
    exit_date: str
    exit_price: str
    exit_reason: str

    # ── 候选信号关联 ──────────────────────────────────
    candidate_matched: bool
    signal_date: str
    a_date: str
    a_price: str
    b_date: str
    b_price: str
    c_date: str
    c_price: str
    ab_gain_pct: str
    bc_retracement_pct: str
    distance_to_c_low_pct: str
    score: str
    score_breakdown: str
    is_strong_mainline: str
    weekly_filter_passed: str
    annual_filter_passed: str
    industry_level2: str

    # ── 成本明细 ──────────────────────────────────────
    commission: str
    stamp_tax: str
    slippage_cost: str
    total_cost: str
    gross_pnl: str
    net_pnl: str

    # ── 推导字段 ──────────────────────────────────────
    is_t_plus_1: bool
    entry_signal: str

    # ── 审计备注 ──────────────────────────────────────
    audit_note: str


# CSV 输出列顺序
_AUDIT_CSV_COLUMNS = [
    "trade_id",
    "track",
    "symbol",
    "entry_signal_date",
    "entry_date",
    "entry_price",
    "entry_shares",
    "exit_date",
    "exit_price",
    "exit_reason",
    "candidate_matched",
    "signal_date",
    "a_date",
    "a_price",
    "b_date",
    "b_price",
    "c_date",
    "c_price",
    "ab_gain_pct",
    "bc_retracement_pct",
    "distance_to_c_low_pct",
    "score",
    "score_breakdown",
    "is_strong_mainline",
    "weekly_filter_passed",
    "annual_filter_passed",
    "industry_level2",
    "commission",
    "stamp_tax",
    "slippage_cost",
    "total_cost",
    "gross_pnl",
    "net_pnl",
    "is_t_plus_1",
    "entry_signal",
    "audit_note",
]


def _link_trade_to_candidate(
    trade: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """将交易关联到对应的候选信号。

    关联策略（按优先级）：
    1. candidates.trade_id = trade.trade_id（当候选数据含 trade_id 时）
    2. (track, symbol, signal_date = entry_signal_date)
    """
    trade_id = trade.get("trade_id", "")
    # 策略 1：通过 trade_id 直接关联
    if trade_id:
        for c in candidates:
            if c.get("trade_id") == trade_id:
                return c
    # 策略 2：通过 (track, symbol, signal_date) 关联
    for c in candidates:
        if (
            c.get("track") == trade.get("track")
            and c.get("symbol") == trade.get("symbol")
            and c.get("signal_date") == trade.get("entry_signal_date")
        ):
            return c
    return None


def _derive_entry_signal(candidate: dict[str, Any] | None) -> str:
    """从候选信号推导入场原因描述。"""
    if candidate is None:
        return "无匹配候选信号"
    parts: list[str] = []
    mainline = candidate.get("is_strong_mainline", "")
    if mainline and str(mainline).lower() not in ("false", ""):
        parts.append("强势主线")
    score = candidate.get("score", "")
    if score:
        parts.append(f"评分={score}")
    a_date = candidate.get("a_date", "")
    c_date = candidate.get("c_date", "")
    if a_date and c_date:
        parts.append(f"ABC回调信号({a_date}~{c_date})")
    weekly = candidate.get("weekly_filter_passed", "")
    if str(weekly).lower() == "true":
        parts.append("周线通过")
    annual = candidate.get("annual_filter_passed", "")
    if str(annual).lower() == "true":
        parts.append("年线通过")
    return "; ".join(parts) if parts else "信号信息不完整"


def _is_t_plus_1(entry_signal_date: str, entry_date: str) -> bool:
    """判断是否为 T+1 买入（入场日期晚于信号日期）。"""
    if not entry_signal_date or not entry_date:
        return False
    return entry_date > entry_signal_date


def _build_sample(
    trade: dict[str, Any],
    candidate: dict[str, Any] | None,
) -> AuditSample:
    """从交易和候选信号构建审计样本。"""
    entry_signal_date = str(trade.get("entry_signal_date", ""))
    entry_date = str(trade.get("entry_date", ""))

    def _cand(field: str) -> str:
        return str(candidate.get(field, "")) if candidate else ""

    return AuditSample(
        trade_id=str(trade.get("trade_id", "")),
        track=str(trade.get("track", "")),
        symbol=str(trade.get("symbol", "")),
        entry_signal_date=entry_signal_date,
        entry_date=entry_date,
        entry_price=str(trade.get("entry_price", "")),
        entry_shares=str(trade.get("entry_shares", "")),
        exit_date=str(trade.get("exit_date", "")),
        exit_price=str(trade.get("exit_price", "")),
        exit_reason=str(trade.get("exit_reason", "")),
        candidate_matched=candidate is not None,
        signal_date=_cand("signal_date"),
        a_date=_cand("a_date"),
        a_price=_cand("a_price"),
        b_date=_cand("b_date"),
        b_price=_cand("b_price"),
        c_date=_cand("c_date"),
        c_price=_cand("c_price"),
        ab_gain_pct=_cand("ab_gain_pct"),
        bc_retracement_pct=_cand("bc_retracement_pct"),
        distance_to_c_low_pct=_cand("distance_to_c_low_pct"),
        score=_cand("score"),
        score_breakdown=_cand("score_breakdown"),
        is_strong_mainline=_cand("is_strong_mainline"),
        weekly_filter_passed=_cand("weekly_filter_passed"),
        annual_filter_passed=_cand("annual_filter_passed"),
        industry_level2=_cand("industry_level2"),
        commission=str(trade.get("commission", "")),
        stamp_tax=str(trade.get("stamp_tax", "")),
        slippage_cost=str(trade.get("slippage_cost", "")),
        total_cost=str(trade.get("total_cost", "")),
        gross_pnl=str(trade.get("gross_pnl", "")),
        net_pnl=str(trade.get("net_pnl", "")),
        is_t_plus_1=_is_t_plus_1(entry_signal_date, entry_date),
        entry_signal=_derive_entry_signal(candidate),
        audit_note=str(trade.get("audit_note", "")),
    )


def run_audit(
    trades: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    sample_size: int = 10,
    seed: int = 42,
) -> list[AuditSample]:
    """从交易列表中随机抽样并关联候选信号，生成审计样本。

    Args:
        trades: 交易记录列表（来自 Mvp1DataSet.trades 或 trades.csv）。
        candidates: 候选信号列表（来自 Mvp1DataSet.candidates 或 candidates.csv）。
        sample_size: 抽样数量。当交易数不足时抽样全部。
        seed: 随机种子，保证确定性。

    Returns:
        审计样本列表。
    """
    rng = random.Random(seed)
    actual_size = min(sample_size, len(trades))
    sampled = rng.sample(trades, actual_size)

    samples: list[AuditSample] = []
    for trade in sampled:
        candidate = _link_trade_to_candidate(trade, candidates)
        samples.append(_build_sample(trade, candidate))
    return samples


def write_audit_csv(samples: list[AuditSample], output_dir: Path) -> Path:
    """将审计样本写入 CSV 文件（utf-8-sig 编码）。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "audit_samples.csv"
    with path.open("w", newline="", encoding=CSV_ENCODING) as f:
        writer = csv.DictWriter(f, fieldnames=_AUDIT_CSV_COLUMNS)
        writer.writeheader()
        for sample in samples:
            writer.writerow(asdict(sample))
    return path


def write_audit_md(samples: list[AuditSample], output_dir: Path) -> Path:
    """将审计样本写入人类可读的 Markdown 审计报告。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "audit_samples.md"
    lines: list[str] = [
        "# 人工抽样审计报告",
        "",
        f"样本数量: {len(samples)}",
        "",
    ]

    for i, s in enumerate(samples, 1):
        lines.extend(
            [
                f"## 样本 {i}: {s.trade_id}",
                "",
                "| 字段 | 值 |",
                "|------|-----|",
                f"| 股票 | {s.symbol} |",
                f"| 轨道 | {s.track} |",
                f"| 信号日期 | {s.entry_signal_date} |",
                f"| 入场日期 | {s.entry_date} |",
                f"| 入场价格 | {s.entry_price} |",
                f"| 入场股数 | {s.entry_shares} |",
                f"| 出场日期 | {s.exit_date} |",
                f"| 出场价格 | {s.exit_price} |",
                f"| T+1 | {'是' if s.is_t_plus_1 else '否'} |",
                f"| 入场原因 | {s.entry_signal} |",
                f"| 出场原因 | {s.exit_reason} |",
                f"| 候选匹配 | {'是' if s.candidate_matched else '否'} |",
                "",
                "### 成本明细",
                "",
                "| 项目 | 金额 |",
                "|------|------|",
                f"| 佣金 | {s.commission} |",
                f"| 印花税 | {s.stamp_tax} |",
                f"| 滑点成本 | {s.slippage_cost} |",
                f"| 总成本 | {s.total_cost} |",
                f"| 毛利润 | {s.gross_pnl} |",
                f"| 净利润 | {s.net_pnl} |",
                "",
            ]
        )

        if s.candidate_matched:
            lines.extend(
                [
                    "### 候选信号详情",
                    "",
                    "| 字段 | 值 |",
                    "|------|-----|",
                    f"| A点 | {s.a_date} @ {s.a_price} |",
                    f"| B点 | {s.b_date} @ {s.b_price} |",
                    f"| C点 | {s.c_date} @ {s.c_price} |",
                    f"| AB涨幅 | {s.ab_gain_pct}% |",
                    f"| BC回撤 | {s.bc_retracement_pct}% |",
                    f"| 距C低 | {s.distance_to_c_low_pct}% |",
                    f"| 评分 | {s.score} |",
                    f"| 强势主线 | {s.is_strong_mainline} |",
                    f"| 行业 | {s.industry_level2} |",
                    "",
                ]
            )

        if s.audit_note:
            lines.extend(
                [
                    "### 审计备注",
                    "",
                    s.audit_note,
                    "",
                ]
            )

        lines.append("---")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
