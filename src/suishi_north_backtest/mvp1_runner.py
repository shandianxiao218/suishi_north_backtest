from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.data import Mvp1DataSet
from suishi_north_backtest.lifecycle import (
    ClosedTrade,
    PortfolioRunConfig,
    bars_by_symbol as _bars_by_symbol,
    run_portfolio_lifecycle,
)
from suishi_north_backtest.mainline import MainlineStatus, compute_mainlines
from suishi_north_backtest.market_data import MarketData, StockDaily, load_market_data
from suishi_north_backtest.metrics import build_benchmark_comparison_rows
from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
from suishi_north_backtest.raw_data import validate_raw_snapshot
from suishi_north_backtest.scoring import ScoringContext, ScoreBreakdown, score_candidate
from suishi_north_backtest.signals import CandidateSignal, find_candidates
from suishi_north_backtest.tracks import Track, build_mainline_map
from suishi_north_backtest.sensitivity import (
    create_parameter_variants,
    sensitivity_result_to_rows,
)


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

    # 构建 (symbol, trade_date) -> amount 映射，避免未来函数
    stock_amount_by_symbol_date = _build_stock_amount_by_symbol_date(market_data.stock_daily)
    bars_by_symbol_for_lookup = _bars_by_symbol(market_data.stock_daily)
    # 构建行业候选集中度
    industry_candidate_count = _build_industry_candidate_count(candidates, industry_by_symbol)

    # 预计算每个候选的评分，用于排序和输出
    candidate_scores = _score_all_candidates(
        candidates,
        industry_by_symbol,
        mainline_status_by_key,
        mainline_rank_by_key,
        stock_amount_by_symbol_date,
        bars_by_symbol_for_lookup,
        industry_candidate_count,
    )

    candidate_rows = _candidate_rows_from_scores(candidate_scores)

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
            candidate_scores=candidate_scores,
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
        benchmark_comparison=build_benchmark_comparison_rows(
            equity_curve=primary_equity,
            index_daily=market_data.index_daily,
            as_of=as_of,
            trades=_trade_rows(all_trades),
            required_benchmarks=REQUIRED_BENCHMARKS,
            required_periods=REQUIRED_PERIODS,
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


@dataclass(frozen=True)
class _CandidateScore:
    candidate: CandidateSignal
    score: float
    breakdown: "ScoreBreakdown"
    industry: str
    mainline_status: MainlineStatus


def _score_all_candidates(
    candidates: list[CandidateSignal],
    industry_by_symbol: dict[str, str],
    mainline_status_by_key: dict[tuple[str, str], MainlineStatus],
    mainline_rank_by_key: dict[tuple[str, str], int],
    stock_amount_by_symbol_date: dict[tuple[str, str], float],
    bars_by_symbol: dict[str, list[StockDaily]],
    industry_candidate_count: dict[str, int],
) -> list[_CandidateScore]:
    """为所有候选计算评分，返回带评分信息的列表。"""
    results: list[_CandidateScore] = []
    for candidate in candidates:
        industry = industry_by_symbol.get(candidate.symbol, "")
        status = mainline_status_by_key.get(
            (candidate.signal_date, industry), MainlineStatus.NONE
        )
        rank = mainline_rank_by_key.get((candidate.signal_date, industry), 0)
        stock_amount = _lookup_amount_on_or_before(
            stock_amount_by_symbol_date,
            candidate.symbol,
            candidate.signal_date,
            bars_by_symbol,
        )
        conc_count = industry_candidate_count.get(industry, 1)

        scoring_ctx = ScoringContext(
            mainline_status=status.value if status else "none",
            industry_rank=rank,
            industry_amount=0.0,
            stock_amount=stock_amount,
            same_industry_candidate_count=conc_count,
        )
        total_score, breakdown = score_candidate(
            ab_gain_pct=candidate.ab_gain_pct,
            bc_retracement_pct=candidate.bc_retracement_pct,
            distance_to_c_pct=candidate.distance_to_c_pct,
            weekly_filter_passed=candidate.weekly_filter_passed,
            annual_filter_passed=candidate.annual_filter_passed,
            context=scoring_ctx,
        )
        results.append(_CandidateScore(
            candidate=candidate,
            score=total_score,
            breakdown=breakdown,
            industry=industry,
            mainline_status=status,
        ))
    return results


def _candidate_rows_from_scores(
    scored: list[_CandidateScore],
) -> list[dict[str, object]]:
    """从评分结果生成 candidates.csv 行。"""
    rows: list[dict[str, object]] = []
    for s in scored:
        c = s.candidate
        rows.append(
            {
                "signal_date": c.signal_date,
                "track": "mainline_filtered" if s.mainline_status == MainlineStatus.STRONG else "pure_structure",
                "symbol": c.symbol,
                "industry_level2": s.industry,
                "is_strong_mainline": str(s.mainline_status == MainlineStatus.STRONG).lower(),
                "a_date": c.a_date,
                "a_price": f"{c.a_price:.4f}",
                "b_date": c.b_date,
                "b_price": f"{c.b_price:.4f}",
                "c_date": c.c_date,
                "c_price": f"{c.c_price:.4f}",
                "ab_gain_pct": f"{c.ab_gain_pct:.2f}",
                "bc_retracement_pct": f"{c.bc_retracement_pct:.2f}",
                "distance_to_c_low_pct": f"{c.distance_to_c_pct:.2f}",
                "weekly_filter_passed": str(c.weekly_filter_passed).lower(),
                "annual_filter_passed": str(c.annual_filter_passed).lower(),
                "failure_reason": c.failure_reason,
                "as_of": c.as_of or c.signal_date,
                "signal_rule_version": c.signal_rule_version,
                "score": f"{s.score:.2f}",
                "score_breakdown": s.breakdown.to_csv_string(),
                "audit_note": c.audit_note,
            }
        )
    return rows


def _build_stock_amount_by_symbol_date(
    stock_daily: list[StockDaily],
) -> dict[tuple[str, str], float]:
    """构建 (symbol, trade_date) -> amount 映射。

    评分时按候选 signal_date 查询当日成交额，
    避免使用全局 as_of 末端的未来成交额。
    """
    result: dict[tuple[str, str], float] = {}
    for bar in stock_daily:
        if bar.amount is not None:
            result[(bar.symbol, bar.trade_date)] = float(bar.amount)
    return result


def _lookup_amount_on_or_before(
    amount_map: dict[tuple[str, str], float],
    symbol: str,
    signal_date: str,
    bars_by_symbol: dict[str, list[StockDaily]],
) -> float:
    """查询 signal_date 当日或之前最近一日的成交额。

    如果 signal_date 当日没有行情（停牌等），向前查找最近可用值。
    """
    # 先尝试精确匹配
    amt = amount_map.get((symbol, signal_date))
    if amt is not None:
        return amt
    # 向前查找最近可用日
    symbol_bars = bars_by_symbol.get(symbol, [])
    for bar in reversed(symbol_bars):
        if bar.trade_date <= signal_date and bar.amount is not None:
            return float(bar.amount)
    return 0.0


def _build_industry_candidate_count(
    candidates: list[CandidateSignal],
    industry_by_symbol: dict[str, str],
) -> dict[str, int]:
    """构建每个二级行业的候选数量映射。"""
    counts: dict[str, int] = {}
    for c in candidates:
        industry = industry_by_symbol.get(c.symbol, "")
        counts[industry] = counts.get(industry, 0) + 1
    return counts


def _simulate_portfolio_for_track(
    candidate_scores: list[_CandidateScore],
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
    """单条轨道模拟：过滤候选 -> 调用 lifecycle -> 返回结果。"""
    skipped_rows: list[dict[str, object]] = []
    if track_name == "mainline_filtered" and mainline_map and industry_by_symbol:
        filtered_scores = []
        for cs in candidate_scores:
            c = cs.candidate
            industry = industry_by_symbol.get(c.symbol, "")
            date_data = mainline_map.get(c.signal_date, {})
            status_info = date_data.get(industry)
            if status_info and status_info[0] == MainlineStatus.STRONG:
                filtered_scores.append(cs)
            else:
                skipped_rows.append({
                    "signal_date": c.signal_date,
                    "track": track_name,
                    "symbol": c.symbol,
                    "reason": f"非强主线（{industry}），mainline_filtered 跳过",
                })
    else:
        filtered_scores = list(candidate_scores)

    # 按评分排序后转为 lifecycle 所需的 (candidate, score) 列表
    sorted_pairs = [
        (cs.candidate, cs.score)
        for cs in sorted(filtered_scores, key=lambda s: (s.candidate.signal_date, -s.score, s.candidate.symbol))
    ]

    all_bars = _bars_by_symbol(market_data.stock_daily)
    run_config = PortfolioRunConfig(
        track_name=track_name,
        initial_cash=config.initial_cash,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    result = run_portfolio_lifecycle(
        scored_candidates=sorted_pairs,
        bars_by_symbol=all_bars,
        run_config=run_config,
        parameters=parameters,
    )

    # 主线过滤跳过审计
    skipped_rows.extend(result.skipped_trades)

    # 无候选审计
    if not filtered_scores:
        skip_reason = (
            "mainline_filtered 过滤后无候选（原始候选可能存在但非强主线）"
            if track_name == "mainline_filtered" and candidate_scores
            else "raw snapshot 未产生候选信号"
        )
        skipped_rows.append({
            "signal_date": config.end_date,
            "track": track_name,
            "symbol": "ALL",
            "reason": skip_reason,
        })

    return result.trades, result.holdings, skipped_rows, result.equity_curve

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
    """敏感性分析占位符函数。

    注意：此函数已由 sensitivity.py 中的真实参数扰动回测替代。
    生产环境中应使用 sensitivity.run_sensitivity_analysis 和 sensitivity.sensitivity_result_to_rows。
    此函数仅用于向后兼容和简化测试。
    """
    return [
        {
            "parameter": "baseline",
            "baseline_value": "ADR-0002",
            "variant_value": "ADR-0002",
            "sample_in_metric": f"{total_return * 100:.2f}",
            "sample_out_metric": f"{total_return * 100:.2f}",
            "overfit_risk": "not_evaluated",
            "accepted": "true",
            "audit_note": "placeholder - use sensitivity.run_sensitivity_analysis for real analysis",
        },
        {
            "parameter": "ab_min_gain_pct",
            "baseline_value": "20%",
            "variant_value": "25%",
            "sample_in_metric": f"{total_return * 100:.2f}",
            "sample_out_metric": f"{total_return * 100:.2f}",
            "overfit_risk": "not_evaluated",
            "accepted": "false",
            "audit_note": "placeholder - use sensitivity.run_sensitivity_analysis for real analysis",
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
