# 仓库协作说明

本仓库用于构建 `随势向北股票趋势交易系统` 的回测与优化系统，市场数据源使用 `a-stock-data`。

## 交流语言

本项目默认使用中文交流、中文文档和中文 issue 描述。代码命名可以使用英文，但领域术语、策略说明、回测报告和架构决策优先使用中文。

## github

GitHub 写操作改成 阶段批处理模式，尽量减少点确认的次数。

## 与 Claude Code 的协作方式

当需要让 Claude Code 修改代码、修 PR、补测试或执行验收整改时，必须优先使用 GitHub issue / PR Conversation 的 checklist 方式交流，而不是只在聊天中口头说明。

协作要求：

- 将整改意见写成清晰的 issue-style checklist，包含背景、目标、必须整改项、测试要求和提交要求。
- 每个 checklist item 必须可验证、可勾选，避免含糊表述。
- 对 PR review 发现的问题，优先发布到对应 PR 的 Conversation；如是新任务，优先创建或更新 GitHub Issue。
- 指示 Claude Code 时要明确：不要自行合并，完成后回填完整测试输出，等待 review。
- 新对话中如果用户要求“让 Claude 改”“给 Claude 指示”“按 issue 的方式交流”，默认按本节执行。

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
