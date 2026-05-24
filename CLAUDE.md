# Claude Code 交互说明

本文件是仓库中专门用于和 Claude Code 交互的入口文件。Claude Code 接手本仓库时，应先阅读本文件，再阅读 `AGENTS.md`、`CONTEXT.md`、`README.md` 和最新交接文档。

## 文件使用边界

`CLAUDE.md` 只作为长期稳定规则入口，不作为每次对话记录、临时任务单或测试输出日志。

后续交互按以下分工处理：

1. `CLAUDE.md` 只作为稳定规则入口。
2. 当前任务写进 `TODO_QUALITY_REVIEW.md` 或 PR 描述。
3. 每次测试输出贴 PR 评论。
4. 阶段完成后写 handoff 文档。

不要把每次对话、临时测试输出、执行过程日志或一次性 TODO 追加到本文件。需要频繁更新的内容应放到 PR 描述、PR 评论、GitHub Issues、`TODO_QUALITY_REVIEW.md` 或 `docs/handoff/`。

## 最高优先级规则

1. 使用中文交流、中文提交信息、中文 PR 描述和中文文档。
2. 不要直接提交到 `main`。
3. 所有后续工作必须通过分支和 PR 完成。
4. 每个阶段只做一个清晰范围的 PR。
5. 每个 PR 合并前必须有 review。
6. 每个 PR 必须说明：完成了什么、没有完成什么、如何测试。
7. 不得把 fixture 验收通过表述为真实 A 股历史策略有效性验证完成。
8. 回测输出只能作为研究输出，不能表述为投资建议。
9. 不允许未来函数 / look-ahead bias。
10. 用户可见 CSV 必须继续使用 `utf-8-sig`，避免 Windows / Excel 中文乱码。

## Agent 团队中的 Claude Code 职责

本仓库采用三角色 agent 团队：总管（PI）负责全局把控，Claude Code 负责实现和提交 PR，验收验证（PI）负责独立验收并在通过后合并主线。

Claude Code 必须遵守：

1. 只在任务分支上实现代码，不直接提交 `main`。
2. 只处理总管分配的单一清晰范围；发现范围外问题时，记录到 PR 或 handoff，不顺手扩大范围。
3. 每个 PR 必须包含：变更、没有完成、测试、风险与边界。
4. 行为变化必须有自动化测试或验收脚本覆盖。
5. 验收验证提出整改后，在同一 PR 中修复并重新贴完整测试输出。
6. 未经验收验证通过，不得合并主线。

## 必读文件

开始任何开发前，按顺序阅读：

- `AGENTS.md`
- `CONTEXT.md`
- `README.md`
- `docs/adr/0002-mvp-1-daily-close-backtest-scope.md`
- `docs/handoff/2026-05-18-project-handoff-and-roadmap.md`
- `TODO_QUALITY_REVIEW.md`，如果存在

如果 `TODO_QUALITY_REVIEW.md` 只存在于本地但未提交，请先把它纳入质量修复 PR。

## 当前真实状态

当前仓库已完成：

- MVP-1 工程骨架。
- smoke / full / real 三层验收。
- fixture 数据源。
- `Mvp1DataSet` / `DataProvider` 边界。
- `AStockDataProvider` 本地快照读取。
- `snapshot_builder`，可把已有 MVP-1 输出目录转换为 a-stock-data 本地快照。
- raw a-stock-data 输入规范雏形。
- market data / universe / mainline / signals / portfolio / execution / exits 模块雏形。

当前尚未完成：

- raw a-stock-data 到真实 MVP-1 输出目录的端到端转换器。
- 新增策略模块与 `engine.py` / `AStockDataProvider` 的真实回测闭环集成。
- 真实 A 股历史数据下的策略有效性验证。
- 真实双轨回测、真实基准指标、真实参数敏感性完整闭环。

## 当前质量阻塞项

在继续新增功能前，必须优先处理以下质量问题。

### 1. 恢复 PR / review 工作流

最近有多个阶段性提交直接进入 `main`。后续不得继续直接提交 `main`。

推荐创建分支：

`fix/quality-review-blockers`

### 2. execution.py 成本模型复核

检查并修复买入滑点是否重复计入。

必须明确一种模型：

- 方案 A：成交价含滑点，现金扣减为 `shares * adjusted_entry_price + commission`，slippage 只作为审计字段，不再额外扣现金。
- 方案 B：成交价不含滑点，现金扣减为 `shares * open_price + commission + slippage_cost`。

不得同时把滑点计入成交价和现金扣减。

必须新增或保留测试：`test_execution_does_not_double_count_slippage`。

### 3. execution.py 一字涨停判断统一

买入限制不得只用 `open_price >= limit_up`。

应统一为一字涨停判断：`open == high == low == close == limit_up`。

如果 `execute_buy()` 当前参数不足，应扩展入参或引入交易日 bar 对象。

### 4. exits.py 退出信号与卖出执行分离

MVP-1 语义是：T 日收盘检测退出信号，T+1 开盘执行卖出，停牌 / 一字跌停则顺延。

应拆分为：

- `detect_exit_signal()`
- `execute_sell()`

不得在信号检测函数中直接把 `current_bar.close` 当作实际卖出价。

必须新增或保留测试：`test_exit_signal_detected_on_t_close_but_sell_executes_on_t_plus_1_open`。

### 5. exits.py 一字跌停判断统一

卖出顺延不得只用 `close <= limit_down`。

应统一为一字跌停判断：`open == high == low == close == limit_down`。

### 6. market_data.py ST 识别

`StockDaily.is_st` 不得永远硬编码为 `False`。

至少支持一种方式：

- `stock_daily.csv` 包含 `is_st` 字段。
- 或 `stock_daily.csv` 包含 `stock_name` 字段，并从 `ST` / `*ST` 推导。

必须新增或保留测试：`test_market_data_reads_is_st_or_derives_from_stock_name`。

### 7. acceptance_check.py metadata 强校验

验收脚本已经支持 `--data-source`、`--data-snapshot`、`--data-dir`，但还需要校验输出 `run_metadata.json` 与请求参数一致，至少包括：

- `data_source`
- `data_version`
- `parameter_set`
- `universe`

当请求 `--data-source a-stock-data` 时，必须验证 `run_metadata.json.data_source == "a-stock-data"`。

建议验收报告打印：

- `data_source`
- `data_snapshot`
- `data_dir`

### 8. 最小端到端测试

新增一个最小端到端测试，不要求完整盈利逻辑，但必须证明模块可以串联：

`raw snapshot -> validate_raw_snapshot -> load_market_data -> build_universe -> compute_mainlines -> find_candidates -> select_candidates -> execute_buy -> detect_exit_signal / execute_sell`

建议测试名：`test_raw_to_strategy_modules_minimal_end_to_end_flow`。

## 必须重新运行的测试

质量修复 PR 中必须贴完整输出，不要只写“通过”。

基础测试：

`python -m pytest -q`

分模块测试：

- `python -m pytest tests/test_acceptance_check.py -q`
- `python -m pytest tests/test_raw_data_contract.py -q`
- `python -m pytest tests/test_market_data.py -q`
- `python -m pytest tests/test_universe.py -q`
- `python -m pytest tests/test_mainline.py -q`
- `python -m pytest tests/test_signals.py -q`
- `python -m pytest tests/test_portfolio_constraints.py -q`
- `python -m pytest tests/test_execution.py -q`
- `python -m pytest tests/test_exits.py -q`

三层验收：

- `python scripts/acceptance_check.py --profile smoke`
- `python scripts/acceptance_check.py --profile full`
- `python scripts/acceptance_check.py --profile real`

fixture 到本地快照再验收 a-stock-data：

```powershell
python -m suishi_north_backtest.cli `
  --data-source fixture `
  --data-snapshot fixture-local-run-001 `
  --output-dir outputs/mvp1-skeleton

python -m suishi_north_backtest.snapshot_builder `
  --source-output-dir outputs/mvp1-skeleton `
  --snapshot snapshot-retest-claude `
  --data-dir data/a_stock_data_snapshots `
  --data-version a-stock-data-snapshot-retest-claude `
  --overwrite

python scripts/acceptance_check.py --profile real `
  --data-source a-stock-data `
  --data-snapshot snapshot-retest-claude `
  --data-dir data/a_stock_data_snapshots `
  --output-dir outputs/acceptance-a-stock-data
```

## 后续功能阶段顺序

在上述质量阻塞项修完前，不要继续做阶段 I/J/K。

修复完成后，后续顺序：

1. raw a-stock-data 到 MVP-1 输出目录转换器。
2. 真实双轨回测。
3. 真实基准指标和样本区间评估。
4. 真实参数敏感性。
5. 人工抽样审计工具。

## PR 描述模板

每个 PR 使用以下结构：

```markdown
## 变更

- ...

## 没有完成

- ...

## 测试

- `python -m pytest -q`
- `python scripts/acceptance_check.py --profile real`

## 风险与边界

- 当前仍不能说明真实 A 股历史策略有效性已经验证完成。
```

## 禁止事项

- 禁止直接提交 `main`。
- 禁止跳过测试。
- 禁止把 fixture 输出当成真实历史回测。
- 禁止在没有 `as_of` 约束的情况下实现信号或主线逻辑。
- 禁止把交易建议、买卖建议写进报告。
- 禁止新增大范围功能后不写测试。

## 和其他 agent 的交互方式

如果需要 GPT / 人类复核，请在 PR 描述或 `TODO_QUALITY_REVIEW.md` 中提供：

1. 当前分支名。
2. 基准提交。
3. 最新提交。
4. 变更文件列表。
5. 完整测试输出。
6. 自查结论。
7. 仍未完成事项。

不要只说“测试通过”。必须贴命令和输出。
