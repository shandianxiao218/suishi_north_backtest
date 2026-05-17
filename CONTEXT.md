# suishi_north_backtest Context

## Project purpose

This repository builds a backtesting and optimization system for the 随势向北股票趋势交易系统.

The system should turn a discretionary trend-trading framework into reproducible, auditable research code.

The outputs are educational trading research artifacts, not investment advice.

## Core trading maxim

有主线才看股，有级别才定策略，有信号才下单，有止损才持仓，有复盘才迭代。

## Data source

Market data comes from `a-stock-data`.

The backtest system should treat the data source as an adapter boundary. Strategy logic should not depend directly on vendor-specific data shapes.

## Timeframe model

| Layer | Timeframe | Responsibility |
|---|---|---|
| Market environment | Index / theme level | Decide whether the system is allowed to trade |
| Big cycle | Weekly | Direction filter |
| Trading cycle | Daily | Define AB, BC, C-point area, and candidate state |
| Execution cycle | 60-minute | Define current-trend reversal, entry trigger, and structural stop |

In this repo, `当前走势` means the 60-minute execution timeframe trend unless an ADR changes it.

## Core strategy concepts

### 主线

A tradable market theme with sector linkage, continuity, liquidity, and identifiable leaders/followers.

The system should reduce exposure or stay in cash when there is no clear main theme.

### AB 段

A clear daily-level advance from A to B.

Default minimum rise: 20%.

### BC 调整

A controlled pullback or consolidation after B.

Default maximum retracement: 60% of the AB gain.

### C 点

The area near the end of BC where downside momentum weakens and the 60-minute execution timeframe begins to turn upward.

C must be identifiable using only data available on or before the selection date.

### D 点

Possible later expansion after C. D is not required to have happened at candidate selection time.

## Default parameters

| Parameter | Default |
|---|---|
| AB minimum rise | 20% |
| BC maximum retracement | 60% of AB gain |
| Emergency stop | -5% from entry |
| Time stop | 3 trading days |
| Max trades per day | 1 |
| Max trades per week | 2 |
| Single-trade account risk | 0.5%-1% |

## Backtest invariants

- No look-ahead bias.
- Every signal must be computed as-of the selection timestamp.
- Later price action must not be used to define A, B, C, entry, or stop.
- Corporate actions, suspensions, limit-up/limit-down constraints, liquidity, and transaction costs should be modeled explicitly where data allows.
- Every backtest run should record the data version, parameter set, universe, date range, and code version.

## Engineering direction

Prefer a layered architecture:

1. Data adapters
2. Calendar and market-session utilities
3. Feature computation
4. Strategy signal generation
5. Execution simulation
6. Portfolio and risk model
7. Metrics and reporting
8. Parameter optimization and validation

Keep strategy rules deterministic and testable.
