# Domain Docs

How engineering skills should consume this repo's domain documentation when exploring the codebase.

## Layout

This repo uses a single-context layout:

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Before exploring, read these

- `CONTEXT.md` at the repo root.
- Relevant ADRs under `docs/adr/`.

If any of these files do not exist yet, proceed silently and infer from the current task.

## Use the glossary's vocabulary

When output names a domain concept, use the term as defined in `CONTEXT.md`.

Important domain terms include:

- 随势向北
- 主线
- 周线方向
- 日线 AB 段
- 日线 BC 调整
- C 点
- D 点
- 当前走势
- 60 分钟转向
- 结构止损
- 应急止损
- 时间止损
- 回测样本
- 未来函数 / look-ahead bias
- 参数优化
- 样本内 / 样本外验证

## Flag ADR conflicts

If output contradicts an existing ADR, surface it explicitly rather than silently overriding.
