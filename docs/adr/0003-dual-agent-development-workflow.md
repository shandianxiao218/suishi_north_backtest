# ADR-0003：Subagent 驱动开发流程

## 状态

已接受（2026-05-30 更新，替代原双 Agent tmux 方案）

## 背景

本仓库需要一种可复现的开发流程，让 AI agent 能够自主完成从规划到实现到 review 的完整闭环，减少人工中转。

原方案使用两个独立 pi agent 实例通过 tmux + 完成标记协议协作。现改为单 orchestrator + subagent 模式，由一个主 agent 统一调度 worker、reviewer 等 subagent 角色，减少 tmux 启动开销和标记协议复杂度。

## 决策

采用单 orchestrator + pi-subagents 协作：

| 角色 | 实现方式 | 职责 |
|---|---|---|
| 架构师 (orchestrator) | 主 pi agent 会话 | 策略方向决策、工程拆分为 issue、调度 subagent、review 结果、合并 PR |
| worker | `subagent(agent="worker")` | 实现 issue、跑测试、提 PR |
| reviewer | `subagent(agent="reviewer")` | 代码审查 |
| scout | `subagent(agent="scout")` | 代码侦察 |

### 工作流程

```
人类 ↔ 架构师（主会话）
       ↓
架构师用 scout 侦察代码现状
       ↓
架构师整理实现计划
       ↓
🚨 人类确认计划（重大决策才需要）
       ↓
架构师派 worker(async) 实现 → 跑测试 → 报告 handoff
       ↓
架构师审查 handoff → 决定是否进 review
       ↓
架构师派并行 reviewer(async, fresh context) 审查
       ↓
架构师汇总审查结果
       ├── 严重问题 → 🚨 找人类决策
       ├── 一般问题 → 派 worker(async) 修复 → 重新 review
       └── 通过 → 合并分支、关闭 issue
```

### 确认门控

| 门 | 触发条件 | 谁决定 |
|---|---|---|
| 计划确认 | 每个新 issue 开始前 | 🚨 人类确认 |
| 重大决策 | 策略逻辑理解不确定、实现方向有两个合理选项、reviewer 发现 issue 之外的问题 | 🚨 人类确认 |
| 实现确认 | worker 完成后 | 架构师自行决定 |
| 审查决策 | reviewer 完成后 | 架构师自行决定，严重问题才升级 |

### 模型升级机制

worker 默认使用项目默认模型。当 worker 连续失败或 reviewer 连续两次发现 blocker 时，架构师可将后续 worker 的 model 参数升级为更强模型（如 GLM-5-Turbo）重做。升级只针对当前 issue，下一个 issue 自动降回默认模型。

### 完成标记

不再使用 tmux 完成标记协议。subagent 运行结果通过 `subagent({ action: "status" })` 直接获取，包含文件变更、测试输出和遗留问题。

### 技术方案

使用 pi-subagents 扩展，orchestrator 通过 `subagent(...)` 工具调度：
- `subagent(agent="scout")` — 代码侦察
- `subagent(agent="worker", async=true)` — 异步实现
- `subagent(agent="reviewer", context="fresh")` — 并行审查
- `subagent({ action: "status", id="..." })` — 检查异步任务状态

分支管理：每个 issue 一个分支 `feat/issue-{N}-{slug}`，worker 在分支上工作，reviewer 通过 `git diff` 审查。

合并使用 `review_pr(action="merge")` 或直接 `gh pr merge --squash`。

### Review Checklist

5.1 (架构师) review PR 时按以下清单检查：

**回测可信度：**
- 无未来函数：所有信号、主线、排序、退出只使用 as_of 及以前数据
- 样本边界：样本外数据不泄露到样本内计算
- T+1 时序：买入当日不检测退出，不出现同日买卖
- 退出优先级：结构止损 > 应急止损 > 时间止损 > 趋势退出 > 硬最大持仓
- 双轨公平：唯一差异是主线过滤，排序/成本/退出/股票池一致
- 成本完整：买入佣金+滑点，卖出佣金+印花税+滑点，total_cost = 全部之和
- 参数可配置：新参数有默认值，记录在 parameters.py

**工程标准：**
- 测试全绿：pytest 通过
- 新代码有对应测试
- 分层架构：数据适配 → 特征 → 信号 → 执行 → 报告，无跨层调用
- 输出协议：CSV 字段、JSON 字段符合 output_contract.py

**Agent 协作：**
- PR 范围：只改 issue 要求的内容，无夹带
- Issue 完成度：每个验收标准有代码或测试覆盖
- ADR 一致：不与已有 ADR 矛盾，矛盾则新增 ADR
- 研究免责：输出保留"研究输出，不是投资建议"
- 幸存者偏差标注：报告/文档标注 MVP-1 幸存者偏差限制

**代码质量：**
- 无占位符/fixture 残留
- CSV 编码 utf-8-sig
- 审计字段完整

## 后果

- 人类只需与架构师对话，subagent 调度完全透明。
- 不再依赖 tmux 和完成标记协议，减少环境依赖和启动开销。
- 架构师自动合并 PR 意味着人类信任架构师的 review 质量。如果架构师 review 漏判，错误代码会直接进入主分支。
- 严重问题升级到人类，一般问题架构师自行处理，减少人类中转次数。
- 写操作保持单线程：同一时刻只有一个 worker 在修改代码，避免冲突。
