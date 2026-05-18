# suishi_north_backtest

`suishi_north_backtest` 是 `随势向北股票趋势交易系统` 的回测与优化系统。

当前阶段为 MVP-1：日线收盘级组合回测骨架。

## MVP-1 定位

MVP-1 是日线代理研究系统，用于验证日线 C 点结构在组合级约束下是否具有统计边际。

它不等同于完整实盘交易系统：

- 暂不接入 60 分钟真实执行周期。
- 暂不实现完整 `a-stock-data` 数据适配。
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

## 运行 MVP-1 骨架

安装后可以运行：

```bash
suishi-north-backtest --output-dir outputs/mvp1-skeleton
```

或：

```bash
python -m suishi_north_backtest.cli --output-dir outputs/mvp1-skeleton
```

运行后会生成：

- `equity_curve.csv`
- `trades.csv`
- `skipped_trades.csv`
- `run_metadata.json`

## MVP-1 验收

快速烟雾验收只检查最小骨架是否能运行：

```bash
python scripts/acceptance_check.py --profile smoke
```

也可以通过 npm 脚本运行：

```bash
npm run acceptance:smoke
```

完整验收用于检查 ADR-0002 和 #1-#12 约定的完整 MVP-1 输出：

```bash
python scripts/acceptance_check.py --profile full
```

或：

```bash
npm run acceptance
```

说明：

- `smoke` 通过只代表最小回测骨架可运行。
- `full` 通过才代表 MVP-1 系统输出满足总体验收标准。
- 当前如果代码仍只输出最小骨架文件，`full` 应失败，这是预期行为；它用于暴露“issue 已关闭但实际输出不完整”的问题。
