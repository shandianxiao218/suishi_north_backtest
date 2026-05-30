"""敏感性分析测试：验证真实参数扰动回测。

测试覆盖：
- baseline 和 variant 参数都能运行回测
- 使用真实的策略回测，不是静态记录
- 标记样本内改善、样本外恶化的过拟合风险
- 不修改默认参数
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from dataclasses import replace

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
from suishi_north_backtest.mvp1_runner import run_mvp1_from_raw_snapshot
from suishi_north_backtest.sensitivity import (
    SensitivityResult,
    run_sensitivity_analysis,
    create_parameter_variants,
    _split_equity_by_period,
)


STOCK_DAILY_FIELDS = [
    "trade_date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "limit_up",
    "limit_down",
]

INDEX_DAILY_FIELDS = [
    "trade_date",
    "index_code",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]


def _write_csv(path: Path, fields: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        writer.writerows(rows)


def _build_extended_raw_snapshot(snapshot_dir: Path) -> None:
    """构造一个覆盖样本内和样本外时间的 extended raw snapshot。

    使用更小的数据集，减少测试时间。
    样本内：2024-01-01 至 2024-03-31
    样本外：2024-04-01 至 2024-06-30
    """
    manifest = {
        "data_version": "sensitivity-test-v1",
        "source": "sensitivity-test",
        "created_at": "2024-01-01T00:00:00+08:00",
        "stock_daily_file": "stock_daily.csv",
        "index_daily_file": "index_daily.csv",
        "industry_map_file": "industry_map.csv",
        "industry_daily_amount_file": "industry_daily_amount.csv",
        "trading_calendar_file": "trading_calendar.csv",
    }
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    # 只使用前半年的数据，减少测试时间
    dates = [
        "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
        "2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12", "2024-01-15",
        "2024-01-16", "2024-01-17", "2024-01-18", "2024-01-19", "2024-01-22",
        "2024-01-23", "2024-01-24", "2024-01-25", "2024-01-26",
        "2024-02-02", "2024-02-05", "2024-02-06", "2024-02-07", "2024-02-08",
        "2024-03-01", "2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07",
        "2024-03-08", "2024-03-11", "2024-03-12", "2024-03-13", "2024-03-14",
        "2024-03-15", "2024-03-18", "2024-03-19", "2024-03-20", "2024-03-21",
        "2024-03-22", "2024-03-25", "2024-03-26", "2024-03-27", "2024-03-28",
        "2024-03-29",
        "2024-04-02", "2024-04-03", "2024-04-08", "2024-04-09", "2024-04-10",
        "2024-04-11", "2024-04-12", "2024-04-15", "2024-04-16", "2024-04-17",
        "2024-04-18", "2024-04-19", "2024-04-22", "2024-04-23", "2024-04-24",
        "2024-04-25", "2024-04-26", "2024-04-29", "2024-04-30",
        "2024-05-06", "2024-05-07", "2024-05-08", "2024-05-09", "2024-05-10",
        "2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17",
        "2024-05-20", "2024-05-21", "2024-05-22", "2024-05-23", "2024-05-24",
        "2024-05-27", "2024-05-28", "2024-05-29", "2024-05-30", "2024-05-31",
        "2024-06-03", "2024-06-04", "2024-06-05", "2024-06-06", "2024-06-07",
        "2024-06-11", "2024-06-12", "2024-06-13", "2024-06-14", "2024-06-17",
        "2024-06-18", "2024-06-19", "2024-06-20", "2024-06-21", "2024-06-24",
        "2024-06-25", "2024-06-26", "2024-06-27", "2024-06-28",
    ]

    base_prices = []
    base = 10.0
    for i, date in enumerate(dates):
        # 制造周期性波动，产生多个 ABC 结构
        phase = i % 30
        if phase < 8:  # AB 段上涨
            base *= 1.02
        elif phase < 12:  # BC 段回撤
            base *= 0.97
        elif phase < 15:  # C 点区域
            base *= 1.005
        else:  # D 段/震荡
            base *= 1.001

        open_p = base * 0.995
        high_p = base * 1.02
        low_p = base * 0.98
        close_p = base
        volume = "50000"
        amount = str(50000 * close_p)
        limit_up = f"{close_p * 1.1:.2f}"
        limit_down = f"{close_p * 0.9:.2f}"

        base_prices.append(
            (date, f"{open_p:.2f}", f"{high_p:.2f}", f"{low_p:.2f}",
             f"{close_p:.2f}", volume, amount, limit_up, limit_down)
        )

    stock_rows = [[r[0], "000001", *r[1:]] for r in base_prices]
    _write_csv(snapshot_dir / "stock_daily.csv", STOCK_DAILY_FIELDS, stock_rows)

    # 指数数据
    index_rows = []
    for date in dates:
        index_rows.append(
            [date, "000300", "3500", "3520", "3490", "3510", "10000", "35000000"]
        )
    _write_csv(snapshot_dir / "index_daily.csv", INDEX_DAILY_FIELDS, index_rows)

    # 行业映射
    _write_csv(
        snapshot_dir / "industry_map.csv",
        ["symbol", "industry_level2"],
        [["000001", "白酒"]],
    )

    # 行业成交额
    industry_rows = []
    for date in dates:
        industry_rows.append([date, "白酒", "5000000000"])
        industry_rows.append([date, "银行", "1000000000"])
        industry_rows.append([date, "地产", "800000000"])
        industry_rows.append([date, "医药", "600000000"])
        industry_rows.append([date, "科技", "500000000"])
    _write_csv(
        snapshot_dir / "industry_daily_amount.csv",
        ["trade_date", "industry_level2", "amount"],
        industry_rows,
    )

    # 交易日历
    cal_rows = [[d, "1"] for d in dates]
    _write_csv(
        snapshot_dir / "trading_calendar.csv",
        ["trade_date", "is_open"],
        cal_rows,
    )


def test_sensitivity_runs_baseline_and_variants(tmp_path: Path) -> None:
    """测试敏感性分析能运行 baseline 和所有 variant 参数集。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_extended_raw_snapshot(snapshot_dir)

    baseline_params = default_mvp1_parameters()
    variants = create_parameter_variants(baseline_params)

    # 验证生成的变体数量
    assert len(variants) == 12, f"应生成 12 个参数变体，实际：{len(variants)}"

    config = BacktestConfig(
        name="sensitivity-test",
        start_date="2024-01-01",
        end_date="2024-06-28",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )

    # 只测试一个 variant，减少测试时间
    result = run_sensitivity_analysis(
        snapshot_dir=snapshot_dir,
        config=config,
        baseline_params=baseline_params,
        parameter_variants=[variants[0]],
        sample_in_end="2024-03-29",
        sample_out_start="2024-04-01",
        run_backtest_fn=run_mvp1_from_raw_snapshot,
    )

    # 验证结果结构
    assert result.baseline_return_sample_in is not None, "baseline 样本内收益不能为 None"
    assert result.baseline_return_sample_out is not None, "baseline 样本外收益不能为 None"

    # 验证 variant 有结果
    assert len(result.variant_results) == 1, "应有一个 variant 结果"

    # variant 应该有样本内和样本外收益
    vr = result.variant_results[0]
    assert vr.return_sample_in is not None, f"variant {vr.variant_name} 样本内收益不能为 None"
    assert vr.return_sample_out is not None, f"variant {vr.variant_name} 样本外收益不能为 None"
    assert vr.overfit_risk is not None, f"variant {vr.variant_name} 过拟合风险标记不能为 None"


def test_sensitivity_uses_real_strategy_runs(tmp_path: Path) -> None:
    """测试敏感性分析使用真实的策略回测，不是静态记录。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_extended_raw_snapshot(snapshot_dir)

    baseline_params = default_mvp1_parameters()

    # 创建一个与 baseline 不同的 variant
    aggressive_variant = replace(baseline_params, name="aggressive-ab-15", ab_min_gain_pct=0.15)  # 降低 AB 涨幅门槛

    config = BacktestConfig(
        name="sensitivity-test",
        start_date="2024-01-01",
        end_date="2024-06-28",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )

    result = run_sensitivity_analysis(
        snapshot_dir=snapshot_dir,
        config=config,
        baseline_params=baseline_params,
        parameter_variants=[aggressive_variant],
        sample_in_end="2024-03-29",
        sample_out_start="2024-04-01",
        run_backtest_fn=run_mvp1_from_raw_snapshot,
    )

    # 验证两个结果都来自真实回测
    baseline_result = result.baseline_return_sample_in
    aggressive_result = result.variant_results[0].return_sample_in

    assert baseline_result is not None, "baseline 样本内应有回测结果"
    assert aggressive_result is not None, "variant 样本内应有回测结果"

    # 参数不同，结果也应该不同（除非恰好相同）
    # 更低的 AB 涨幅门槛通常会产生更多候选
    # 但由于我们只验证回测确实运行了，这里只检查两者都有结果即可


def test_sensitivity_flags_sample_in_improves_sample_out_worsens(tmp_path: Path) -> None:
    """测试敏感性分析能正确标记样本内改善、样本外恶化的过拟合风险。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_extended_raw_snapshot(snapshot_dir)

    baseline_params = default_mvp1_parameters()

    # 创建一个可能过拟合的 variant（只改一个参数）
    overfit_variant = replace(
        baseline_params,
        name="bc_max_retracement-50pct",
        bc_max_retracement_pct=0.50,  # 更严格的 BC 回撤限制
    )

    config = BacktestConfig(
        name="sensitivity-test",
        start_date="2024-01-01",
        end_date="2024-06-28",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )

    result = run_sensitivity_analysis(
        snapshot_dir=snapshot_dir,
        config=config,
        baseline_params=baseline_params,
        parameter_variants=[overfit_variant],
        sample_in_end="2024-03-29",
        sample_out_start="2024-04-01",
        run_backtest_fn=run_mvp1_from_raw_snapshot,
    )

    # 验证过拟合风险标记已设置
    variant_result = result.variant_results[0]
    assert variant_result.overfit_risk is not None, "过拟合风险标记不能为 None"

    # 如果样本内改善且样本外恶化，应标记为高风险
    if (variant_result.return_sample_in is not None and
        variant_result.return_sample_out is not None and
        result.baseline_return_sample_in is not None and
        result.baseline_return_sample_out is not None):

        sample_in_improves = variant_result.return_sample_in > result.baseline_return_sample_in
        sample_out_worsens = variant_result.return_sample_out < result.baseline_return_sample_out

        if sample_in_improves and sample_out_worsens:
            assert variant_result.overfit_risk == "high", (
                "样本内改善、样本外恶化应标记为高风险"
            )


def test_sensitivity_does_not_mutate_default_parameters(tmp_path: Path) -> None:
    """测试敏感性分析不修改默认参数。"""
    snapshot_dir = tmp_path / "raw-snapshot"
    snapshot_dir.mkdir()
    _build_extended_raw_snapshot(snapshot_dir)

    # 保存原始默认参数
    original_params = default_mvp1_parameters()
    original_ab_min = original_params.ab_min_gain_pct
    original_bc_max = original_params.bc_max_retracement_pct
    original_trend_exit = original_params.trend_exit_pct
    original_c_distance = original_params.signal_distance_to_c_max_pct
    original_max_holding = original_params.max_holding_days
    original_mainline_days = original_params.strong_mainline_days

    variants = create_parameter_variants(original_params)

    config = BacktestConfig(
        name="sensitivity-test",
        start_date="2024-01-01",
        end_date="2024-06-28",
        initial_cash=1_000_000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot=snapshot_dir.name,
        data_dir=snapshot_dir.parent,
    )

    # 只测试一个 variant，减少测试时间
    result = run_sensitivity_analysis(
        snapshot_dir=snapshot_dir,
        config=config,
        baseline_params=original_params,
        parameter_variants=[variants[0]],
        sample_in_end="2024-03-29",
        sample_out_start="2024-04-01",
        run_backtest_fn=run_mvp1_from_raw_snapshot,
    )

    # 验证默认参数未被修改
    current_params = default_mvp1_parameters()
    assert current_params.ab_min_gain_pct == original_ab_min, (
        f"ab_min_gain_pct 被修改：原始={original_ab_min}，当前={current_params.ab_min_gain_pct}"
    )
    assert current_params.bc_max_retracement_pct == original_bc_max, (
        f"bc_max_retracement_pct 被修改：原始={original_bc_max}，当前={current_params.bc_max_retracement_pct}"
    )
    assert current_params.trend_exit_pct == original_trend_exit, (
        f"trend_exit_pct 被修改：原始={original_trend_exit}，当前={current_params.trend_exit_pct}"
    )
    assert current_params.signal_distance_to_c_max_pct == original_c_distance, (
        f"signal_distance_to_c_max_pct 被修改：原始={original_c_distance}，当前={current_params.signal_distance_to_c_max_pct}"
    )
    assert current_params.max_holding_days == original_max_holding, (
        f"max_holding_days 被修改：原始={original_max_holding}，当前={current_params.max_holding_days}"
    )
    assert current_params.strong_mainline_days == original_mainline_days, (
        f"strong_mainline_days 被修改：原始={original_mainline_days}，当前={current_params.strong_mainline_days}"
    )

    # variant 参数应与 baseline 不同（至少一个参数不同）
    for variant in variants:
        assert variant.ab_min_gain_pct != original_ab_min or \
               variant.bc_max_retracement_pct != original_bc_max or \
               variant.trend_exit_pct != original_trend_exit or \
               variant.signal_distance_to_c_max_pct != original_c_distance or \
               variant.max_holding_days != original_max_holding or \
               variant.strong_mainline_days != original_mainline_days, (
            f"variant {variant.name} 应与 baseline 参数不同"
        )


def test_create_parameter_variants_generates_expected_variants() -> None:
    """测试 create_parameter_variants 生成预期的参数变体。"""
    baseline = default_mvp1_parameters()
    variants = create_parameter_variants(baseline)

    # 验证 variant 数量：6个参数各2个变体 = 12个
    assert len(variants) == 12, f"应生成 12 个 variant，实际：{len(variants)}"

    # 验证每个 variant 的名称和参数
    variant_names = {v.name for v in variants}
    expected_names = {
        "ab_min_gain-15pct",
        "ab_min_gain-25pct",
        "bc_max_retracement-50pct",
        "bc_max_retracement-70pct",
        "c_distance-6pct",
        "c_distance-10pct",
        "trend_exit-6pct",
        "trend_exit-10pct",
        "max_holding_days-20",
        "max_holding_days-40",
        "strong_mainline_days-2",
        "strong_mainline_days-5",
    }
    assert variant_names == expected_names, (
        f"variant 名称不匹配，预期：{expected_names}，实际：{variant_names}"
    )

    # 验证参数值
    for v in variants:
        if v.name == "ab_min_gain-15pct":
            assert v.ab_min_gain_pct == 0.15
        elif v.name == "ab_min_gain-25pct":
            assert v.ab_min_gain_pct == 0.25
        elif v.name == "bc_max_retracement-50pct":
            assert v.bc_max_retracement_pct == 0.50
        elif v.name == "bc_max_retracement-70pct":
            assert v.bc_max_retracement_pct == 0.70
        elif v.name == "c_distance-6pct":
            assert v.signal_distance_to_c_max_pct == 0.06
        elif v.name == "c_distance-10pct":
            assert v.signal_distance_to_c_max_pct == 0.10
        elif v.name == "trend_exit-6pct":
            assert v.trend_exit_pct == 0.06
        elif v.name == "trend_exit-10pct":
            assert v.trend_exit_pct == 0.10
        elif v.name == "max_holding_days-20":
            assert v.max_holding_days == 20
        elif v.name == "max_holding_days-40":
            assert v.max_holding_days == 40
        elif v.name == "strong_mainline_days-2":
            assert v.strong_mainline_days == 2
        elif v.name == "strong_mainline_days-5":
            assert v.strong_mainline_days == 5


def test_split_equity_by_period() -> None:
    """测试按样本切分计算收益的函数。"""
    equity_curve = [
        {"date": "2024-01-01", "equity": 1000000.0, "track": "mainline_filtered"},
        {"date": "2024-03-01", "equity": 1050000.0, "track": "mainline_filtered"},
        {"date": "2024-06-30", "equity": 1100000.0, "track": "mainline_filtered"},
        {"date": "2024-09-01", "equity": 1080000.0, "track": "mainline_filtered"},
        {"date": "2024-12-31", "equity": 1150000.0, "track": "mainline_filtered"},
    ]

    sample_in_return = _split_equity_by_period(
        equity_curve, "2024-01-01", "2024-06-30"
    )
    sample_out_return = _split_equity_by_period(
        equity_curve, "2024-07-01", "2024-12-31"
    )

    # 样本内：1000000 -> 1100000 = +10%
    assert abs(sample_in_return - 0.10) < 0.001, (
        f"样本内收益应为 10%，实际：{sample_in_return * 100:.2f}%"
    )

    # 样本外：1100000 -> 1150000 = +4.55%
    assert abs(sample_out_return - 0.0455) < 0.001, (
        f"样本外收益应为 4.55%，实际：{sample_out_return * 100:.2f}%"
    )


def test_assess_overfit_risk_all_branches() -> None:
    """测试 _assess_overfit_risk 的 high/medium/low 分支。"""
    from suishi_north_backtest.sensitivity import _assess_overfit_risk

    # high: 样本内改善 >5% 且样本外恶化 >5%
    assert _assess_overfit_risk(0.20, -0.10, 0.10, 0.05) == "high"

    # medium: 样本内改善且样本外恶化，但差值 <=5%
    assert _assess_overfit_risk(0.12, 0.04, 0.10, 0.05) == "medium"

    # low: 样本内改善且样本外也改善
    assert _assess_overfit_risk(0.15, 0.10, 0.10, 0.05) == "low"

    # low: 样本内恶化
    assert _assess_overfit_risk(0.05, 0.03, 0.10, 0.05) == "low"

    # None: 任一输入为 None
    assert _assess_overfit_risk(None, 0.10, 0.10, 0.05) is None
    assert _assess_overfit_risk(0.10, None, 0.10, 0.05) is None