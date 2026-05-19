# 质量复核 TODO 列表

基于人工审查确认的问题清单。每项标注状态、文件、测试和验收方式。

## 已确认问题

### Q-01: execution.py 成本模型——滑点重复计入

- **状态**: 待修复
- **文件**: `src/suishi_north_backtest/execution.py`
- **问题**: `execute_buy()` 中 `entry_price = open_price * (1 + slippage_rate)` 已将滑点计入成交价，但第 99 行又额外计算 `slippage = shares * open_price * slippage_rate` 并从现金中扣除，导致滑点被双倍计入。
- **修复方案**: 采用方案 A——成交价含滑点。`cash -= shares * adjusted_entry_price + commission`。slippage 只作为审计字段记录，不再额外扣现金。
- **测试**: `test_execution_does_not_double_count_slippage`
- **验收**: `python -m pytest tests/test_execution.py -q`

### Q-02: execution.py 一字涨停判断不完整

- **状态**: 待修复
- **文件**: `src/suishi_north_backtest/execution.py`
- **问题**: 第 50 行 `open_price >= limit_up` 不是一字涨停判断。一字涨停应要求 `open == high == low == close == limit_up`。
- **修复方案**: 扩展 `execute_buy()` 入参，接收 high/low/close，统一一字涨停判断。
- **测试**: 现有 `test_buy_skipped_when_limit_up` 需更新
- **验收**: `python -m pytest tests/test_execution.py -q`

### Q-03: exits.py 退出语义不正确

- **状态**: 待修复
- **文件**: `src/suishi_north_backtest/exits.py`
- **问题**: `check_exit()` 在信号检测时直接使用 `current_bar.close` 作为 `exit_price`。MVP-1 语义是 T 日收盘检测退出信号、T+1 开盘执行卖出。信号检测不应返回实际卖出价。
- **修复方案**: 拆分为 `detect_exit_signal()` 和 `execute_sell()`。信号检测只返回信号类型和触发日，不返回卖出价。
- **测试**: `test_exit_signal_detected_on_t_close_but_sell_executes_on_t_plus_1_open`
- **验收**: `python -m pytest tests/test_exits.py -q`

### Q-04: exits.py 一字跌停判断不完整

- **状态**: 待修复
- **文件**: `src/suishi_north_backtest/exits.py`
- **问题**: `_can_sell()` 中 `close <= limit_down` 不是一字跌停判断。一字跌停应要求 `open == high == low == close == limit_down`。
- **修复方案**: 统一为一字跌停判断 `open == high == low == close == limit_down`。
- **测试**: `test_limit_down_defers_exit` 需更新
- **验收**: `python -m pytest tests/test_exits.py -q`

### Q-05: market_data.py ST 识别硬编码为 False

- **状态**: 待修复
- **文件**: `src/suishi_north_backtest/market_data.py`
- **问题**: 第 113 行 `is_st=False` 硬编码，不从 CSV 读取也不从 stock_name 推导。
- **修复方案**: 支持从 CSV 读取 `is_st` 字段或从 `stock_name` 推导（ST / \*ST）。
- **测试**: `test_market_data_reads_is_st_or_derives_from_stock_name`
- **验收**: `python -m pytest tests/test_market_data.py -q`

### Q-06: acceptance_check.py 缺少 metadata 参数一致性校验

- **状态**: 待修复
- **文件**: `scripts/acceptance_check.py`
- **问题**: `validate_metadata()` 不校验 `data_source`、`data_version`、`parameter_set`、`universe` 与请求参数一致。
- **修复方案**: 增加 `data_source` 一致性校验，并在报告中打印 `data_source`、`data_snapshot`、`data_dir`。
- **测试**: 新增 test 验证 `data_source` 不一致时报错
- **验收**: `python -m pytest tests/test_acceptance_check.py -q`

## 已修复问题

（本分支修复后在此记录）

## 仍未完成问题

- universe.py `_is_buy_restricted` 和 `_is_sell_deferred` 也使用简化的涨停/跌停判断，但与 execution/exits 不同模块，本阶段暂不修改，后续统一处理。
- 端到端集成测试覆盖不足：当前各模块独立测试，缺少从 raw snapshot 到策略执行的完整串联测试。
