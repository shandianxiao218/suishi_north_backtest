"""MVP-1 策略参数集。

统一管理所有可配置策略参数，替代分散在各模块的硬编码默认值。
内部统一使用小数（0.20 = 20%，0.0003 = 0.03%）。
signals.py 使用百分比值（20.0 = 20%），通过属性转换。
"""
from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class StrategyParameters:
    name: str

    # ABC / C 点候选
    ab_min_gain_pct: float
    bc_max_retracement_pct: float
    c_window_min_days: int
    c_window_max_days: int
    signal_distance_to_c_max_pct: float

    # 主线
    mainline_top_n: int
    strong_mainline_days: int
    observation_window_days: int
    observation_min_count: int

    # 组合约束
    max_holdings: int
    daily_open_limit: int
    weekly_open_limit: int

    # 执行 / 仓位
    risk_pct: float
    stop_loss_pct: float
    commission_rate: float
    stamp_tax_rate: float
    buy_slippage_rate: float
    sell_slippage_rate: float
    lot_size: int

    # 退出
    emergency_stop_pct: float
    time_stop_days: int
    trend_exit_pct: float
    max_holding_days: int

    # -- signals.py 兼容属性：它用百分比值（20.0 = 20%） --

    @property
    def ab_min_gain_pct_for_signals(self) -> float:
        return self.ab_min_gain_pct * 100.0

    @property
    def bc_max_retracement_pct_for_signals(self) -> float:
        return self.bc_max_retracement_pct * 100.0

    @property
    def signal_distance_to_c_max_pct_for_signals(self) -> float:
        return self.signal_distance_to_c_max_pct * 100.0

    def to_metadata(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for f in fields(self):
            result[f.name] = getattr(self, f.name)
        return result


def default_mvp1_parameters() -> StrategyParameters:
    """返回 ADR-0002 定义的 MVP-1 默认参数。"""
    return StrategyParameters(
        name="ADR-0002-defaults",
        ab_min_gain_pct=0.20,
        bc_max_retracement_pct=0.60,
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
    )
