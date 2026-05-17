# suishi_north_backtest

`suishi_north_backtest` 是 `随势向北股票趋势交易系统` 的回测与优化系统。

当前阶段为 MVP-1：日线收盘级组合回测骨架。

## MVP-1 定位

MVP-1 是日线代理研究系统，用于验证日线 C 点结构在组合级约束下是否具有统计边际。

它不等同于完整实盘交易系统：

- 暂不接入 60 分钟真实执行周期。
- 暂不实现完整 `a-stock-data` 数据适配。
- 暂不做激进参数优化。

## 运行测试

```bash
python -m pytest
```

## 运行 MVP-1 骨架

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
