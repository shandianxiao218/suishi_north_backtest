from __future__ import annotations

import pytest

from suishi_north_backtest.market_data import IndustryDailyAmount
from suishi_north_backtest.mainline import (
    IndustryMainlineEntry,
    MainlineStatus,
    compute_mainlines,
)


# ---- 辅助函数 ----


def ind(
    trade_date: str, industry: str, amount: float
) -> IndustryDailyAmount:
    return IndustryDailyAmount(
        trade_date=trade_date,
        industry_level2=industry,
        amount=amount,
    )


def make_daily_amounts(
    pattern: dict[str, dict[str, float]]
) -> list[IndustryDailyAmount]:
    result = []
    for date, industries in pattern.items():
        for industry, amount in industries.items():
            result.append(ind(date, industry, amount))
    return result


# ---- 测试 ----


def test_consecutive_3_days_top5_triggers_strong_mainline() -> None:
    """连续 3 个交易日进入前 5 名，触发强主线。"""
    data = make_daily_amounts({
        "2024-01-02": {"银行": 100, "白酒": 90, "医药": 80, "地产": 70, "科技": 60, "汽车": 50},
        "2024-01-03": {"银行": 110, "白酒": 95, "医药": 85, "地产": 75, "科技": 65, "汽车": 55},
        "2024-01-04": {"银行": 120, "白酒": 100, "医药": 90, "地产": 80, "科技": 70, "汽车": 60},
    })

    mainlines = compute_mainlines(data, as_of="2024-01-04")

    bank_entries = [m for m in mainlines if m.industry_level2 == "银行"]
    assert len(bank_entries) > 0
    # 在 2024-01-04 银行应已达到强主线
    bank_0104 = [m for m in bank_entries if m.trade_date == "2024-01-04"]
    assert any(m.status == MainlineStatus.STRONG for m in bank_0104)


def test_observation_mainline_3_of_5_days() -> None:
    """近 5 日内至少 3 次进入前 5，触发观察主线。"""
    data = make_daily_amounts({
        "2024-01-02": {"银行": 100, "白酒": 90, "医药": 80, "地产": 70, "科技": 60, "汽车": 50},
        "2024-01-03": {"银行": 50,  "白酒": 100, "医药": 90, "地产": 80, "科技": 70, "汽车": 60},
        "2024-01-04": {"银行": 100, "白酒": 90,  "医药": 80, "地产": 70, "科技": 60, "汽车": 50},
        "2024-01-05": {"银行": 50,  "白酒": 100, "医药": 90, "地产": 80, "科技": 70, "汽车": 60},
        "2024-01-08": {"银行": 100, "白酒": 90,  "医药": 80, "地产": 70, "科技": 60, "汽车": 50},
    })

    mainlines = compute_mainlines(data, as_of="2024-01-08")

    bank_entries = [m for m in mainlines if m.industry_level2 == "银行" and m.trade_date == "2024-01-08"]
    # 银行在 5 天中 3 天排前 5（1/2, 1/4, 1/8），应触发观察主线
    assert any(m.status in (MainlineStatus.OBSERVATION, MainlineStatus.STRONG) for m in bank_entries)


def test_as_of_limits_data_usage() -> None:
    """只用 as_of 及之前数据，as_of 之后的数据不影响判断。"""
    data = make_daily_amounts({
        "2024-01-02": {"银行": 100, "白酒": 90, "医药": 80, "地产": 70, "科技": 60, "汽车": 50},
        "2024-01-03": {"银行": 110, "白酒": 95, "医药": 85, "地产": 75, "科技": 65, "汽车": 55},
        "2024-01-04": {"银行": 120, "白酒": 100, "医药": 90, "地产": 80, "科技": 70, "汽车": 60},
        "2024-01-05": {"银行": 50,  "白酒": 130, "医药": 120, "地产": 110, "科技": 100, "汽车": 90},
    })

    # as_of = 2024-01-04，只用前 3 天数据
    mainlines_0104 = compute_mainlines(data, as_of="2024-01-04")
    bank_0104 = [m for m in mainlines_0104 if m.industry_level2 == "银行" and m.trade_date == "2024-01-04"]
    assert any(m.status == MainlineStatus.STRONG for m in bank_0104)

    # as_of = 2024-01-03，只用前 2 天数据，银行不够 3 天
    mainlines_0103 = compute_mainlines(data, as_of="2024-01-03")
    bank_0103 = [m for m in mainlines_0103 if m.industry_level2 == "银行" and m.trade_date == "2024-01-03"]
    assert not any(m.status == MainlineStatus.STRONG for m in bank_0103)


def test_non_top5_industry_not_mainline() -> None:
    """从未进入前 5 的行业不应成为任何主线。"""
    data = make_daily_amounts({
        "2024-01-02": {"银行": 100, "白酒": 90, "医药": 80, "地产": 70, "科技": 60, "汽车": 50},
        "2024-01-03": {"银行": 110, "白酒": 95, "医药": 85, "地产": 75, "科技": 65, "汽车": 55},
        "2024-01-04": {"银行": 120, "白酒": 100, "医药": 90, "地产": 80, "科技": 70, "汽车": 60},
    })

    mainlines = compute_mainlines(data, as_of="2024-01-04")

    auto_entries = [m for m in mainlines if m.industry_level2 == "汽车"]
    # 汽车从未进入前 5
    assert not any(m.status != MainlineStatus.NONE for m in auto_entries)


def test_mainline_entry_has_required_fields() -> None:
    data = make_daily_amounts({
        "2024-01-02": {"银行": 100, "白酒": 90, "医药": 80, "地产": 70, "科技": 60},
    })

    mainlines = compute_mainlines(data, as_of="2024-01-02")

    for m in mainlines:
        assert hasattr(m, "trade_date")
        assert hasattr(m, "industry_level2")
        assert hasattr(m, "status")
        assert hasattr(m, "rank")
        assert hasattr(m, "amount")


def test_startup_day_recorded() -> None:
    """首次进入前 5 应记录为启动日。"""
    data = make_daily_amounts({
        "2024-01-02": {"白酒": 100, "医药": 90, "地产": 80, "科技": 70, "汽车": 60, "银行": 50},
        "2024-01-03": {"银行": 100, "白酒": 90, "医药": 80, "地产": 70, "科技": 60, "汽车": 50},
    })

    mainlines = compute_mainlines(data, as_of="2024-01-03")

    # 银行 1/2 不在前 5，1/3 进入前 5，应为启动日
    bank_0103 = [m for m in mainlines if m.industry_level2 == "银行" and m.trade_date == "2024-01-03"]
    assert any(m.status == MainlineStatus.STARTUP for m in bank_0103)


def test_empty_data_returns_empty() -> None:
    mainlines = compute_mainlines([], as_of="2024-01-02")
    assert mainlines == []
