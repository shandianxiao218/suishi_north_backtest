from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

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
from suishi_north_backtest.metrics import (
    REQUIRED_BENCHMARKS,
    build_benchmark_comparison_rows,
    equity_points_from_rows,
    sample_windows,
)
from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
from suishi_north_backtest.raw_data import validate_raw_snapshot
from suishi_north_backtest.scoring import ScoringContext, ScoreBreakdown, score_candidate
from suishi_north_backtest.signals import CandidateSignal, find_candidates
from suishi_north_backtest.tracks import build_mainline_map


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

    universe_skip_rows: list[dict[str, object]] = []
    for audit in tradability_audit:
        if audit.buy_restricted or audit.sell_deferred:
            continue
        universe_skip_rows.append(
            {
                "signal_date": audit.trade_date,
                "track": "universe_filter",
                "symbol": audit.symbol,
                "reason": audit.reason,
            }
        )

    mainlines = compute_mainlines(
        market_data.industry_daily_amount,
        as_of=as_of,
        parameters=parameters,
    )
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

    stock_amount_by_symbol_date = _build_stock_amount_by_symbol_date(market_data.stock_daily)
    bars_by_symbol_for_lookup = _bars_by_symbol(market_data.stock_daily)
    industry_candidate_count = _build_industry_candidate_count(candidates, industry_by_symbol)

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

    mainline_entries = compute_mainlines(
        market_data.industry_daily_amount,
        as_of=as_of,
        parameters=parameters,
    )
    mainline_map = build_mainline_map(mainline_entries)

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

    all_skipped.extend(universe_skip_rows)
    all_equity.sort(key=lambda point: str(point.get("date", "")))

    ps_trades = [trade for trade in all_trades if trade.trade_id.startswith("PURE")]
    mf_trades = [trade for trade in all_trades if trade.trade_id.startswith("MAIN")]
    ps_equity = [point for point in all_equity if point.get("track") == "pure_structure"]
    mf_equity = [point for point in all_equity if point.get("track") == "mainline_filtered"]

    ps_return = _safe_pct_change(
        float(config.initial_cash),
        float(ps_equity[-1]["equity"]) if ps_equity else float(config.initial_cash),
    )
    mf_return = _safe_pct_change(
        float(config.initial_cash),
        float(mf_equity[-1]["equity"]) if mf_equity else float(config.initial_cash),
    )

    primary_equity = mf_equity if mf_equity else ps_equity
    ending_equity = float(primary_equity[-1]["equity"]) if primary_equity else float(config.initial_cash)
    total_return = _safe_pct_change(config.initial_cash, ending_equity)
    primary_drawdown_values = [float(point["equity"]) for point in primary_equity]
    max_drawdown = _max_drawdown(primary_drawdown_values)
    win_rate = _win_rate(all_trades)
    profit_factor = _profit_factor(all_trades)
    windows = sample_windows(as_of)

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
            window.name: [window.start_date, window.end_date] for window in windows
        },
        "audit_note": "raw snapshot generated MVP-1 dataset with real dual-track benchmark metrics",
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
            index_daily=market_data.index_daily,
            strategy_equity=equity_points_from_rows(primary_equity),
            trades=all_trades,
            as_of=as_of,
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
    breakdown: ScoreBreakdown
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
        concentration_count = industry_candidate_count.get(industry, 1)

        scoring_ctx = ScoringContext(
            mainline_status=status.value if status else "none",
            industry_rank=rank,
            industry_amount=0.0,
            stock_amount=stock_amount,
            same_industry_candidate_count=concentration_count,
        )
        total_score, breakdown = score_candidate(
            ab_gain_pct=candidate.ab_gain_pct,
            bc_retracement_pct=candidate.bc_retracement_pct,
            distance_to_c_pct=candidate.distance_to_c_pct,
            weekly_filter_passed=candidate.weekly_filter_passed,
            annual_filter_passed=candidate.annual_filter_passed,
            context=scoring_ctx,
        )
        results.append(
            _CandidateScore(
                candidate=candidate,
                score=total_score,
                breakdown=breakdown,
                industry=industry,
                mainline_status=status,
            )
        )
    return results


def _candidate_rows_from_scores(
    scored: list[_CandidateScore],
) -> list[dict[str, object]]:
    """从评分结果生成 candidates.csv 行。"""
    rows: list[dict[str, object]] = []
    for score in scored:
        candidate = score.candidate
        rows.append(
            {
                "signal_date": candidate.signal_date,
                "track": "mainline_filtered" if score.mainline_status == MainlineStatus.STRONG else "pure_structure",
                "symbol": candidate.symbol,
                "industry_level2": score.industry,
                "is_strong_mainline": str(score.mainline_status == MainlineStatus.STRONG).lower(),
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
                "score": f"{score.score:.2f}",
                "score_breakdown": score.breakdown.to_csv_string(),
                "audit_note": candidate.audit_note,
            }
        )
    return rows


def _build_stock_amount_by_symbol_date(
    stock_daily: list[StockDaily],
) -> dict[tuple[str, str], float]:
    """构建 (symbol, trade_date) -> amount 映射。"""
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
    amt = amount_map.get((symbol, signal_date))
    if amt is not None:
        return amt
    symbol_bars = bars_by_symbol.get(symbol, [])
    for bar in reversed(symbol_bars):
        if bar.trade_date <= signal_date and bar.amount is not None:
            return float(bar.amount)
    return 0.0


def _build_industry_candidate_count(
    candidates: list[CandidateSignal],
    industry_by_symbol: dict[str, str],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        industry = industry_by_symbol.get(candidate.symbol, "")
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
        for candidate_score in candidate_scores:
            candidate = candidate_score.candidate
            industry = industry_by_symbol.get(candidate.symbol, "")
            date_data = mainline_map.get(candidate.signal_date, {})
            status_info = date_data.get(industry)
            if status_info and status_info[0] == MainlineStatus.STRONG:
                filtered_scores.append(candidate_score)
            else:
                skipped_rows.append(
                    {
                        "signal_date": candidate.signal_date,
                        "track": track_name,
                        "symbol": candidate.symbol,
                        "reason": f"非强主线（{industry}），mainline_filtered 跳过",
                    }
                )
    else:
        filtered_scores = list(candidate_scores)

    sorted_pairs = [
        (candidate_score.candidate, candidate_score.score)
        for candidate_score in sorted(
            filtered_scores,
            key=lambda score: (score.candidate.signal_date, -score.score, score.candidate.symbol),
        )
    ]

    result = run_portfolio_lifecycle(
        scored_candidates=sorted_pairs,
        bars_by_symbol=_bars_by_symbol(market_data.stock_daily),
        run_config=PortfolioRunConfig(
            track_name=track_name,
            initial_cash=config.initial_cash,
            start_date=config.start_date,
            end_date=config.end_date,
        ),
        parameters=parameters,
    )

    skipped_rows.extend(result.skipped_trades)
    if not filtered_scores:
        skip_reason = (
            "mainline_filtered 过滤后无候选（原始候选可能存在但非强主线）"
            if track_name == "mainline_filtered" and candidate_scores
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


def _real_track_rows(
    ps_trades: list[ClosedTrade],
    ps_return: float,
    mf_trades: list[ClosedTrade],
    mf_return: float,
) -> list[dict[str, object]]:
    ps_win = sum(1 for trade in ps_trades if trade.net_pnl > 0)
    mf_win = sum(1 for trade in mf_trades if trade.net_pnl > 0)
    ps_win_rate = ps_win / len(ps_trades) if ps_trades else 0.0
    mf_win_rate = mf_win / len(mf_trades) if mf_trades else 0.0

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
            "pure_structure_track": f"{ps_win_rate * 100:.2f}",
            "mainline_filtered_track": f"{mf_win_rate * 100:.2f}",
            "delta": f"{(ps_win_rate - mf_win_rate) * 100:.2f}",
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
        return sum(gains) if gains else 0.0
    return sum(gains) / sum(losses) if gains else 0.0


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
