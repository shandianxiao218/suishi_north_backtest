# 交接文档：MVP-1 当前状态、后续计划与验收路线

日期：2026-05-18

仓库：`shandianxiao218/suishi_north_backtest`

面向对象：后续接手开发的 agent / 人类维护者

## 一句话结论

当前项目已经完成 **MVP-1 工程骨架、输出协议、fixture real 验收、本地 a-stock-data 快照读取链路、快照构建器**。

当前还没有完成 **a-stock-data 原始行情到真实 MVP-1 回测结果的自动生成**。

因此，当前系统可以证明：

> 回测输出协议、验收体系、数据源边界、本地快照读取和快照构建工具已经打通。

但还不能证明：

> `随势向北` 策略在真实 A 股历史数据上有效。

后续开发核心目标是：

> 将 `a-stock-data` 原始日线、周线、指数、行业数据转换成真实 MVP-1 输出目录，并让 `a-stock-data` 数据源下的 `real` 验收通过。

---

## 当前已完成工作

### 1. 项目协作与文档体系

已完成中文化项目协作文档与领域上下文：

- `AGENTS.md`
- `CONTEXT.md`
- `README.md`
- `docs/agents/issue-tracker.md`
- `docs/agents/triage-labels.md`
- `docs/agents/domain.md`
- `docs/adr/0001-record-architecture-decisions.md`
- `docs/adr/0002-mvp-1-daily-close-backtest-scope.md`
- `docs/handoff/2026-05-17-mvp1-current-status.md`

核心约定：

- 默认中文交流、中文 issue、中文 ADR、中文报告。
- Issue tracker 使用 GitHub Issues。
- 每个 PR 合并前需要 review。
- 回测结果始终表述为研究输出，不得表述为投资建议。
- MVP-1 是日线收盘级组合回测，不是完整实盘交易系统。

### 2. MVP-1 策略与回测边界

`ADR-0002` 已锁定 MVP-1 范围：

- 优先验证策略有效性，暂不做激进参数优化。
- 数据颗粒度：周线 + 日线；60 分钟真实执行周期后移到 MVP-2。
- 股票池：沪深 A 股核心股票池，主板 + 创业板 + 科创板，暂不纳入北交所。
- 主线代理：二级行业成交金额连续 3 个交易日进入前 5，视为强主线。
- 信号：T 日收盘后生成，T+1 开盘买入。
- 回测方式：只使用组合级回测。
- 初始资金：100 万。
- 单笔风险：1% 账户权益。
- 最大同时持仓：3 只。
- 每日最多新开仓：1 笔。
- 每周最多新开仓：2 笔。
- 成本：单边佣金 0.03%，卖出印花税 0.05%，买卖各 0.05% 滑点。
- 基准：沪深300、中证500、中证1000。
- 样本切分：2018-2022 样本内，2023 至今样本外，2024 至今近期窗口。

### 3. GitHub Issues 状态

原始 MVP-1 issues #1-#12 在 GitHub issue 层面均已关闭为 completed。

但需要明确：issue 关闭不等于真实市场回测完成。后续判断必须以验收脚本和输出文件为准。

| Issue | 标题 | 当前真实状态 |
|---:|---|---|
| #1 | 建立最小可运行的 MVP-1 组合回测骨架 | 已完成 |
| #2 | 接入日线、周线和指数基准数据适配器 | 数据源边界与本地快照读取已完成；原始行情转换未完成 |
| #3 | 实现沪深核心 A 股股票池与可交易性过滤 | fixture 输出协议已覆盖字段；真实过滤逻辑未完成 |
| #4 | 实现二级行业成交金额主线代理 | fixture 输出协议已覆盖字段；真实主线计算未完成 |
| #5 | 实现日线 ABCD 与 C 点代理候选识别 | fixture 证据已覆盖；真实识别逻辑未完成 |
| #6 | 实现候选排序与组合开仓约束 | fixture 证据已覆盖；真实组合逻辑未完成 |
| #7 | 实现 T+1 开盘成交、仓位 sizing、交易成本与滑点 | fixture 证据已覆盖；真实成交逻辑未完成 |
| #8 | 实现 MVP-1 退出规则与顺延卖出 | fixture 证据已覆盖；真实退出逻辑未完成 |
| #9 | 实现纯结构组合轨与主线过滤组合轨对比 | fixture 证据已覆盖；真实双轨对比未完成 |
| #10 | 实现指数基准对比与样本区间评估 | fixture 证据已覆盖；真实基准数据未完成 |
| #11 | 实现 MVP-1 回测报告与审计日志 | 输出协议已完成；真实内容生成未完成 |
| #12 | 实现 MVP-1 参数敏感性与样本外防过拟合检查 | fixture 证据已覆盖；真实扰动回测未完成 |

---

## 已合并 PR 总结

| PR | 标题 | 关键结果 |
|---:|---|---|
| #13 | 添加 pre-commit 工程护栏 | Husky / lint-staged / Prettier / npm test |
| #14 | 实现 MVP-1 组合回测骨架 | Python 项目结构、CLI、基础输出 |
| #15 | 修复 CSV 中文显示乱码 | CSV 改为 `utf-8-sig` |
| #16 | 添加 MVP-1 当前状态交接文档 | 初版 handoff |
| #17 | 添加 MVP-1 总体验收脚本 | `smoke` / `full` 验收 |
| #18 | 补齐 full 验收所需输出骨架 | 输出协议齐全 |
| #19 | 新增真实回测验收档位 | 新增 `real` 验收，拒绝占位输出 |
| #20 | 用确定性 fixture 结果通过 real 验收 | fixture real 验收通过 |
| #21 | 建立 MVP-1 数据源适配器边界 | `Mvp1DataSet` / `DataProvider` / `FixtureDataProvider` / `AStockDataProvider` |
| #22 | 实现 a-stock-data 本地快照读取器 | 本地快照目录读取、manifest 校验 |
| #23 | 新增 MVP-1 快照构建器 | 自动把已有 MVP-1 输出目录转换为本地快照 |

---

## 当前可用命令

### 安装

仓库使用 `src/` 布局。新 Python 环境必须先安装本地包：

```powershell
python -m pip install -e ".[dev]"
```

如果遇到：

```text
ModuleNotFoundError: No module named 'suishi_north_backtest'
```

说明当前 Python 解释器还没有安装本地包。重新执行上面的安装命令。

### 运行测试

```powershell
python -m pytest
```

或：

```powershell
npm run test
```

### 运行 fixture 回测

```powershell
python -m suishi_north_backtest.cli `
  --data-source fixture `
  --data-snapshot fixture-local-run-001 `
  --output-dir outputs/mvp1-skeleton
```

### 构建 a-stock-data 本地快照

```powershell
python -m suishi_north_backtest.snapshot_builder `
  --source-output-dir outputs/mvp1-skeleton `
  --snapshot snapshot-2026-05-18 `
  --data-dir data/a_stock_data_snapshots `
  --data-version a-stock-data-snapshot-2026-05-18 `
  --overwrite
```

### 读取 a-stock-data 本地快照

```powershell
python -m suishi_north_backtest.cli `
  --data-source a-stock-data `
  --data-snapshot snapshot-2026-05-18 `
  --data-dir data/a_stock_data_snapshots `
  --output-dir outputs/mvp1-a-stock-data
```

### 验收

```powershell
python scripts/acceptance_check.py --profile smoke
python scripts/acceptance_check.py --profile full
python scripts/acceptance_check.py --profile real
```

npm 版本：

```powershell
npm run acceptance:smoke
npm run acceptance
npm run acceptance:real
```

---

## 当前验收语义

| 验收档位 | 当前状态 | 含义 |
|---|---|---|
| `smoke` | 通过 | CLI 最小链路可运行 |
| `full` | 通过 | MVP-1 输出文件协议完整 |
| `real` | fixture 下通过 | 输出不再是空占位，具备非占位 fixture 证据 |
| `real` with `a-stock-data snapshot` | 可通过，取决于快照内容 | 本地快照读取链路已打通 |
| `real` with raw a-stock-data | 未完成 | 还没有原始行情转换器 |

注意：当前 `real` 通过不代表策略有效性已经验证。当前 real 通过的主要价值是：

- 输出协议完整；
- 非占位证据存在；
- 数据版本可记录；
- 本地快照可读取；
- 后续真实数据接入有稳定验收门槛。

---

## 当前目录与模块说明

| 路径 | 作用 |
|---|---|
| `src/suishi_north_backtest/config.py` | 回测配置，含数据源、快照、输出目录 |
| `src/suishi_north_backtest/cli.py` | 主 CLI，运行 MVP-1 回测 |
| `src/suishi_north_backtest/engine.py` | 输出写入引擎，只依赖 `Mvp1DataSet` |
| `src/suishi_north_backtest/data.py` | 数据源边界、fixture provider、a-stock-data 本地快照 provider |
| `src/suishi_north_backtest/snapshot_builder.py` | 将已有 MVP-1 输出目录转换为本地快照 |
| `scripts/acceptance_check.py` | smoke/full/real 验收脚本 |
| `tests/test_mvp1_skeleton.py` | 回测输出与 fixture 证据测试 |
| `tests/test_acceptance_check.py` | 验收脚本测试 |
| `tests/test_data_provider.py` | 数据源 provider 测试 |
| `tests/test_snapshot_builder.py` | 快照构建器测试 |

---

## 后续总路线图

后续所有工作建议严格按阶段推进。每个阶段遵循：

1. 一个分支；
2. 一个 PR；
3. 先写测试；
4. 实现最小功能；
5. 运行 `python -m pytest`；
6. 运行相关验收命令；
7. review；
8. squash merge。

---

# 后续阶段计划

## 阶段 A：原始 a-stock-data 快照输入规范

### 目标

定义外部 `a-stock-data` 原始数据在本仓库中的本地落盘格式，不直接把未知字段形状塞进策略引擎。

### 建议新增

- `docs/data/a-stock-data-raw-snapshot-format.md`
- `src/suishi_north_backtest/raw_data.py`
- `tests/test_raw_data_contract.py`

### 原始数据建议目录

```text
data/a_stock_data_raw/<snapshot-name>/
```

建议最小文件：

```text
manifest.json
stock_daily.csv
index_daily.csv
industry_map.csv
industry_daily_amount.csv
trading_calendar.csv
```

### `manifest.json` 建议字段

```json
{
  "data_version": "a-stock-data-raw-2026-05-18",
  "source": "a-stock-data",
  "created_at": "2026-05-18T00:00:00+08:00",
  "stock_daily_file": "stock_daily.csv",
  "index_daily_file": "index_daily.csv",
  "industry_map_file": "industry_map.csv",
  "industry_daily_amount_file": "industry_daily_amount.csv",
  "trading_calendar_file": "trading_calendar.csv"
}
```

### 测试

- 缺少 raw snapshot 目录时报错。
- 缺少 manifest 时报错。
- manifest 缺少 `data_version` 时报错。
- 缺少必需 raw 文件时报错。
- CSV 表头缺字段时报错。

### 验收

```powershell
python -m pytest tests/test_raw_data_contract.py
python -m pytest
```

---

## 阶段 B：原始行情读取与字段标准化

### 目标

将 raw `a-stock-data` CSV 读取为内部标准表，不做策略逻辑。

### 建议新增

- `src/suishi_north_backtest/market_data.py`
- `tests/test_market_data.py`

### 内部标准字段

`stock_daily`：

```text
trade_date,symbol,open,high,low,close,volume,amount,is_st,limit_up,limit_down,is_suspended
```

`index_daily`：

```text
trade_date,index_code,open,high,low,close,volume,amount
```

`industry_map`：

```text
symbol,industry_level2
```

`industry_daily_amount`：

```text
trade_date,industry_level2,amount
```

`trading_calendar`：

```text
trade_date,is_open
```

### 测试

- 数值字段可转 float。
- 日期字段可排序。
- 股票、指数、行业字段命名统一。
- 中文行业名可正常读取。
- 空值、停牌、无开盘价有显式标记。

### 验收

```powershell
python -m pytest tests/test_market_data.py
python -m pytest
```

---

## 阶段 C：股票池与可交易性过滤

### 目标

从标准化行情生成每日可交易股票池。

### 规则

- 纳入主板、创业板、科创板。
- 暂不纳入北交所。
- 排除 ST / `*ST`。
- 排除退市整理。
- 排除新股窗口。
- 排除长期停牌。
- 排除低流动性。
- 买入日排除停牌、无开盘价、一字涨停。
- 卖出日遇停牌、一字跌停应顺延。

### 建议新增

- `src/suishi_north_backtest/universe.py`
- `tests/test_universe.py`

### 输出证据

- `universe.csv`
- `tradability_audit.csv`

### 测试

- ST 被排除。
- 新股被排除。
- 停牌买入被跳过。
- 一字涨停买入被跳过。
- 一字跌停卖出顺延。

---

## 阶段 D：二级行业主线代理

### 目标

实现二级行业成交金额主线判断。

### 规则

- 强主线：连续 3 个交易日进入二级行业成交金额前 5。
- 观察主线：近 5 日至少 3 次进入前 5。
- 启动日：首次进入前 5，只记录，不直接视为强主线。
- 所有计算必须受 `as_of` 限制，不允许未来函数。

### 建议新增

- `src/suishi_north_backtest/mainline.py`
- `tests/test_mainline.py`

### 输出证据

- `industry_mainline.csv`
- `mainline_audit.csv`

### 测试

- 连续 3 日前 5 触发强主线。
- 近 5 日 3 次前 5 触发观察主线。
- 只用 `as_of` 及之前数据。
- 股票能正确映射到二级行业。

---

## 阶段 E：ABCD / C 点候选识别

### 目标

从日线/周线结构识别候选。

### 规则

- AB 涨幅默认 ≥ 20%。
- BC 回撤不超过 AB 涨幅 60%。
- B 后 3-20 个交易日内寻找 C 点。
- 日线代理转强：站上 5 日均线或连续 2 日收盘不创新低。
- 信号日距离 C 点低点不超过 8%。
- 周线方向和年线弱结构过滤生效。
- 所有判断必须受 `as_of` 限制。

### 建议新增

- `src/suishi_north_backtest/signals.py`
- `tests/test_signals.py`

### 输出证据

- `candidates.csv`
- `signal_audit.csv`

### 测试

- 满足 AB / BC / C 点窗口时生成候选。
- 超过 C 点距离 8% 不生成候选。
- 未来数据不能影响当前信号。
- 周线/年线过滤失败时跳过。

---

## 阶段 F：候选排序与组合开仓约束

### 目标

实现组合级候选排序和开仓限制。

### 规则

- 每日最多新开 1 笔。
- 每周最多新开 2 笔。
- 最大同时持仓 3 只。
- 已持仓股票重复信号跳过。
- 同日多个候选只选排序最高者。
- 主线过滤轨只允许强主线候选。

### 建议新增

- `src/suishi_north_backtest/portfolio.py`
- `tests/test_portfolio_constraints.py`

### 输出证据

- `selected_candidates.csv`
- `skipped_trades.csv`

### 测试

- 多候选只选最高分。
- 满仓跳过。
- 日开仓上限生效。
- 周开仓上限生效。
- 重复持仓跳过。

---

## 阶段 G：T+1 执行、仓位 sizing、成本与滑点

### 目标

实现真实组合交易执行。

### 规则

- T 日收盘信号，T+1 开盘买入。
- 单笔风险 1%。
- 整手交易。
- 现金约束。
- 买入佣金、买入滑点计入。
- 卖出佣金、印花税、卖出滑点计入。

### 建议新增

- `src/suishi_north_backtest/execution.py`
- `tests/test_execution.py`

### 输出证据

- `trades.csv`
- `cash_ledger.csv`

### 测试

- T+1 开盘价成交。
- 一字涨停买入跳过。
- 成本进入现金和净值。
- 股数按整手。
- 现金不足时缩小或跳过。

---

## 阶段 H：退出规则与顺延卖出

### 目标

实现 MVP-1 卖出逻辑。

### 规则

- 结构止损：跌破 C 点低点。
- 应急止损：买入价下跌 5%。
- 时间止损：买入后 3 个交易日无浮盈。
- 第一目标：到 B 点或 2R 只记录，不强制卖出。
- 趋势退出：最高收盘价回撤 8%。
- 硬最大持仓：30 个交易日。
- 退出信号后次日开盘卖出。
- 停牌或一字跌停无法卖出时顺延。

### 建议新增

- `src/suishi_north_backtest/exits.py`
- `tests/test_exits.py`

### 输出证据

- `exit_audit.csv`
- `trades.csv` 中退出字段完整。

### 测试

- 每类退出规则单独触发。
- 优先级：止损优先，其次时间止损、趋势退出、硬最大持仓。
- 停牌顺延。
- 一字跌停顺延。

---

## 阶段 I：双轨回测

### 目标

实现纯结构轨和主线过滤轨公平对比。

### 规则

- 纯结构轨不使用主线硬过滤。
- 主线过滤轨只允许强主线行业候选。
- 两轨使用相同股票池、成本、执行、退出规则。

### 建议新增

- `src/suishi_north_backtest/tracks.py`
- `tests/test_tracks.py`

### 输出证据

- `track_comparison.csv`
- `metrics.json.tracks`

### 测试

- 两轨输入候选差异仅来自主线过滤。
- 成本和退出规则一致。
- 指标可比。

---

## 阶段 J：指数基准与样本区间评估

### 目标

输出真实基准对比和样本区间指标。

### 基准

- CSI300 / 沪深300
- CSI500 / 中证500
- CSI1000 / 中证1000

### 样本区间

- `sample_in`: 2018-01-01 到 2022-12-31
- `sample_out`: 2023-01-01 到最新完整交易日
- `recent`: 2024-01-01 到最新完整交易日

### 建议新增

- `src/suishi_north_backtest/metrics.py`
- `tests/test_metrics.py`

### 输出证据

- `benchmark_comparison.csv`
- `metrics.json`

### 测试

- 累计收益正确。
- 最大回撤正确。
- 超额收益正确。
- 各区间均有输出。
- 缺基准数据时报错或明确跳过。

---

## 阶段 K：参数敏感性与防过拟合

### 目标

实现真实参数扰动回测。

### 参数

- AB 最小涨幅。
- BC 最大回撤。
- C 点距离。
- 趋势退出回撤。
- 最大持仓天数。
- 主线确认天数。

### 建议新增

- `src/suishi_north_backtest/sensitivity.py`
- `tests/test_sensitivity.py`

### 输出证据

- `sensitivity.csv`

### 测试

- 至少 baseline + 一个扰动。
- 样本内改善、样本外退化时标记过拟合风险。
- 不自动替换默认参数。

---

## 阶段 L：原始 a-stock-data → MVP-1 输出目录转换器

### 目标

把前面所有模块串起来，从 raw snapshot 自动生成完整 MVP-1 输出目录。

### 建议新增

- `src/suishi_north_backtest/raw_snapshot_builder.py`
- `tests/test_raw_snapshot_builder.py`

### 命令设计

```powershell
python -m suishi_north_backtest.raw_snapshot_builder `
  --raw-data-dir data/a_stock_data_raw `
  --raw-snapshot raw-2026-05-18 `
  --output-dir outputs/mvp1-real-2026-05-18
```

然后再生成本地快照：

```powershell
python -m suishi_north_backtest.snapshot_builder `
  --source-output-dir outputs/mvp1-real-2026-05-18 `
  --snapshot snapshot-2026-05-18 `
  --data-dir data/a_stock_data_snapshots `
  --data-version a-stock-data-snapshot-2026-05-18 `
  --overwrite
```

最后验收：

```powershell
python -m suishi_north_backtest.cli `
  --data-source a-stock-data `
  --data-snapshot snapshot-2026-05-18 `
  --data-dir data/a_stock_data_snapshots `
  --output-dir outputs/mvp1-a-stock-data

python scripts/acceptance_check.py --profile real `
  --output-dir outputs/acceptance-mvp1
```

注意：当前 `acceptance_check.py` 会自己运行 CLI，默认 fixture。后续如果要验收 a-stock-data，应扩展验收脚本参数支持：

```powershell
python scripts/acceptance_check.py --profile real `
  --data-source a-stock-data `
  --data-snapshot snapshot-2026-05-18 `
  --data-dir data/a_stock_data_snapshots
```

---

## 阶段 M：扩展验收脚本支持数据源参数

### 目标

让 `acceptance_check.py` 可以验收 fixture 或 a-stock-data，而不是固定运行默认 fixture。

### 建议修改

`scripts/acceptance_check.py` 增加：

- `--data-source`
- `--data-snapshot`
- `--data-dir`

并将参数传给 CLI。

### 测试

- 默认仍使用 fixture。
- 指定 `--data-source a-stock-data` 时传参正确。
- 缺 snapshot 时能暴露 provider 错误。

### 验收

```powershell
python scripts/acceptance_check.py --profile real
python scripts/acceptance_check.py --profile real `
  --data-source a-stock-data `
  --data-snapshot snapshot-2026-05-18 `
  --data-dir data/a_stock_data_snapshots
```

---

# 最终真实 MVP-1 验收标准

当后续 agent 完成真实数据实现后，必须满足以下条件：

## 工程验收

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python scripts/acceptance_check.py --profile smoke
python scripts/acceptance_check.py --profile full
python scripts/acceptance_check.py --profile real
```

全部通过。

## a-stock-data 验收

```powershell
python -m suishi_north_backtest.raw_snapshot_builder `
  --raw-data-dir data/a_stock_data_raw `
  --raw-snapshot <raw-snapshot> `
  --output-dir outputs/mvp1-real

python -m suishi_north_backtest.snapshot_builder `
  --source-output-dir outputs/mvp1-real `
  --snapshot <snapshot> `
  --data-dir data/a_stock_data_snapshots `
  --data-version <data-version> `
  --overwrite

python -m suishi_north_backtest.cli `
  --data-source a-stock-data `
  --data-snapshot <snapshot> `
  --data-dir data/a_stock_data_snapshots `
  --output-dir outputs/mvp1-a-stock-data
```

输出目录必须包含：

```text
equity_curve.csv
trades.csv
skipped_trades.csv
run_metadata.json
metrics.json
candidates.csv
holdings.csv
benchmark_comparison.csv
track_comparison.csv
sensitivity.csv
```

## 内容验收

- `run_metadata.json.data_source = a-stock-data`
- `run_metadata.json.data_version` 不是 fixture。
- `candidates.csv` 来自真实行情计算。
- `trades.csv` 来自真实组合执行。
- `benchmark_comparison.csv` 来自真实指数数据。
- `track_comparison.csv` 来自真实双轨回测。
- `sensitivity.csv` 来自真实参数扰动。
- 无 `fixture`、`占位`、`验收骨架`、`后续接入` 等占位标记。
- 每笔交易能追溯：为什么买、为什么卖、为什么跳过、成本如何计入。

## 人工抽样验收

至少抽 5 笔交易检查：

1. 信号日是否只使用当日及之前数据。
2. AB / BC / C 点计算是否正确。
3. 主线状态是否只使用 `as_of` 前数据。
4. T+1 开盘成交是否正确。
5. 成本、滑点、印花税是否进入资金曲线。
6. 退出触发日与实际卖出日是否正确。
7. 如果顺延卖出，是否有停牌 / 一字跌停证据。

---

## 风险清单

### 风险 1：把 fixture real 通过误解为策略有效性通过

当前 fixture real 通过只是系统证据链通过，不是策略验证。

处理：所有文档和 PR 必须明确 fixture 与真实 A 股历史回测的区别。

### 风险 2：原始 a-stock-data 字段形状不稳定

处理：必须通过 raw data contract 层标准化，不允许策略逻辑直接引用外部字段名。

### 风险 3：未来函数

处理：所有信号、主线、排序、退出必须带 `as_of` 测试。

### 风险 4：样本外污染

处理：参数敏感性只能报告，不得自动替换默认参数；样本外单独输出。

### 风险 5：Windows / Excel CSV 中文乱码

处理：用户可见 CSV 一律 `utf-8-sig`。

### 风险 6：Windows 文件占用

处理：CLI 或验收脚本遇到 PermissionError 时提示关闭 Excel / WPS / 预览窗格，或更换输出目录。

---

## 给下一位 agent 的执行建议

1. 先读：
   - `AGENTS.md`
   - `CONTEXT.md`
   - `docs/adr/0002-mvp-1-daily-close-backtest-scope.md`
   - 本文档
2. 本地先跑：

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python scripts/acceptance_check.py --profile real
```

3. 不要直接改 `engine.py` 堆策略逻辑。应按模块拆分：raw data → market data → universe → mainline → signals → portfolio → execution → exits → metrics → sensitivity。
4. 每阶段只做一个 PR。
5. 每阶段必须补测试。
6. 每阶段合并前必须 review。
7. 真实数据阶段必须持续强调：回测结果是研究输出，不是投资建议。

---

## 下一步最推荐的第一个任务

建议下一位 agent 先做：

> 阶段 M：扩展验收脚本支持 `--data-source` / `--data-snapshot` / `--data-dir`。

原因：

- 当前验收脚本默认运行 fixture。
- 真实数据接入后，需要同一个验收入口验收 `a-stock-data`。
- 这一步能先建立后续真实数据开发的反馈闭环。

完成后再进入：

> 阶段 A：定义 raw a-stock-data 原始快照输入规范。

这符合 TDD 习惯：先让验收工具能选数据源，再逐步接入真实 raw 数据。
