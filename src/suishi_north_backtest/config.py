from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


DataSourceName = Literal["fixture", "a-stock-data"]


@dataclass(frozen=True)
class BacktestConfig:
    """MVP-1 组合回测配置。"""

    name: str = "mvp1-skeleton"
    start_date: str = "2024-01-01"
    end_date: str = "2024-01-05"
    initial_cash: int = 1_000_000
    output_dir: Path = Path("outputs/mvp1-skeleton")
    data_source: DataSourceName = "fixture"
    data_snapshot: str | None = None
    data_dir: Path = Path("data/a_stock_data_snapshots")

    def normalized_output_dir(self) -> Path:
        return Path(self.output_dir)

    def normalized_data_dir(self) -> Path:
        return Path(self.data_dir)
