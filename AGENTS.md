# 仓库协作说明

本仓库用于构建 `随势向北股票趋势交易系统` 的回测与优化系统，市场数据源使用 `a-stock-data`。

## 交流语言

本项目默认使用中文交流、中文文档和中文 issue 描述。代码命名可以使用英文，但领域术语、策略说明、回测报告和架构决策优先使用中文。

## Agent skills

### Issue tracker

本仓库的任务、PRD 和缺陷记录使用 GitHub Issues：`shandianxiao218/suishi_north_backtest`。详见 `docs/agents/issue-tracker.md`。

### Triage labels

本仓库使用默认五类 triage 标签。详见 `docs/agents/triage-labels.md`。

### Domain docs

本仓库使用单上下文领域文档布局。详见 `docs/agents/domain.md`。

## 领域优先工作规则

在实现或修改核心行为之前，先阅读：

- `CONTEXT.md`
- `docs/adr/` 下相关 ADR

处理交易系统相关任务时，除非任务明确要求修改，否则必须保持 `随势向北` 的系统边界：

- 严格避免未来函数 / look-ahead bias。
- 候选股、交易信号和回测结果只能作为研究输出，不能表述为投资建议。
- 明确区分主线、周线、日线和执行周期。
- 策略参数必须可配置；每次回测必须记录数据版本、参数组合、股票池、时间范围和代码版本。
- 所有可优化参数必须先有默认基线，再做样本外验证。
