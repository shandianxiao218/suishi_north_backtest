# suishi_north_backtest

`suishi_north_backtest` 是 `随势向北股票趋势交易系统` 的回测与优化系统。

当前阶段为 MVP-1：日线收盘级组合回测骨架。

## MVP-1 定位

MVP-1 是日线代理研究系统，用于验证日线 C 点结构在组合级约束下是否具有统计边际。

它不等同于完整实盘交易系统：

- 暂不接入 60 分钟真实执行周期。
- 暂未接入完整 `a-stock-data` 历史数据回测。
- 暂不做激进参数优化。

## 开发安装

```bash
python -m pip install -e ".[dev]"
```

## 运行测试

```bash
python -m pytest
```

也可以通过 npm 脚本运行：

```bash
npm run test
```

## 运行 MVP-1

默认使用确定性 fixture 数据源：

```bash
suishi-north-backtest --output-dir outputs/mvp1-skeleton
```

或：

```bash
python -m suishi_north_backtest.cli --output-dir outputs/mvp1-skeleton
```

可以显式指定数据源和数据快照版本：

```bash
python -m suishi_north_backtest.cli \
  --data-source fixture \
  --data-snapshot fixture-local-run-001 \
  --output-dir outputs/mvp1-fixture
```

`a-stock-data` 已作为数据源边界预留，但尚未实现真实外部数据读取：

```bash
python -m suishi_north_backtest.cli --data-source a-stock-data
```

当前会返回明确的未实现错误。后续真实数据接入必须在 `AStockDataProvider` 中完成字段映射、缓存和数据版本生成，不应让策略引擎直接依赖外部数据字段形状。

运行后会生成：

- `equity_curve.csv`
- `trades.csv`
- `skipped_trades.csv`
- `run_metadata.json`
- `metrics.json`
- `candidates.csv`
- `holdings.csv`
- `benchmark_comparison.csv`
- `track_comparison.csv`
- `sensitivity.csv`

## 数据源边界

当前支持两个数据源名称：

| 数据源 | 状态 | 用途 |
|---|---|---|
| `fixture` | 已实现 | 确定性验收和回归测试 |
| `a-stock-data` | 边界已预留，读取未实现 | 后续接入真实 A 股历史数据 |

引擎只依赖统一的 `Mvp1DataSet`，不直接依赖外部数据源字段。真实数据接入时必须保持输出协议不变。

## MVP-1 验收

快速烟雾验收只检查最小骨架是否能运行：

```bash
python scripts/acceptance_check.py --profile smoke
```

也可以通过 npm 脚本运行：

```bash
npm run acceptance:smoke
```

完整输出协议验收用于检查 ADR-0002 和 #1-#12 约定的输出文件是否齐全：

```bash
python scripts/acceptance_check.py --profile full
```

或：

```bash
npm run acceptance
```

真实回测验收用于检查输出是否已经替换为真实数据和真实回测证据，不能包含占位数据：

```bash
python scripts/acceptance_check.py --profile real
```

或：

```bash
npm run acceptance:real
```

说明：

- `smoke` 通过只代表最小回测骨架可运行。
- `full` 通过代表 MVP-1 输出协议满足总体验收标准。
- `real` 通过代表输出不再是占位骨架，而是具备数据版本、候选/交易审计、基准区间和参数扰动证据。
- 当前 `real` 通过基于确定性 fixture 数据，不等同于完整 A 股历史数据回测通过。
