# ADR-0003：双 Agent 协作开发流程

## 状态

已接受

## 背景

本仓库需要一种可复现的开发流程，让 AI agent 能够自主完成从规划到实现到 review 的完整闭环，减少人工中转。

## 决策

采用两个 pi agent 实例，不同模型，不同角色，通过 tmux + pi extension 协作：

| 角色 | 代号 | 默认模型 | 职责 |
|---|---|---|---|
| 规划 + review agent | 架构师 (architect) | GLM-5.1 | 策略方向决策、工程拆分为 issue、review PR、合并 PR |
| 实现 + 执行 agent | 码农 (coder) | GLM-4.7 | 领 issue、写代码、跑测试、提 PR、响应 review 意见 |

### 工作流程

```
人类 ↔ 5.1 对话
       ↓
5.1 规划 → 拆 issue (ready-for-agent)
       ↓
5.1 (架构师) 通过 tmux 启动 4.7 (码农)
       ↓
码农领 issue → 写代码 → 跑测试 → 提 PR
       ↓
码农输出完成标记
       ↓
架构师检测标记 → 自动 review PR
       ├── 通过 → 合并
       └── 不通过 → 写 review comments
                      ↓
              码农读评论 → 改代码 → 重推
                      ↓
              架构师重新 review → ... → 合并
       ↓
架构师汇报结果给人类
```

### 操舵模型升级机制

同一 issue 连续两次 review 不通过时，架构师自动将码农的模型从 GLM-4.7 升级到 GLM-5-Turbo 重做：

```
架构师 review PR
  ├── 通过 → 合并
  ├── 不通过（第 1 次）→ 写 review comments → 码农改代码 → 重推 → 架构师重新 review
  │     ├── 通过 → 合并
  │     └── 不通过（第 2 次）→ 升级码农模型为 GLM-5-Turbo → 从头重做该 issue
  │           ├── 通过 → 合并，后续 issue 码农降回 GLM-4.7
  │           └── 不通过 → 通知人类介入
```

升级只针对当前 issue，下一个 issue 码农自动降回 GLM-4.7。

升级标记：
```
::AGENT-DONE::SUISHI-NORTH::issue=<编号>::pr=<PR编号>::status=success::model=glm-4.7
::AGENT-DONE::SUISHI-NORTH::issue=<编号>::pr=<PR编号>::status=success::model=glm-5-turbo
```

架构师通过 model 字段追踪码农当前使用的模型，决定是否需要升级或降回。

### 完成标记协议

4.7 完成后在 tmux 输出结构化标记行：

```
::AGENT-DONE::<项目标识>::issue=<编号>::pr=<PR编号>::status=success
::AGENT-DONE::<项目标识>::issue=<编号>::status=failed::error=<原因>
```

项目标识：`SUISHI-NORTH`

泛化时只需更换项目标识段。

### 技术方案

Extension 放在项目级 `.pi/extensions/` 目录
- 架构师通过 tmux 启动码农会话
- 架构师通过 `tmux capture-pane` 监控码农输出，检测 `::AGENT-DONE::` 标记
- issue 串行执行，一个做完再做下一个
- 码农的启动指令模板包含：issue 编号、分支名、角色说明、完成标记格式

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

- 人类只需与架构师对话，不需要手动在两个 agent 之间中转。
- Extension 目前是项目级的，泛化到其他项目需要复制并修改项目标识。
- 串行执行意味着规划拆分粒度影响吞吐——issue 太小则 tmux 启动开销大，太大则单次反馈周期长。
- 架构师自动合并 PR 意味着人类信任架构师的 review 质量。如果架构师 review 漏判，错误代码会直接进入主分支。
- 两次 review 不过后码农升级到 GLM-5-Turbo，是最后的自动恢复手段。GLM-5-Turbo 仍不过则必须人类介入。
