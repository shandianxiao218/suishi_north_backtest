# 质量复核 TODO 列表

> 基于 2026-05-19 人工代码审查结果，对照 `f03d190` 提交后的代码现状逐项确认。
> 分为：**已修复待验证** / **仍需修复** / **非阻塞改进** 三档。
> 每个 TODO 精确到文件路径、行号、期望行为、验证方法。

---

## A. 阻塞问题（必须修复后才能继续后续阶段）

### A-1. 流程阻塞：恢复 PR/review 工作流

- **文件**: 仓库协作流程
- **现状**: 最新 9 个提交（`2b9f95e` ~ `f03d190`）直接提交到 `main`，未走 PR/review。
- **要求**: 后续所有变更必须通过 feature 分支 + PR + review + squash merge。
- **验证**: `git log --oneline main` 后续提交均为 merge commit 或 squash merge。

---

### A-2. 集成阻塞：engine.py 未接入真实回测主流程

- **文件**: `src/suishi_north_backtest/engine.py:35-59`
- **现状**: `run_mvp1_backtest()` 仍然只做 `DataProvider -> Mvp1DataSet -> 写输出文件`，未调用 `raw_data / market_data / universe / mainline / signals / portfolio / execution / exits`。
- **要求**: engine.py 必须实现完整闭环：
  ```
  raw snapshot -> market_data -> universe -> mainline -> signals -> portfolio -> execution -> exits -> 输出
  ```
- **验证方法**:
  1. `engine.py` 中可 grep 到 `load_market_data`, `build_universe`, `compute_mainlines`, `find_candidates`, `select_candidates`, `execute_buy`, `detect_exit_signal`, `execute_sell` 的调用。
  2. 用 fixture 数据运行 CLI，输出 trades.csv 包含至少一条真实交易记录（非占位数据）。
  3. `test_e2e_pipeline.py` 的端到端测试通过。
- **注意事项**: 不要把当前状态表述为"真实策略回测已完成"。

---

### A-3. 执行成本模型：滑点是否重复扣费

- **文件**: `src/suishi_north_backtest/execution.py:59-105`
- **当前代码行为分析**:
  - L60: `entry_price = open_price * (1 + slippage_rate)` — 成交价含滑点 ✓
  - L88: `trade_amount = shares * entry_price` — 交易金额已含滑点 ✓
  - L101-103: `commission = trade_amount * commission_rate` / `slippage = trade_amount - shares * open_price` / `total_cost = commission + slippage` — 这里的 `slippage` 和 `total_cost` 仅用于审计报告
  - L105: `cash_remaining = cash - trade_amount - commission` — 实际现金扣减 = 股数×含滑点成交价 + 佣金
- **判定**: **现金扣减未重复**。滑点只通过 `entry_price` 间接扣了一次，`total_cost` 仅为审计字段。
- **但仍需修复**: `ExecutionResult.total_cost` 字段名具有误导性，容易让人以为这是额外的扣费项。需要：
  1. 在 `ExecutionResult` 上加注释或重命名为 `audit_total_cost`，明确标注"仅用于审计，非实际扣费"。
  2. 确认所有使用 `total_cost` 的地方不会被误解为额外扣减。
- **验证测试**: `tests/test_execution.py:164-180` — `test_cash_deducted_correctly` 验证 `cash_remaining == initial_cash - shares * entry_price - commission`，已正确。
- **建议新增测试**:
  ```python
  def test_execution_slippage_not_double_counted():
      """滑点不含在现金扣减中，仅通过 entry_price 间接体现。"""
      result = execute_buy(candidate=c, open_price=10.0, cash=1_000_000, equity=1_000_000)
      # cash_remaining = cash - shares * entry_price - commission
      # entry_price 已含滑点，不应再单独扣 slippage
      expected_cash = initial_cash - result.shares * result.entry_price - result.commission
      assert result.cash_remaining == pytest.approx(expected_cash, abs=0.01)
  ```

---

### A-4. 退出规则：退出信号检测 vs T+1 卖出执行

- **文件**: `src/suishi_north_backtest/exits.py:50-110, 113-168`
- **现状**: 已拆成 `detect_exit_signal()` 和 `execute_sell()` 两个函数。
  - `detect_exit_signal()` — 只用 T 日数据，返回 `ExitSignal`，不含卖出执行。
  - `execute_sell()` — 接收 `ExitSignal`，用 T+1 开盘价执行卖出，处理停牌/一字跌停顺延。
- **判定**: **基本已修复**。
- **仍需验证的点**:
  1. `execute_sell()` L136: 一字跌停判断用 `open_price <= limit_down`，仅比较开盘价与跌停价，未使用 universe.py 的四值一致性判断（`open==high==low==close==limit_down`）。是否需要统一？
  2. `execute_sell()` L162: `exit_date=""` — 由调用方填入，但调用方（engine）尚不存在，无法验证。
- **建议新增测试**:
  ```python
  def test_exit_signal_detected_on_t_close_but_sell_executes_on_t_plus_1_open():
      """退出信号在 T 日收盘检测，卖出在 T+1 开盘执行。"""
      t_bar = bar("2024-01-12", close=9.9)  # 触发应急止损
      signal = detect_exit_signal(current_bar=t_bar, entry_price=10.5, ...)
      assert signal.signal_date == "2024-01-12"  # T 日

      # T+1 开盘卖出
      result = execute_sell(signal=signal, symbol="000001", open_price=9.8, ...)
      assert result.executed
      assert result.exit_price != t_bar.close  # 卖出价是 T+1 开盘价，不是 T 日收盘价
  ```

---

### A-5. 一字涨跌停判断：universe.py vs execution/exits 的不一致

- **文件对比**:
  - `universe.py:140-155` — `_is_buy_restricted()` / `_is_sell_deferred()` 使用 `open==high==low==close==limit_up/limit_down`（四值一致性）✓
  - `execution.py:51` — `open_price >= limit_up`（仅开盘价对比）✗
  - `exits.py:136` — `open_price <= limit_down`（仅开盘价对比）✗
- **现状**: universe.py 已修复为严格四值判断，但 execution.py 和 exits.py 仍用宽松判断。
- **问题**: 宽松判断会把普通涨停收盘误判为一字涨停。
  - 例：某股开盘 10.0，收盘涨停 11.0，开盘价 10.0 < 涨停价 11.0 → 不误判（execution.py 恰好安全）
  - 但如果某股开盘价=涨停价（集合竞价涨停），即使盘中打开涨停，也会被误判为无法买入
- **要求**: 统一判断标准。execution.py 和 exits.py 中的一字板判断应与 universe.py 一致，或至少改用 `open==high==low==close==limit_up/limit_down` 四值判断。
- **验证测试**:
  ```python
  # test_execution.py
  def test_buy_allowed_when_only_close_at_limit_up():
      """仅收盘涨停（非一字板）应可买入。"""
      # 普通涨停：open=10.0, close=11.0, limit_up=11.0
      result = execute_buy(candidate=c, open_price=10.0, cash=1_000_000, equity=1_000_000,
                           limit_up=11.0, high=11.0, low=10.0, close=11.0)
      assert result.executed  # 不是一字涨停，应可买入

  def test_buy_blocked_when_true_one_char_limit_up():
      """一字涨停（开=高=低=收=涨停价）不可买入。"""
      result = execute_buy(candidate=c, open_price=11.0, cash=1_000_000, equity=1_000_000,
                           limit_up=11.0, high=11.0, low=11.0, close=11.0)
      assert not result.executed

  # test_exits.py
  def test_sell_deferred_only_for_true_one_char_limit_down():
      """仅一字跌停（开=高=低=收=跌停价）才顺延。"""
      # 普通跌停开盘：open=9.5, 但 high=10.0, low=9.0 → 非一字跌停，可卖出
      result = execute_sell(signal=signal, symbol="000001", open_price=9.5,
                           limit_down=9.5, high=10.0, low=9.0, close=9.0, ...)
      assert result.executed  # 非一字跌停，应可卖出
  ```
- **注意**: 这要求 `execute_buy()` 和 `execute_sell()` 增加 `high`/`low`/`close` 参数，用于判断一字板。

---

### A-6. ST 识别：CSV 字段已支持，但缺少 stock_name 推导

- **文件**: `src/suishi_north_backtest/market_data.py:104-126`
- **现状**:
  - `StockDaily.is_st` 字段已定义 ✓
  - `_load_stock_daily()` L119: `is_st=_to_bool(row.get("is_st"))` 从 CSV 读取 ✓
  - 测试 `test_stock_daily_is_st_read_from_csv` 验证了读取 ✓
- **缺失**:
  - 无 `stock_name` 字段。如果 raw CSV 没有 `is_st` 列但有 `stock_name` 列（如 `ST某某`、`*ST某某`），当前无法推导。
- **要求**: 增加可选 `stock_name` 字段，当 `is_st` 列不存在或为空时，从 `stock_name` 前缀推导 ST 状态。
  - 推导规则：`stock_name` 以 `ST` 或 `*ST` 开头（不区分大小写）→ `is_st = True`
- **验证测试**:
  ```python
  def test_is_st_derived_from_stock_name_prefix():
      """当无 is_st 列但有 stock_name 列时，从名称推导 ST。"""
      # CSV 中 stock_name = "ST某某" → is_st 应为 True
      # CSV 中 stock_name = "某某科技" → is_st 应为 False
  ```
- **验证方法**: 修改 fixture 数据中 000002 为 `stock_name="ST某某"` 但无 `is_st` 列，确认被 universe 排除。

---

### A-7. 验收 metadata 强校验：data_source 必须匹配

- **文件**: `scripts/acceptance_check.py:250-282` — `validate_metadata()`
- **现状**: 校验了 `name, start_date, end_date, initial_cash, code_version, research_limitation, outputs` ✓
- **缺失**:
  1. 未校验 `data_source` 字段存在。
  2. 未校验 `data_source` 与 CLI 参数 `--data-source` 一致。
  3. 未校验 `data_version`, `data_snapshot`, `parameter_set`, `universe` 字段存在（仅在 `real` profile 的 `validate_real_metadata` 中部分检查）。
- **要求**:
  1. `validate_metadata()` 中增加 `data_source` 字段存在性检查。
  2. 当 `--data-source a-stock-data` 时，校验 `metadata["data_source"] == "a-stock-data"`。
  3. 打印 `data_source` / `data_snapshot` / `data_dir` 到验收报告。
- **验证方法**:
  ```powershell
  python scripts/acceptance_check.py --profile full --data-source a-stock-data
  ```
  如果 metadata 中 `data_source` 不是 `a-stock-data`，应报错。

- **验证测试**:
  ```python
  def test_acceptance_metadata_matches_requested_data_source():
      """当 --data-source a-stock-data 时，metadata.data_source 必须是 a-stock-data。"""
  ```

---

### A-8. 端到端集成测试

- **文件**: `tests/test_e2e_pipeline.py`
- **现状**: 已存在，测试了 `raw snapshot → market_data → universe → mainline → signals → portfolio → execution → exits` 全链路 ✓
- **缺失**:
  1. 测试对 candidates 是否找到做了宽松断言（`assert isinstance(candidates, list)`），未验证具体候选。
  2. 没有测试"退出信号日 ≠ 卖出执行日"的时序。
  3. 没有 ST 从 stock_name 推导的端到端覆盖。
  4. 没有"普通涨停可买入 vs 一字涨停不可买入"的区分测试。
- **要求**: 在现有 `test_e2e_pipeline.py` 基础上增加以下场景测试：
  ```python
  def test_e2e_st_excluded_via_stock_name():
      """ST 股从 stock_name 推导后被 universe 排除。"""

  def test_e2e_normal_limit_up_buyable():
      """普通涨停收盘但非一字板，买入不被拒绝。"""

  def test_e2e_exit_signal_t_sell_t_plus_1():
      """退出信号在 T 日触发，卖出在 T+1 执行。"""

  def test_e2e_sell_deferred_on_one_char_limit_down():
      """T+1 一字跌停导致卖出顺延到 T+2。"""
  ```

---

## B. 非阻塞但需要改进的问题

### B-1. signals.py 测试注释错误

- **文件**: `tests/test_signals.py:103`
- **现状**: 注释写"BC 回撤约 67%"，但 `A=10, B=13, C=11.5`，BC 回撤 = `(13-11.5)/(13-10) = 1.5/3 = 50%`，不是 67%。
- **要求**: 修正注释为"BC 回撤 50%"。

---

### B-2. signals.py 缺少候选失败原因审计

- **文件**: `src/suishi_north_backtest/signals.py`
- **现状**: 候选不满足条件时直接 `continue`，无审计记录。
- **建议**: 增加 `CandidateAudit` 数据结构，记录每只股票为何不是候选（AB 涨幅不足 / BC 回撤过大 / C 点窗口不足 / 未止跌转强 / 距 C 点过远）。
- **非阻塞**: 可在后续阶段增加。

---

### B-3. signals.py 缺少周线/年线过滤

- **文件**: `src/suishi_north_backtest/signals.py`
- **现状**: 信号判断只有 AB 涨幅、BC 回撤、C 点窗口、止跌转强、距离 C 点过滤。
- **缺失**: 周线方向过滤、年线弱结构过滤、主线状态参与评分。
- **非阻塞**: 作为后续增强。

---

### B-4. portfolio.py 排序只按 AB 涨幅

- **文件**: `src/suishi_north_backtest/portfolio.py:37`
- **现状**: `sorted(candidates, key=lambda c: -c.ab_gain_pct)`
- **缺失**: 未考虑是否强主线、距 C 点距离、BC 回撤质量、流动性、行业集中度。
- **非阻塞**: 可作为最小版本的排序，后续增强。

---

### B-5. mainline.py 性能可改进

- **文件**: `src/suishi_north_backtest/mainline.py:84, 107`
- **现状**: `sorted_dates.index(date)` 在循环内调用，O(n) 复杂度，数据量大时效率低。
- **建议**: 预构建 `date_to_idx` 字典。
- **非阻塞**: 当前数据量下不影响正确性。

---

### B-6. raw_data.py 仅是 contract，不是完整转换器

- **文件**: `src/suishi_north_backtest/raw_data.py`
- **现状**: 只做 manifest 和 CSV 列校验，不生成回测输出，不与 `AStockDataProvider` 串起来。
- **非阻塞**: 属于后续集成工作。

---

## C. 验收检查清单（手动验证）

完成以上修复后，执行以下命令并验证输出：

### C-1. 基础测试
```powershell
python -m pytest -q
```
**期望**: 全部通过，0 failed。

### C-2. 分模块测试
```powershell
python -m pytest tests/test_acceptance_check.py -q
python -m pytest tests/test_raw_data_contract.py -q
python -m pytest tests/test_market_data.py -q
python -m pytest tests/test_universe.py -q
python -m pytest tests/test_mainline.py -q
python -m pytest tests/test_signals.py -q
python -m pytest tests/test_portfolio_constraints.py -q
python -m pytest tests/test_execution.py -q
python -m pytest tests/test_exits.py -q
python -m pytest tests/test_e2e_pipeline.py -q
```
**期望**: 每个模块全部通过。

### C-3. 验收脚本
```powershell
python scripts/acceptance_check.py --profile smoke
python scripts/acceptance_check.py --profile full
```
**期望**: 两个 profile 均通过。

### C-4. 必须新增的测试用例（在修复 PR 中一并提交）

| # | 测试名 | 验证目标 |
|---|--------|---------|
| 1 | `test_execution_slippage_not_double_counted` | 滑点仅通过 entry_price 间接扣，不重复 |
| 2 | `test_buy_allowed_when_only_close_at_limit_up` | 仅收盘涨停（非一字板）可买入 |
| 3 | `test_buy_blocked_when_true_one_char_limit_up` | 一字涨停（四值相等）不可买入 |
| 4 | `test_sell_deferred_only_for_true_one_char_limit_down` | 仅一字跌停才顺延卖出 |
| 5 | `test_exit_signal_date_differs_from_sell_date` | 退出信号日 ≠ 卖出执行日 |
| 6 | `test_is_st_derived_from_stock_name` | 从 stock_name 推导 ST |
| 7 | `test_acceptance_metadata_matches_data_source` | metadata.data_source 与 --data-source 一致 |

---

## D. 修复优先级排序

```
优先级 1（业务正确性，直接影响回测绩效）:
  → A-5  一字板判断统一（execution/exits vs universe）
  → A-3  total_cost 字段语义澄清
  → A-4  execute_sell 一字跌停判断与 universe 统一

优先级 2（数据完整性）:
  → A-6  ST 从 stock_name 推导
  → A-7  验收 metadata 强校验

优先级 3（集成闭环）:
  → A-2  engine.py 接入真实回测流程
  → A-8  端到端测试增强

优先级 4（流程恢复）:
  → A-1  PR/review 工作流

优先级 5（非阻塞改进）:
  → B-1 ~ B-6
```
