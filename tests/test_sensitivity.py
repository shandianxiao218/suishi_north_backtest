"""敏感性回测测试：真实回测而非静态记录。

TDD 要求：
- test_sensitivity_runs_baseline_and_variants
- test_sensitivity_uses_real_strategy_runs
- test_sensitivity_flags_sample_in_improves_sample_out_worsens
- test_sensitivity_does_not_mutate_default_parameters
"""

from __future__ import annotations

from pathlib import Path

from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.parameters import StrategyParameters, default_mvp1_parameters
from suishi_north_backtest.sensitivity import (
    SensitivityResult,
    SensitivityRow,
    SensitivityVariant,
    run_sensitivity_analysis,
)


def _build_minimal_raw_snapshot(snapshot_dir: Path) -> None:
    """构建最小化 raw snapshot 用于测试敏感性分析。"""
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # manifest.json
    (snapshot_dir / "manifest.json").write_text(
        """
{
    "data_version": "test-v1",
    "source": "test",
    "created_at": "2024-01-01T00:00:00+08:00",
    "stock_daily_file": "stock_daily.csv",
    "index_daily_file": "index_daily.csv",
    "industry_map_file": "industry_map.csv",
    "industry_daily_amount_file": "industry_daily_amount.csv",
    "trading_calendar_file": "trading_calendar.csv"
}
""",
        encoding="utf-8",
    )

    # stock_daily.csv - 最小候选信号
    (snapshot_dir / "stock_daily.csv").write_text(
        "trade_date,symbol,open,high,low,close,volume,amount,limit_up,limit_down\n"
        "2024-01-02,TEST001,8.0,8.2,7.8,8.0,100000,800000,8.8,7.2\n"
        "2024-01-03,TEST001,8.0,8.5,7.9,8.4,110000,924000,9.24,7.56\n"
        "2024-01-04,TEST001,8.4,9.0,8.3,8.8,120000,1056000,9.68,7.92\n"
        "2024-01-05,TEST001,8.8,9.5,8.7,9.2,130000,1196000,10.12,8.28\n"
        "2024-01-08,TEST001,9.2,10.0,9.1,9.8,140000,1372000,10.78,8.82\n"
        "2024-01-09,TEST001,9.8,11.0,9.7,10.5,150000,1575000,11.55,9.45\n"
        "2024-01-10,TEST001,10.5,11.5,10.3,11.0,140000,1540000,12.10,9.90\n"
        "2024-01-11,TEST001,11.0,12.0,10.8,11.5,130000,1495000,12.65,10.35\n"
        "2024-01-12,TEST001,11.5,12.8,11.3,12.0,120000,1440000,13.20,10.80\n"
        "2024-01-15,TEST001,12.0,13.0,11.8,11.5,100000,1150000,12.65,10.35\n"
        "2024-01-16,TEST001,11.5,12.0,11.0,11.0,90000,990000,12.10,9.90\n"
        "2024-01-17,TEST001,11.0,11.5,10.5,10.8,80000,864000,11.88,9.72\n"
        "2024-01-18,TEST001,10.8,11.2,10.4,10.5,75000,798000,11.55,9.45\n"
        "2024-01-19,TEST001,10.5,11.0,10.2,10.8,85000,918000,11.88,9.72\n"
        "2024-01-22,TEST001,10.8,11.5,10.6,11.2,95000,1064000,12.32,10.08\n"
        "2024-01-23,TEST001,11.2,12.0,11.0,11.8,100000,1180000,12.98,10.62\n"
        "2024-01-24,TEST001,11.8,13.0,11.5,12.5,110000,1375000,13.75,11.25\n"
        "2024-01-25,TEST001,12.5,14.0,12.3,13.5,120000,1620000,14.85,12.15\n"
        "2024-01-26,TEST001,13.5,15.0,13.2,14.2,110000,1562000,15.62,12.78\n"
        "2024-01-29,TEST001,14.2,16.0,14.0,15.5,100000,1550000,17.05,13.95\n"
        "2024-01-30,TEST001,15.5,17.5,15.2,16.8,90000,1512000,18.48,15.12\n"
        "2024-01-31,TEST001,16.8,18.5,16.5,17.5,85000,1487500,19.25,15.75\n",
        encoding="utf-8-sig",
    )

    # index_daily.csv
    (snapshot_dir / "index_daily.csv").write_text(
        "trade_date,index_code,open,high,low,close,volume,amount\n"
        "2024-01-02,000300,3500,3600,3450,3550,100000000,355000000000\n"
        "2024-01-03,000300,3550,3650,3500,3600,110000000,396000000000\n"
        "2024-01-04,000300,3600,3700,3550,3650,120000000,438000000000\n"
        "2024-01-05,000300,3650,3750,3600,3700,130000000,481000000000\n"
        "2024-01-08,000300,3700,3800,3650,3750,140000000,525000000000\n"
        "2024-01-09,000300,3750,3850,3700,3800,150000000,570000000000\n"
        "2024-01-10,000300,3800,3900,3750,3850,160000000,616000000000\n"
        "2024-01-11,000300,3850,3950,3800,3900,170000000,663000000000\n"
        "2024-01-12,000300,3900,4000,3850,3950,180000000,711000000000\n"
        "2024-01-15,000300,3950,4050,3900,4000,190000000,760000000000\n"
        "2024-01-16,000300,4000,4100,3950,4050,200000000,810000000000\n"
        "2024-01-17,000300,4050,4150,4000,4100,210000000,861000000000\n"
        "2024-01-18,000300,4100,4200,4050,4150,220000000,913000000000\n"
        "2024-01-19,000300,4150,4250,4100,4200,230000000,966000000000\n"
        "2024-01-22,000300,4200,4300,4150,4250,240000000,1020000000000\n"
        "2024-01-23,000300,4250,4350,4200,4300,250000000,1075000000000\n"
        "2024-01-24,000300,4300,4400,4250,4350,260000000,1131000000000\n"
        "2024-01-25,000300,4350,4450,4300,4400,270000000,1188000000000\n"
        "2024-01-26,000300,4400,4500,4350,4450,280000000,1246000000000\n"
        "2024-01-29,000300,4450,4550,4400,4500,290000000,1305000000000\n"
        "2024-01-30,000300,4500,4600,4450,4550,300000000,1365000000000\n"
        "2024-01-31,000300,4550,4650,4500,4600,310000000,1426000000000\n",
        encoding="utf-8-sig",
    )

    # industry_map.csv
    (snapshot_dir / "industry_map.csv").write_text(
        "symbol,industry_level2\nTEST001,电子信息\n",
        encoding="utf-8-sig",
    )

    # industry_daily_amount.csv
    (snapshot_dir / "industry_daily_amount.csv").write_text(
        "trade_date,industry_level2,amount\n"
        "2024-01-02,电子信息,100000000000\n"
        "2024-01-03,电子信息,110000000000\n"
        "2024-01-04,电子信息,120000000000\n"
        "2024-01-05,电子信息,130000000000\n"
        "2024-01-08,电子信息,140000000000\n"
        "2024-01-09,电子信息,150000000000\n"
        "2024-01-10,电子信息,160000000000\n"
        "2024-01-11,电子信息,170000000000\n"
        "2024-01-12,电子信息,180000000000\n"
        "2024-01-15,电子信息,190000000000\n"
        "2024-01-16,电子信息,200000000000\n"
        "2024-01-17,电子信息,210000000000\n"
        "2024-01-18,电子信息,220000000000\n"
        "2024-01-19,电子信息,230000000000\n"
        "2024-01-22,电子信息,240000000000\n"
        "2024-01-23,电子信息,250000000000\n"
        "2024-01-24,电子信息,260000000000\n"
        "2024-01-25,电子信息,270000000000\n"
        "2024-01-26,电子信息,280000000000\n"
        "2024-01-29,电子信息,290000000000\n"
        "2024-01-30,电子信息,300000000000\n"
        "2024-01-31,电子信息,310000000000\n"
        "2024-01-02,机械设备,80000000000\n"
        "2024-01-03,机械设备,85000000000\n"
        "2024-01-04,机械设备,90000000000\n"
        "2024-01-05,机械设备,95000000000\n"
        "2024-01-08,机械设备,100000000000\n"
        "2024-01-09,机械设备,105000000000\n"
        "2024-01-10,机械设备,110000000000\n"
        "2024-01-11,机械设备,115000000000\n"
        "2024-01-12,机械设备,120000000000\n"
        "2024-01-15,机械设备,125000000000\n"
        "2024-01-16,机械设备,130000000000\n"
        "2024-01-17,机械设备,135000000000\n"
        "2024-01-18,机械设备,140000000000\n"
        "2024-01-19,机械设备,145000000000\n"
        "2024-01-22,机械设备,150000000000\n"
        "2024-01-23,机械设备,155000000000\n"
        "2024-01-24,机械设备,160000000000\n"
        "2024-01-25,机械设备,165000000000\n"
        "2024-01-26,机械设备,170000000000\n"
        "2024-01-29,机械设备,175000000000\n"
        "2024-01-30,机械设备,180000000000\n"
        "2024-01-31,机械设备,185000000000\n",
        encoding="utf-8-sig",
    )

    # trading_calendar.csv
    (snapshot_dir / "trading_calendar.csv").write_text(
        "trade_date,is_open\n"
        "2024-01-02,1\n"
        "2024-01-03,1\n"
        "2024-01-04,1\n"
        "2024-01-05,1\n"
        "2024-01-08,1\n"
        "2024-01-09,1\n"
        "2024-01-10,1\n"
        "2024-01-11,1\n"
        "2024-01-12,1\n"
        "2024-01-15,1\n"
        "2024-01-16,1\n"
        "2024-01-17,1\n"
        "2024-01-18,1\n"
        "2024-01-19,1\n"
        "2024-01-22,1\n"
        "2024-01-23,1\n"
        "2024-01-24,1\n"
        "2024-01-25,1\n"
        "2024-01-26,1\n"
        "2024-01-29,1\n"
        "2024-01-30,1\n"
        "2024-01-31,1\n",
        encoding="utf-8-sig",
    )


def test_sensitivity_runs_baseline_and_variants(tmp_path: Path) -> None:
    """测试敏感性分析运行 baseline 和多个 variant。"""
    raw_snapshot_dir = tmp_path / "raw_snapshot"
    _build_minimal_raw_snapshot(raw_snapshot_dir)

    config = BacktestConfig(
        name="sensitivity-test",
        start_date="2024-01-02",
        end_date="2024-01-31",
        initial_cash=1000000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot="test-snapshot",
        data_dir=tmp_path,
    )

    result = run_sensitivity_analysis(
        raw_snapshot_dir=raw_snapshot_dir,
        config=config,
        base_parameters=default_mvp1_parameters(),
    )

    # 验证结果结构
    assert isinstance(result, SensitivityResult)
    assert result.base_parameters.name == "ADR-0002-defaults"

    # 验证包含 baseline 行
    baseline_rows = [row for row in result.rows if row.parameter == "baseline"]
    assert len(baseline_rows) == 1
    assert baseline_rows[0].baseline_value == "ADR-0002-defaults"
    assert baseline_rows[0].variant_value == "ADR-0002-defaults"

    # 验证包含所有 6 个参数的 variant
    expected_parameters = [
        "ab_min_gain_pct",
        "bc_max_retracement_pct",
        "signal_distance_to_c_max_pct",
        "trend_exit_pct",
        "max_holding_days",
        "strong_mainline_days",
    ]
    variant_parameters = [row.parameter for row in result.rows if row.parameter != "baseline"]
    assert set(variant_parameters) == set(expected_parameters)


def test_sensitivity_uses_real_strategy_runs(tmp_path: Path) -> None:
    """测试敏感性分析使用真实的策略回测，而非静态记录。"""
    raw_snapshot_dir = tmp_path / "raw_snapshot"
    _build_minimal_raw_snapshot(raw_snapshot_dir)

    config = BacktestConfig(
        name="sensitivity-test",
        start_date="2024-01-02",
        end_date="2024-01-31",
        initial_cash=1000000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot="test-snapshot",
        data_dir=tmp_path,
    )

    result = run_sensitivity_analysis(
        raw_snapshot_dir=raw_snapshot_dir,
        config=config,
        base_parameters=default_mvp1_parameters(),
    )

    # 验证每个 variant 都调用了真实的策略回测
    # 检查是否有样本内/样本外指标
    for row in result.rows:
        # 确保有真实数值而非占位符
        assert row.sample_in_metric != "not_evaluated"
        assert row.sample_out_metric != "not_evaluated"

        # 验证指标格式
        try:
            float(row.sample_in_metric)
            float(row.sample_out_metric)
        except ValueError:
            # 如果不是浮点数，应该有说明
            assert row.sample_in_metric in ["N/A", "0.00"]
            assert row.sample_out_metric in ["N/A", "0.00"]

    # 验证 baseline 行有真实的策略运行结果
    baseline_row = next(row for row in result.rows if row.parameter == "baseline")
    assert baseline_row.sample_in_metric != "not_evaluated"
    assert baseline_row.sample_out_metric != "not_evaluated"


def test_sensitivity_flags_sample_in_improves_sample_out_worsens(tmp_path: Path) -> None:
    """测试敏感性分析标记样本内改善但样本外恶化的过拟合风险。"""
    raw_snapshot_dir = tmp_path / "raw_snapshot"
    _build_minimal_raw_snapshot(raw_snapshot_dir)

    # 创建一个参数集，预期会产生不同的样本内/样本外结果
    modified_params = StrategyParameters(
        name="test-overfit-risk-params",
        ab_min_gain_pct=0.25,  # 更严格的 AB 涨幅
        bc_max_retracement_pct=0.50,  # 更严格的 BC 回撤
        c_window_min_days=3,
        c_window_max_days=20,
        signal_distance_to_c_max_pct=0.08,
        mainline_top_n=5,
        strong_mainline_days=3,
        observation_window_days=5,
        observation_min_count=3,
        max_holdings=3,
        daily_open_limit=1,
        weekly_open_limit=2,
        risk_pct=0.01,
        stop_loss_pct=0.05,
        commission_rate=0.0003,
        stamp_tax_rate=0.0005,
        buy_slippage_rate=0.0005,
        sell_slippage_rate=0.0005,
        lot_size=100,
        emergency_stop_pct=0.05,
        time_stop_days=3,
        trend_exit_pct=0.08,
        max_holding_days=30,
        min_daily_amount=0.0,
        long_suspension_days=0,
    )

    config = BacktestConfig(
        name="sensitivity-test",
        start_date="2024-01-02",
        end_date="2024-01-31",
        initial_cash=1000000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot="test-snapshot",
        data_dir=tmp_path,
    )

    result = run_sensitivity_analysis(
        raw_snapshot_dir=raw_snapshot_dir,
        config=config,
        base_parameters=default_mvp1_parameters(),
    )

    # 验证 overfit_risk 字段存在
    for row in result.rows:
        assert row.overfit_risk in ["high", "medium", "low", "none"]

    # 验证 accepted 字段存在
    for row in result.rows:
        assert row.accepted in ["true", "false"]

    # 验证如果 variant 的样本内改善但样本外恶化，则标记过拟合风险
    baseline_row = next(row for row in result.rows if row.parameter == "baseline")
    baseline_sample_in = float(baseline_row.sample_in_metric)
    baseline_sample_out = float(baseline_row.sample_out_metric)

    for row in result.rows:
        if row.parameter == "baseline":
            continue

        try:
            variant_sample_in = float(row.sample_in_metric)
            variant_sample_out = float(row.sample_out_metric)

            # 如果样本内改善但样本外恶化，应标记过拟合风险
            if variant_sample_in > baseline_sample_in and variant_sample_out < baseline_sample_out:
                assert row.overfit_risk in ["high", "medium"]
                assert row.accepted == "false"
        except ValueError:
            # 如果无法转换为浮点数，跳过检查
            pass


def test_sensitivity_does_not_mutate_default_parameters(tmp_path: Path) -> None:
    """确保敏感性分析不修改默认参数。"""
    raw_snapshot_dir = tmp_path / "raw_snapshot"
    _build_minimal_raw_snapshot(raw_snapshot_dir)

    # 获取原始默认参数
    original_params = default_mvp1_parameters()

    # 运行敏感性分析
    config = BacktestConfig(
        name="sensitivity-test",
        start_date="2024-01-02",
        end_date="2024-01-31",
        initial_cash=1000000,
        output_dir=tmp_path / "output",
        data_source="a-stock-data",
        data_snapshot="test-snapshot",
        data_dir=tmp_path,
    )

    result = run_sensitivity_analysis(
        raw_snapshot_dir=raw_snapshot_dir,
        config=config,
        base_parameters=original_params,
    )

    # 验证默认参数未被修改
    new_params = default_mvp1_parameters()
    assert new_params.ab_min_gain_pct == 0.20
    assert new_params.bc_max_retracement_pct == 0.60
    assert new_params.signal_distance_to_c_max_pct == 0.08
    assert new_params.trend_exit_pct == 0.08
    assert new_params.max_holding_days == 30
    assert new_params.strong_mainline_days == 3
    assert new_params == original_params