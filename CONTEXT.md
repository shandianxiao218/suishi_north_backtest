# Code Context — Issue #38: 生成 MVP-1 研究报告 report.md

## Files Retrieved

1. `src/suishi_north_backtest/data.py` (全文) — Mvp1DataSet 定义、FixtureDataProvider、AStockDataProvider
2. `src/suishi_north_backtest/output_contract.py` (全文) — CSV/JSON 输出协议、文件名规范、校验函数
3. `src/suishi_north_backtest/metrics.py` (全文) — 新旧两套指标 API（dataclass-based + dict-based）
4. `src/suishi_north_backtest/parameters.py` (全文) — StrategyParameters 参数集定义
5. `src/suishi_north_backtest/config.py` (全文) — BacktestConfig 配置
6. `src/suishi_north_backtest/engine.py` (全文) — write_mvp1_dataset_outputs、CSV/JSON 写入
7. `src/suishi_north_backtest/mvp1_runner.py` (全文) — 生产链路入口、Mvp1DataSet 组装
8. `src/suishi_north_backtest/sensitivity.py` (全文) — 参数敏感性分析
9. `src/suishi_north_backtest/signal_audit.py` (全文) — 信号审计行生成
10. `src/suishi_north_backtest/scoring.py` (全文) — 候选多因子评分
11. `tests/test_report.py` (全文) — **report.py 的完整测试规范（尚未有 report.py 实现）**
12. `CONTEXT.md` (全文) — 项目领域上下文
13. `docs/adr/0002-mvp-1-daily-close-backtest-scope.md` (全文) — MVP-1 范围定义

## Key Code

### Mvp1DataSet 数据结构 (`data.py`)

```python
@dataclass(frozen=True)
class Mvp1DataSet:
    data_version: str
    parameter_set: str
    universe: str
    equity_curve: list[dict[str, object]]       # [{date, cash, equity, drawdown, track}]
    trades: list[dict[str, object]]              # 18 个字段见 output_contract trades.csv
    skipped_trades: list[dict[str, object]]      # [{signal_date, track, symbol, reason}]
    candidates: list[dict[str, object]]          # 21 个字段见 output_contract candidates.csv
    holdings: list[dict[str, object]]            # 10 个字段见 output_contract holdings.csv
    benchmark_comparison: list[dict[str, object]]  # 17 个字段，含 period/benchmark/策略/基准侧指标
    track_comparison: list[dict[str, object]]     # [{metric, pure_structure_track, mainline_filtered_track, delta, audit_note}]
    sensitivity: list[dict[str, object]]          # 8 个字段，参数扰动结果
    metrics: dict[str, object]                    # 含 total_return, max_drawdown, profit_factor, win_rate, trade_count, tracks, benchmarks, sample_windows 等
```

### BacktestConfig (`config.py`)

```python
@dataclass(frozen=True)
class BacktestConfig:
    name: str = "mvp1-skeleton"
    start_date: str = "2024-01-01"
    end_date: str = "2024-01-05"
    initial_cash: int = 1_000_000
    output_dir: Path = Path("outputs/mvp1-skeleton")
    data_source: DataSourceName = "fixture"       # "fixture" | "a-stock-data"
    data_snapshot: str | None = None
    data_dir: Path = Path("data/a_stock_data_snapshots")
```

### generate_report 签名（从 test_report.py 推导）

```python
from suishi_north_backtest.config import BacktestConfig
from suishi_north_backtest.data import Mvp1DataSet

def generate_report(config: BacktestConfig, data_set: Mvp1DataSet) -> None:
    """生成 report.md 写入 config.output_dir / "report.md"。"""
```

### 测试要求的报告章节（来自 test_report.py）

必需章节标题/关键词（全部出现在 report.md 内容中）：

| 关键词 | 说明 |
|---|---|
| 数据版本 | 含 data_version 值 |
| 参数集 | 含 parameter_set 值 |
| 股票池 | universe 信息 |
| 样本区间 | 含 "样本内"/"样本外"/"近期窗口" |
| 策略摘要 | — |
| 双轨对比 | pure_structure / mainline_filtered |
| 基准对比 | CSI300 / CSI500 / CSI1000 或中文名 |
| 参数敏感性 | sensitivity 数据 |
| 最大回撤 | max_drawdown |
| 交易样本 | 含交易次数 |
| 风险提示 | — |
| 研究限制 | 含 "这是研究输出，不是投资建议。" |

**禁止措辞**：建议买入、建议卖出、推荐投资、应该买入、应该卖出、建议投资

### output_contract 中已有的输出文件列表

| 文件名 | Mvp1DataSet 对应属性 |
|---|---|
| equity_curve.csv | `data_set.equity_curve` |
| trades.csv | `data_set.trades` |
| skipped_trades.csv | `data_set.skipped_trades` |
| candidates.csv | `data_set.candidates` |
| holdings.csv | `data_set.holdings` |
| benchmark_comparison.csv | `data_set.benchmark_comparison` |
| track_comparison.csv | `data_set.track_comparison` |
| sensitivity.csv | `data_set.sensitivity` |
| metrics.json | `data_set.metrics` |
| run_metadata.json | 组合 config + data_set 元信息 |

**注意**：`report.md` 不在 output_contract 的文件列表中，是一个独立的新增输出。

### metrics.py 可用的 dict-based 函数

```python
total_return(equity_curve) -> float
max_drawdown(equity_curve) -> float
annualized_return(equity_curve) -> float
volatility(equity_curve) -> float
win_rate(trades) -> float
trade_count(trades) -> int
excess_return(strategy_ret, benchmark_ret) -> float
return_drawdown_ratio(total_ret, max_dd) -> float
sample_windows(as_of) -> dict[str, tuple[str, str]]
equity_curve_in_window(equity_curve, start, end) -> list[dict]
build_benchmark_comparison_rows(...) -> list[dict]  # 已由 mvp1_runner 调用
```

## Architecture

### 数据流

```
raw snapshot → mvp1_runner.run_mvp1_from_raw_snapshot()
                    ↓
              Mvp1DataSet (统一数据集)
                    ↓
        engine.write_mvp1_dataset_outputs() → CSV + JSON 文件
                    ↓
        report.generate_report(config, data_set) → report.md  ← **需要新建**
```

### 关键依赖关系

- `report.py` 需要 `Mvp1DataSet` 的全部 12 个字段来生成完整报告
- `report.py` 可以直接消费 `data_set.metrics` 中已计算好的指标（total_return, max_drawdown, profit_factor, win_rate, trade_count, tracks 等）
- `report.py` 可以消费 `data_set.benchmark_comparison` 行的已格式化字符串（百分比已转为字符串）
- `report.py` 可以消费 `data_set.track_comparison` 行的已格式化数据
- `report.py` 可以消费 `data_set.sensitivity` 行的已格式化数据
- `report.py` 可以用 `metrics.py` 的 dict-based 函数做额外窗口计算（如需要）
- `report.py` 输出到 `config.output_dir / "report.md"`
- `report.py` **不应**直接依赖 market_data、signals、engine 等模块，只依赖 `Mvp1DataSet` 和 `BacktestConfig`

### engine.py 中的关键常量

```python
RESEARCH_LIMITATION = "MVP-1 是日线代理研究系统，不等同于完整实盘交易系统。"
```

## Start Here

打开 `tests/test_report.py` — 这个文件完整定义了 `report.py` 必须满足的**所有行为契约**。然后新建 `src/suishi_north_backtest/report.py`，实现 `generate_report(config: BacktestConfig, data_set: Mvp1DataSet) -> None` 函数。

实现思路：
1. 从 `data_set.metrics` 提取策略摘要指标
2. 从 `data_set.track_comparison` 构建双轨对比表
3. 从 `data_set.benchmark_comparison` 构建基准对比表
4. 从 `data_set.sensitivity` 构建参数敏感性表
5. 从 `data_set.trades` 取前几笔构建交易样本
6. 从 `data_set.metrics["sample_windows"]` 构建样本区间信息
7. 从 `config` 和 `data_set` 元信息构建头部（数据版本、参数集、股票池等）
8. 固定尾部（风险提示、研究限制、免责声明）

## Constraints & Open Questions

- **report.md 不在 output_contract 中**：如果希望 report.md 被自动校验，后续可能需要更新 `mvp1_required_files()` 和 `validate_output_contract()`
- **测试未覆盖 report.md 是否被 engine 自动调用**：当前测试只直接调 `generate_report()`，engine.py 的 `write_mvp1_dataset_outputs()` 未调用 report
- **数据格式差异**：fixture 数据中很多值是字符串（如 `"10.2051"`），而 mvp1_runner 生成的值是浮点数字符串格式化后的结果；report.py 需要处理两种情况
- **benchmark_comparison 中百分比已是字符串**（如 `"3.42"`），report.py 需要直接展示或做 `float()` 转换后重新格式化
