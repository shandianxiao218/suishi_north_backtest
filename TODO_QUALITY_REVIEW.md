# 质量复核 TODO 列表

基于人工审查确认的问题清单。每项标注状态、文件、测试和验收方式。

## 已确认问题

### Q-01: execution.py 成本模型——滑点重复计入

- **状态**: 已修复
- **文件**: `src/suishi_north_backtest/execution.py`
- **修复方案**: 采用方案 A——成交价含滑点。`cash -= shares * adjusted_entry_price + commission`。slippage 只作为审计字段记录，不再额外扣现金。
- **测试**: `test_execution_does_not_double_count_slippage` 通过

### Q-02: execution.py 一字涨停判断不完整

- **状态**: 已修复
- **文件**: `src/suishi_north_backtest/execution.py`
- **修复方案**: 扩展 `execute_buy()` 入参接收 high/low/close，统一为一字涨停判断 `open == high == low == close == limit_up`。
- **测试**: `test_buy_skipped_when_one_word_limit_up` 通过

### Q-03: exits.py 退出语义不正确

- **状态**: 已修复
- **文件**: `src/suishi_north_backtest/exits.py`
- **修复方案**: 拆分为 `detect_exit_signal()` 和 `execute_sell()`。信号检测只返回信号类型和触发日，不返回卖出价。旧 `check_exit` 保留为别名。
- **测试**: `test_exit_signal_detected_on_t_close_but_sell_executes_on_t_plus_1_open` 通过

### Q-04: exits.py 一字跌停判断不完整

- **状态**: 已修复
- **文件**: `src/suishi_north_backtest/exits.py`
- **修复方案**: 统一为一字跌停判断 `open == high == low == close == limit_down`。
- **测试**: `test_one_word_limit_down_defers_exit` 通过

### Q-05: market_data.py ST 识别硬编码为 False

- **状态**: 已修复
- **文件**: `src/suishi_north_backtest/market_data.py`
- **修复方案**: 支持从 CSV 读取 `is_st` 字段或从 `stock_name` 推导（ST / \*ST）。空 is_st 字段时回退到 stock_name 推导。
- **测试**: `test_market_data_reads_is_st_or_derives_from_stock_name` 通过

### Q-06: acceptance_check.py 缺少 metadata 参数一致性校验

- **状态**: 已修复
- **文件**: `scripts/acceptance_check.py`
- **修复方案**: 增加 `data_source` 一致性校验和 `data_version`/`parameter_set`/`universe` 必填字段检查。报告打印 `data_source`、`data_snapshot`、`data_dir`。
- **测试**: `test_validate_metadata_checks_data_source_consistency`、`test_validate_metadata_fails_on_data_source_mismatch`、`test_validate_metadata_requires_new_fields` 通过

## 已修复问题

- Q-01: execution.py 成本模型——滑点不再双倍计入（方案 A）
- Q-02: execution.py 一字涨停判断——`open == high == low == close == limit_up`
- Q-03: exits.py 退出语义——拆分为 `detect_exit_signal()` + `execute_sell()`
- Q-04: exits.py 一字跌停判断——`open == high == low == close == limit_down`
- Q-05: market_data.py ST 识别——支持 is_st 字段和 stock_name 推导
- Q-06: acceptance_check.py metadata 校验——data_source/data_version/parameter_set/universe
- 新增：最小端到端测试 `test_raw_to_strategy_modules_minimal_end_to_end_flow`
- 新增：`execute_sell()` 函数（含佣金、印花税、滑点）
- 新增：`SellResult` 数据类

## 仍未完成问题

- universe.py `_is_buy_restricted` 和 `_is_sell_deferred` 使用简化的涨停/跌停判断，后续需统一为一字涨停/跌停判断。
