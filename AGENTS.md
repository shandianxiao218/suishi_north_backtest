# Repository instructions

This repository builds a backtesting and optimization system for the 随势向北股票趋势交易系统 using `a-stock-data` as the market data source.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `shandianxiao218/suishi_north_backtest`. See `docs/agents/issue-tracker.md`.

### Triage labels

The repo uses the default five-role triage label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain documentation layout. See `docs/agents/domain.md`.

## Domain-first work rules

Before implementing or changing behavior, read `CONTEXT.md` and any relevant ADRs under `docs/adr/`.

For trading-system work, preserve the 随势向北 system boundaries unless a task explicitly changes them:

- Avoid look-ahead bias.
- Treat candidates and backtest results as research outputs, not investment advice.
- Keep the market-theme, weekly, daily, and 60-minute timeframe separation explicit.
- Make strategy parameters configurable and record the exact parameter set used in every backtest run.
