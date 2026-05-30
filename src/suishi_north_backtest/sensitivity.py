"""参数敏感性分析模块。

实现真实的参数扰动回测,为 MVP-1 提供参数稳健性评估。

核心功能:
- baseline 参数集运行完整回测
- 为每个参数 variant 运行独立回测
- 分别计算样本内(sample_in)和样本外(sample_out)表现
- 标记过拟合风险:样本内改善但样本外恶化
- 不自动替换默认参数,只提供决策参考
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suishi_north_backtest.config import BacktestConfig
    from suishi_north_backtest.parameters import StrategyParameters
    from suishi_north_backtest.data import Mvp1DataSet

from suishi_north_backtest.config import BacktestConfig


@dataclass(frozen=True)
class VariantResult:
    """单个参数变体的敏感性分析结果。"""
    variant_name: str
    parameter_name: str
    baseline_value: str
    variant_value: str
    return_sample_in: float | None
    return_sample_out: float | None
    overfit_risk: str | None  # None=未评估, "low"=低风险, "medium"=中风险, "high"=高风险
    accepted: bool  # 是否接受该参数设置


@dataclass(frozen=True)
class SensitivityResult:
    """敏感性分析总结果。"""
    baseline_name: str
    baseline_return_sample_in: float | None
    baseline_return_sample_out: float | None
    variant_results: list[VariantResult]
    sample_in_start: str
    sample_in_end: str
    sample_out_start: str
    sample_out_end: str


def create_parameter_variants(baseline: StrategyParameters) -> list[StrategyParameters]:
    """从 baseline 参数创建多个变体，用于敏感性分析。

    根据 issue #37 阶段 10 的要求，创建以下 6 个参数的变体：
    1. AB 最小涨幅：15% 和 25%（baseline 20%)
    2. BC 最大回撤：50% 和 70%（baseline 60%）
    3. C 点距离：6% 和 10%（baseline 8%）
    4. 趋势退出回撤：6% 和 10%（baseline 8%）
    5. 最大持仓天数：20 和 40（baseline 30）
    6. 主线确认天数：2 和 5（baseline 3）

    Args:
        baseline: 基线参数集

    Returns:
        参数变体列表（12个变体）
    """
    variants = []

    # AB 最小涨幅变体
    variants.append(replace(
        baseline,
        name="ab_min_gain-15pct",
        ab_min_gain_pct=0.15,
    ))
    variants.append(replace(
        baseline,
        name="ab_min_gain-25pct",
        ab_min_gain_pct=0.25,
    ))

    # BC 最大回撤变体
    variants.append(replace(
        baseline,
        name="bc_max_retracement-50pct",
        bc_max_retracement_pct=0.50,
    ))
    variants.append(replace(
        baseline,
        name="bc_max_retracement-70pct",
        bc_max_retracement_pct=0.70,
    ))

    # C 点距离变体
    variants.append(replace(
        baseline,
        name="c_distance-6pct",
        signal_distance_to_c_max_pct=0.06,
    ))
    variants.append(replace(
        baseline,
        name="c_distance-10pct",
        signal_distance_to_c_max_pct=0.10,
    ))

    # 趋势退出回撤变体
    variants.append(replace(
        baseline,
        name="trend_exit-6pct",
        trend_exit_pct=0.06,
    ))
    variants.append(replace(
        baseline,
        name="trend_exit-10pct",
        trend_exit_pct=0.10,
    ))

    # 最大持仓天数变体
    variants.append(replace(
        baseline,
        name="max_holding_days-20",
        max_holding_days=20,
    ))
    variants.append(replace(
        baseline,
        name="max_holding_days-40",
        max_holding_days=40,
    ))

    # 主线确认天数变体
    variants.append(replace(
        baseline,
        name="strong_mainline_days-2",
        strong_mainline_days=2,
    ))
    variants.append(replace(
        baseline,
        name="strong_mainline_days-5",
        strong_mainline_days=5,
    ))

    return variants


def _split_equity_by_period(
    equity_curve: list[dict[str, object]],
    period_start: str,
    period_end: str,
) -> float | None:
    """从净值曲线中提取指定区间的收益率。

    计算逻辑:找到 period_start 时或之前最近的一个净值点作为起点,
    period_end 时或之前最近的一个净值点作为终点。

    Args:
        equity_curve: 净值曲线数据
        period_start: 区间开始日期
        period_end: 区间结束日期

    Returns:
        该区间的收益率(None 表示无有效数据)
    """
    # 过滤 mainline_filtered 轨道的数据
    mf_equity = [
        p for p in equity_curve
        if p.get("track") == "mainline_filtered"
    ]
    if not mf_equity:
        return None

    # 找到区间起始和结束的净值
    # 起点:period_start 时或之前最近的一个点
    # 终点:period_end 时或之前最近的一个点
    start_equity = None
    end_equity = None

    for point in mf_equity:
        date = point.get("date", "")
        equity = float(point.get("equity", 0.0))

        if date <= period_start:
            # 更新起点为更接近 period_start 的点
            start_equity = equity
        elif period_start < date <= period_end:
            # 在区间内,如果没有终点则设置
            if end_equity is None:
                end_equity = equity
            # 始终更新终点为最新的点
            end_equity = equity

    if start_equity is None or end_equity is None or start_equity == 0:
        return None

    return (end_equity - start_equity) / start_equity


def _extract_parameter_name(variant_name: str) -> tuple[str, str, str]:
    """从 variant 名称提取参数名、baseline 值和 variant 值。"""
    # 格式: "ab_min_gain-15pct" -> ("ab_min_gain_pct", "20%", "15%")
    if "ab_min_gain" in variant_name:
        if "15pct" in variant_name:
            return "ab_min_gain_pct", "20%", "15%"
        elif "25pct" in variant_name:
            return "ab_min_gain_pct", "20%", "25%"
    elif "bc_max_retracement" in variant_name:
        if "50pct" in variant_name:
            return "bc_max_retracement_pct", "60%", "50%"
        elif "70pct" in variant_name:
            return "bc_max_retracement_pct", "60%", "70%"
    elif "c_distance" in variant_name:
        if "6pct" in variant_name:
            return "signal_distance_to_c_max_pct", "8%", "6%"
        elif "10pct" in variant_name:
            return "signal_distance_to_c_max_pct", "8%", "10%"
    elif "trend_exit" in variant_name:
        if "6pct" in variant_name:
            return "trend_exit_pct", "8%", "6%"
        elif "10pct" in variant_name:
            return "trend_exit_pct", "8%", "10%"
    elif "max_holding_days" in variant_name:
        if "20" in variant_name:
            return "max_holding_days", "30", "20"
        elif "40" in variant_name:
            return "max_holding_days", "30", "40"
    elif "strong_mainline" in variant_name:
        if "2" in variant_name:
            return "strong_mainline_days", "3", "2"
        elif "5" in variant_name:
            return "strong_mainline_days", "3", "5"

    return "unknown", "unknown", "unknown"


def _assess_overfit_risk(
    return_sample_in: float | None,
    return_sample_out: float | None,
    baseline_return_sample_in: float | None,
    baseline_return_sample_out: float | None,
) -> str | None:
    """评估参数变体的过拟合风险。

    判断逻辑:
    - 如果样本内改善且样本外恶化:high 风险
    - 如果样本内改善但样本外也改善:low 风险
    - 如果样本内恶化:low 风险(参数变差,不会引起过拟合)

    Args:
        return_sample_in: variant 样本内收益
        return_sample_out: variant 样本外收益
        baseline_return_sample_in: baseline 样本内收益
        baseline_return_sample_out: baseline 样本外收益

    Returns:
        风险等级:"low", "medium", "high" 或 None
    """
    if any(v is None for v in [
        return_sample_in, return_sample_out,
        baseline_return_sample_in, baseline_return_sample_out
    ]):
        return None

    sample_in_improves = return_sample_in > baseline_return_sample_in
    sample_out_worsens = return_sample_out < baseline_return_sample_out

    if sample_in_improves and sample_out_worsens:
        # 样本内改善、样本外恶化:典型过拟合
        sample_in_delta = return_sample_in - baseline_return_sample_in
        sample_out_delta = baseline_return_sample_out - return_sample_out

        if sample_in_delta > 0.05 and sample_out_delta > 0.05:
            return "high"
        else:
            return "medium"
    elif sample_in_improves:
        # 样本内和样本外都改善
        return "low"
    else:
        # 样本内恶化,不会引起过拟合
        return "low"


def _determine_accepted(
    overfit_risk: str | None,
    return_sample_out: float | None,
    baseline_return_sample_out: float | None,
) -> bool:
    """决定是否接受该参数变体。

    默认不接受任何变体,只作为分析参考。

    Args:
        overfit_risk: 过拟合风险等级
        return_sample_out: variant 样本外收益
        baseline_return_sample_out: baseline 样本外收益

    Returns:
        是否接受(目前默认 False)
    """
    # MVP-1 阶段不自动接受任何参数变体
    return False


def run_sensitivity_analysis(
    snapshot_dir: Path,
    config: BacktestConfig,
    baseline_params: StrategyParameters,
    parameter_variants: list[StrategyParameters],
    sample_in_end: str,
    sample_out_start: str,
    run_backtest_fn,
) -> SensitivityResult:
    """运行参数敏感性分析。

    流程:
    1. 使用 baseline 参数运行完整回测
    2. 对每个 variant 参数运行独立回测
    3. 计算每个参数集的样本内和样本外收益率
    4. 评估过拟合风险
    5. 生成敏感性分析报告

    Args:
        snapshot_dir: raw a-stock-data 快照目录
        config: 回测配置
        baseline_params: 基线参数集
        parameter_variants: 参数变体列表
        sample_in_end: 样本内结束日期
        sample_out_start: 样本外开始日期
        run_backtest_fn: 回测函数,签名为 (snapshot_dir, config, parameters) -> Mvp1DataSet

    Returns:
        SensitivityResult 包含所有参数集的表现和风险评估
    """
    # 样本切分
    sample_in_start = config.start_date
    sample_out_end = config.end_date

    # 1. 运行 baseline 回测
    baseline_dataset = run_backtest_fn(
        raw_snapshot_dir=snapshot_dir,
        config=config,
        parameters=baseline_params,
    )

    # 计算 baseline 样本内和样本外收益
    baseline_return_sample_in = _split_equity_by_period(
        baseline_dataset.equity_curve,
        sample_in_start,
        sample_in_end,
    )
    baseline_return_sample_out = _split_equity_by_period(
        baseline_dataset.equity_curve,
        sample_out_start,
        sample_out_end,
    )

    # 2. 运行所有 variant 回测
    variant_results = []

    for variant in parameter_variants:
        # 运行 variant 回测
        variant_dataset = run_backtest_fn(
            raw_snapshot_dir=snapshot_dir,
            config=config,
            parameters=variant,
        )

        # 计算 variant 样本内和样本外收益
        variant_return_sample_in = _split_equity_by_period(
            variant_dataset.equity_curve,
            sample_in_start,
            sample_in_end,
        )
        variant_return_sample_out = _split_equity_by_period(
            variant_dataset.equity_curve,
            sample_out_start,
            sample_out_end,
        )

        # 评估过拟合风险
        overfit_risk = _assess_overfit_risk(
            return_sample_in=variant_return_sample_in,
            return_sample_out=variant_return_sample_out,
            baseline_return_sample_in=baseline_return_sample_in,
            baseline_return_sample_out=baseline_return_sample_out,
        )

        # 决定是否接受
        accepted = _determine_accepted(
            overfit_risk=overfit_risk,
            return_sample_out=variant_return_sample_out,
            baseline_return_sample_out=baseline_return_sample_out,
        )

        # 提取参数信息
        param_name, baseline_value, variant_value = _extract_parameter_name(variant.name)

        variant_result = VariantResult(
            variant_name=variant.name,
            parameter_name=param_name,
            baseline_value=baseline_value,
            variant_value=variant_value,
            return_sample_in=variant_return_sample_in,
            return_sample_out=variant_return_sample_out,
            overfit_risk=overfit_risk,
            accepted=accepted,
        )
        variant_results.append(variant_result)

    # 3. 返回敏感性分析结果
    return SensitivityResult(
        baseline_name=baseline_params.name,
        baseline_return_sample_in=baseline_return_sample_in,
        baseline_return_sample_out=baseline_return_sample_out,
        variant_results=variant_results,
        sample_in_start=sample_in_start,
        sample_in_end=sample_in_end,
        sample_out_start=sample_out_start,
        sample_out_end=sample_out_end,
    )


def sensitivity_result_to_rows(result: SensitivityResult) -> list[dict[str, object]]:
    """将敏感性分析结果转换为 CSV 行格式,用于 sensitivity.csv 输出。"""
    rows = []

    # baseline 行
    rows.append({
        "parameter": "baseline",
        "baseline_value": result.baseline_name,
        "variant_value": result.baseline_name,
        "sample_in_metric": f"{result.baseline_return_sample_in * 100:.2f}%" if result.baseline_return_sample_in is not None else "N/A",
        "sample_out_metric": f"{result.baseline_return_sample_out * 100:.2f}%" if result.baseline_return_sample_out is not None else "N/A",
        "overfit_risk": "N/A",
        "accepted": "true",
        "audit_note": f"baseline 参数,样本内 [{result.sample_in_start}, {result.sample_in_end}],样本外 [{result.sample_out_start}, {result.sample_out_end}]",
    })

    # variant 行
    for vr in result.variant_results:
        sample_in_str = f"{vr.return_sample_in * 100:.2f}%" if vr.return_sample_in is not None else "N/A"
        sample_out_str = f"{vr.return_sample_out * 100:.2f}%" if vr.return_sample_out is not None else "N/A"
        risk_str = vr.overfit_risk if vr.overfit_risk else "not_evaluated"

        rows.append({
            "parameter": vr.parameter_name,
            "baseline_value": vr.baseline_value,
            "variant_value": vr.variant_value,
            "sample_in_metric": sample_in_str,
            "sample_out_metric": sample_out_str,
            "overfit_risk": risk_str,
            "accepted": "true" if vr.accepted else "false",
            "audit_note": f"参数扰动真实回测结果,{vr.variant_name}",
        })

    return rows