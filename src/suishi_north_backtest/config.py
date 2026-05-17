from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BacktestConfig:
    """MVP-1 组合回测配置。"""

    name: str = "mvp1-skeleton"
    start_date: str = "2024-01-01"
    end_date: str = "2024-01-05"
    initial_cash: int = 1_000_000
    output_dir: Path = Path("outputs/mvp1-skeleton")

    def normalized_output_dir(self) -> Path:
        return Path(self.output_dir)
