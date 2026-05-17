# 交接文档：MVP-1 当前状态

日期：2026-05-17

仓库：`shandianxiao218/suishi_north_backtest`

## 当前结论

本仓库已经完成 MVP-1 的项目约定、领域文档、ADR、任务拆分、pre-commit 工程护栏，以及最小可运行的组合回测骨架。

当前阶段仍是 **MVP-1 日线收盘级组合回测骨架**，不是完整实盘交易系统。

## 已完成事项

### 1. 项目协作与领域文档

已创建并中文化：

- `AGENTS.md`
- `CONTEXT.md`
- `docs/agents/issue-tracker.md`
- `docs/agents/triage-labels.md`
- `docs/agents/domain.md`
- `docs/adr/0001-record-architecture-decisions.md`
- `docs/adr/0002-mvp-1-daily-close-backtest-scope.md`

关键约定：

- 默认中文交流、中文 issue、中文 ADR、中文回测报告。
- Issue tracker 使用 GitHub Issues。
- Triage 标签使用：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。
- 领域文档使用单上下文：根目录 `CONTEXT.md` + `docs/adr/`。

### 2. MVP-1 策略与回测范围

已在 `ADR-0002` 中锁定：

- 第一目标：先验证策略有效性，参数优化延后。
- 数据颗粒度：MVP-1 使用周线 + 日线，60 分钟真实执行周期放到 MVP-2。
- 股票池：沪深 A 股核心股票池，主板 + 创业板 + 科创板，暂不纳入北交所。
- 主线代理：二级行业成交金额连续 3 个交易日进入前 5 名，视为强主线。
- 信号：T 日收盘后生成，T+1 开盘买入。
- 组合级回测：只使用组合级回测，不使用单票独立统计作为主要结论。
- 初始资金：100 万。
- 单笔风险：1% 账户权益。
- 最大同时持仓：3 只。
- 每日最多新开仓：1 笔。
- 每周最多新开仓：2 笔。
- 交易成本：单边佣金 0.03%，卖出印花税 0.05%，买卖各 0.05% 滑点。
- 基准指数：沪深300、中证500、中证1000。
- 样本切分：2018-2022 样本内，2023 至今样本外，2024 至今近期窗口。

### 3. GitHub Issues 拆分

已创建 12 个 `ready-for-agent` issue：

| Issue | 标题 | 状态 |
|---:|---|---|
| #1 | 建立最小可运行的 MVP-1 组合回测骨架 | 已完成并合并 |
| #2 | 接入日线、周线和指数基准数据适配器 | 下一步 |
| #3 | 实现沪深核心 A 股股票池与可交易性过滤 | 待做 |
| #4 | 实现二级行业成交金额主线代理 | 待做 |
| #5 | 实现日线 ABCD 与 C 点代理候选识别 | 待做 |
| #6 | 实现候选排序与组合开仓约束 | 待做 |
| #7 | 实现 T+1 开盘成交、仓位 sizing、交易成本与滑点 | 待做 |
| #8 | 实现 MVP-1 退出规则与顺延卖出 | 待做 |
| #9 | 实现纯结构组合轨与主线过滤组合轨对比 | 待做 |
| #10 | 实现指数基准对比与样本区间评估 | 待做 |
| #11 | 实现 MVP-1 回测报告与审计日志 | 待做 |
| #12 | 实现 MVP-1 参数敏感性与样本外防过拟合检查 | 待做 |

推荐继续顺序：#2 → #3 → #4 → #5 → #6 → #7 → #8 → #9 → #10 → #11 → #12。

## 已合并 PR

### PR #13：添加 pre-commit 工程护栏

合并提交：`37415bd2ff44e0afe4cd4111d9c05f4373a45c57`

内容：

- `package.json`
- Husky
- lint-staged
- Prettier
- `.husky/pre-commit`

注意：由于 GitHub contents API 无法可靠设置可执行位，`prepare` 脚本中加入了 `chmod +x .husky/pre-commit`。

### PR #14：实现 MVP-1 组合回测骨架

合并提交：`91ea8d3021906825f7560a826da6dbcf72f79c2a`

内容：

- Python 项目结构
- `pyproject.toml`
- `src/suishi_north_backtest/config.py`
- `src/suishi_north_backtest/engine.py`
- `src/suishi_north_backtest/cli.py`
- `tests/test_mvp1_skeleton.py`
- `README.md`
- `.gitignore`

实现了最小 MVP-1 骨架：运行后输出：

- `equity_curve.csv`
- `trades.csv`
- `skipped_trades.csv`
- `run_metadata.json`

### PR #15：修复 CSV 中文显示乱码

合并提交：`ad61b7e2db42d9d3d24de03e17e39e0a17e330ae`

内容：

- CSV 输出编码从 `utf-8` 改为 `utf-8-sig`。
- 增加回归测试，确保 CSV 文件带 UTF-8 BOM。

原因：Windows/Excel 打开无 BOM UTF-8 CSV 时可能把中文误判为 ANSI/GBK，导致乱码。

## 本地开发与运行

### 推荐环境

- Python 3.11
- Windows PowerShell 可用
- 建议使用虚拟环境，但当前项目也可直接用全局 Python 开发

### 初始化

```powershell
git checkout main
git pull
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 运行测试

```powershell
python -m pytest
```

或：

```powershell
npm run test
```

### 运行 MVP-1 骨架

```powershell
python -m suishi_north_backtest.cli --output-dir outputs/mvp1-skeleton
```

或：

```powershell
suishi-north-backtest --output-dir outputs/mvp1-skeleton
```

### 输出文件

默认输出目录：`outputs/mvp1-skeleton/`

包含：

- `equity_curve.csv`
- `trades.csv`
- `skipped_trades.csv`
- `run_metadata.json`

## 已知本地问题与处理方式

### 1. `No module named suishi_north_backtest`

原因：项目使用 `src/` 布局，未安装本地包时 Python 找不到模块。

解决：

```powershell
python -m pip install -e ".[dev]"
```

临时方案：

```powershell
$env:PYTHONPATH = "src"
python -m suishi_north_backtest.cli --output-dir outputs/mvp1-skeleton
```

### 2. `No module named pytest`

原因：开发依赖未安装。

解决：

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

### 3. `PermissionError: outputs\\mvp1-skeleton\\trades.csv`

原因：Windows 上 CSV 被 Excel、WPS 或文件资源管理器预览窗格占用。

解决：关闭打开该 CSV 的程序，或删除输出目录后重跑：

```powershell
Remove-Item -Recurse -Force .\outputs\mvp1-skeleton -ErrorAction SilentlyContinue
python -m suishi_north_backtest.cli --output-dir outputs/mvp1-skeleton
```

也可以换一个新输出目录：

```powershell
python -m suishi_north_backtest.cli --output-dir "outputs/mvp1-skeleton-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

### 4. CSV 中文乱码

已通过 PR #15 修复。新生成的 CSV 使用 `utf-8-sig`，Excel 应能正确识别中文。

## 下一步建议

### 立即下一步：`@tdd #2`

Issue #2：接入日线、周线和指数基准数据适配器。

开发策略：

1. 先写测试定义内部数据结构。
2. 用 fixture 或小型本地样例数据跑通适配层。
3. 再接入 `a-stock-data`。
4. 保持策略逻辑不直接依赖 `a-stock-data` 字段形状。
5. 输出统一内部结构，后续 #3-#12 全部依赖该结构。

### #2 的关键验收点

- 可以读取股票日线行情。
- 可以从日线生成或读取周线。
- 可以读取沪深300、中证500、中证1000基准行情。
- 数据适配层隐藏 `a-stock-data` 的接口差异。
- 本地缓存或数据快照机制支持复现。
- 缺失数据、停牌、无开盘价有显式标记。

## 交接给下一位 agent 的注意事项

1. 先读 `AGENTS.md`、`CONTEXT.md` 和 `docs/adr/0002-mvp-1-daily-close-backtest-scope.md`。
2. 不要跳过 TDD：每个 issue 先写测试，再写最小实现。
3. 每个 PR 合并前必须用 `@review`。
4. 当前没有独立 `@tdd` 技能时，按 TDD 流程手动执行。
5. 数据层从 #2 开始，不要在 #1 骨架里补真实数据逻辑。
6. 所有 CSV 用户可见输出应继续使用 `utf-8-sig`，避免 Windows/Excel 中文乱码。
7. 回测结果必须始终表述为研究输出，不得表述为投资建议。
