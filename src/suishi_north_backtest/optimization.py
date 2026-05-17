from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from suishi_north_backtest.metrics import EquityMetrics


@dataclass(frozen=True)
class ParameterRun:
    """一次参数组合回测结果。"""

    name: str
    parameters: dict[str, Any]
    in_sample: EquityMetrics
    out_of_sample: EquityMetrics


@dataclass(frozen=True)
class SensitivityResult:
    """单个参数变体相对基线的敏感性结果。"""

    name: str
    parameters: dict[str, Any]
    in_sample_return_delta: float
    out_of_sample_return_delta: float
    status: str
    reason: str


@dataclass(frozen=True)
class SensitivityReport:
    """参数敏感性报告。"""

    baseline_name: str
    results: list[SensitivityResult]


def evaluate_parameter_sensitivity(
    baseline: ParameterRun,
    variants: list[ParameterRun],
) -> SensitivityReport:
    """比较参数变体并标记样本外防过拟合风险。"""

    return SensitivityReport(
        baseline_name=baseline.name,
        results=[_evaluate_variant(baseline, variant) for variant in variants],
    )


def _evaluate_variant(
    baseline: ParameterRun,
    variant: ParameterRun,
) -> SensitivityResult:
    in_sample_delta = (
        variant.in_sample.cumulative_return
        - baseline.in_sample.cumulative_return
    )
    out_of_sample_delta = (
        variant.out_of_sample.cumulative_return
        - baseline.out_of_sample.cumulative_return
    )
    status = "acceptable"
    reason = "样本外未退化"
    if in_sample_delta > 0 and out_of_sample_delta < 0:
        status = "overfit_risk"
        reason = "样本内改善但样本外退化"
    return SensitivityResult(
        name=variant.name,
        parameters=variant.parameters,
        in_sample_return_delta=round(in_sample_delta, 10),
        out_of_sample_return_delta=round(out_of_sample_delta, 10),
        status=status,
        reason=reason,
    )
