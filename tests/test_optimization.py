from __future__ import annotations

from suishi_north_backtest.metrics import EquityMetrics
from suishi_north_backtest.optimization import (
    ParameterRun,
    evaluate_parameter_sensitivity,
)


def test_flags_variant_that_improves_in_sample_but_degrades_out_of_sample() -> None:
    baseline = ParameterRun(
        name="baseline",
        parameters={"max_bc_retrace": 0.60},
        in_sample=EquityMetrics(0.20, 0.10, 2.0),
        out_of_sample=EquityMetrics(0.10, 0.08, 1.25),
    )
    aggressive = ParameterRun(
        name="aggressive",
        parameters={"max_bc_retrace": 0.80},
        in_sample=EquityMetrics(0.35, 0.10, 3.5),
        out_of_sample=EquityMetrics(0.02, 0.12, 0.17),
    )

    report = evaluate_parameter_sensitivity(baseline, [aggressive])

    assert report.baseline_name == "baseline"
    assert report.results[0].name == "aggressive"
    assert report.results[0].in_sample_return_delta == 0.15
    assert report.results[0].out_of_sample_return_delta == -0.08
    assert report.results[0].status == "overfit_risk"
    assert report.results[0].reason == "样本内改善但样本外退化"


def test_accepts_variant_when_out_of_sample_does_not_degrade() -> None:
    baseline = ParameterRun(
        name="baseline",
        parameters={"risk_per_trade": 0.01},
        in_sample=EquityMetrics(0.20, 0.10, 2.0),
        out_of_sample=EquityMetrics(0.10, 0.08, 1.25),
    )
    conservative = ParameterRun(
        name="conservative",
        parameters={"risk_per_trade": 0.005},
        in_sample=EquityMetrics(0.18, 0.07, 2.57),
        out_of_sample=EquityMetrics(0.11, 0.06, 1.83),
    )

    report = evaluate_parameter_sensitivity(baseline, [conservative])

    assert report.results[0].status == "acceptable"
    assert report.results[0].reason == "样本外未退化"
    assert report.results[0].out_of_sample_return_delta == 0.01
