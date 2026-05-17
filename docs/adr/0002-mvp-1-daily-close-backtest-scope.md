# ADR-0002: MVP-1 daily close backtest scope and tunable parameters

## Status

Accepted for MVP-1

## Context

The first phase of the 随势向北 backtest system is intended to validate strategy effectiveness before aggressive parameter optimization.

The full trading system uses weekly direction, daily ABCD structure, and 60-minute current-trend reversal. MVP-1 intentionally uses a daily-close-level proxy so the project can first validate whether the daily C-point structure has statistical edge before implementing minute-level execution.

## Decision

MVP-1 will run as a daily-close-level structural backtest.

### Primary goal

Validate strategy effectiveness first. Parameter optimization is deferred.

### Universe

MVP-1 uses the core沪深 A-share universe:

- Include: main board, ChiNext, STAR Market.
- Exclude: Beijing Stock Exchange for MVP-1.
- Exclude: ST, *ST, delisting-board stocks.
- Exclude: long suspensions.
- Exclude: stocks listed for fewer than 120 trading days.
- Exclude: low-liquidity stocks.
- Record MVP-1 survivorship-bias limitations explicitly in reports.

### Data granularity

MVP-1 uses:

- Weekly bars for direction filtering.
- Daily bars for AB, BC, C-point proxy, signal generation, and exits.

MVP-2 may add 60-minute bars for true current-trend reversal and entry simulation.

### Entry execution

- Signal is generated after the close of day T.
- Only data available on or before day T may be used.
- Entry is attempted at T+1 open.
- If T+1 is suspended, has no open price, or is one-word limit-up and cannot be bought, skip the trade.
- Position sizing and stops are calculated from actual entry price.

### Daily proxy C-point rules

MVP-1 uses daily stop-falling/turning-strong behavior as a proxy for the full system's 60-minute current-trend reversal.

Default rules:

- AB rise: A to B rise must be at least 20%.
- BC retracement: B to C retracement must not exceed 60% of the AB gain.
- C-point window: C forms 3-20 trading days after B.
- Stop-falling signal: close above MA5, or two consecutive closes without making a new closing low.
- Volume contraction during BC is a scoring feature in MVP-1, not a hard filter.
- Signal-day close must be no more than 8% above the C-point low.
- Weekly filter: weekly direction is not weak, or price is at least above the 20-week moving average.
- Annual moving-average filter: exclude long-term weak structures below the annual moving average.

### Main-theme proxy

MVP-1 uses second-level industry turnover ranking as a mechanical main-theme proxy.

- Strong main line: a second-level industry ranks top 5 by turnover for 3 consecutive trading days.
- Observation main line: a second-level industry ranks top 5 by turnover at least 3 times in the latest 5 trading days.
- Start day: a second-level industry enters top 5 for the first time; record it, but do not treat it as a confirmed hard-filter main line.

The MVP-1 hard-filter main-line track uses the strong-main-line definition.

### Backtest tracks

MVP-1 should report at least two tracks:

1. Pure structure track: weekly + daily ABCD + C-point proxy, without main-theme filter.
2. Main-line-filtered track: pure structure track plus strong second-level-industry turnover main-line filter.

### Exit rules

- Structural stop: break below the C-point low.
- Emergency stop: -5% from actual entry.
- Time stop: exit if no floating profit appears within 3 trading days after entry.
- First target: reaching B point or 2R is recorded as first-target achieved, but does not force full exit in MVP-1.
- Trend exit: exit when close falls at least 8% from the highest close since entry.
- Hard maximum holding period: 30 trading days.
- Exit at next trading day's open after the exit signal.
- If suspended or one-word limit-down and not sellable, defer exit until executable.
- If multiple exit signals occur on the same day, apply conservative priority: structural/emergency stop, then time stop, then trend exit, then hard maximum holding period.

### Tunable parameters for future optimization

These MVP-1 defaults are intentionally recorded as tunable parameters:

| Parameter | MVP-1 default |
|---|---:|
| Minimum AB rise | 20% |
| Maximum BC retracement | 60% of AB gain |
| C-point window after B | 3-20 trading days |
| Maximum distance above C-point low on signal day | 8% |
| Emergency stop | -5% |
| Time stop | 3 trading days without floating profit |
| Trend exit drawdown from highest close | 8% |
| Hard maximum holding period | 30 trading days |
| Main-line confirmation | second-level industry turnover top 5 for 3 consecutive trading days |
| Observation main-line confirmation | top 5 at least 3 times in latest 5 trading days |
| Newly listed stock exclusion | fewer than 120 trading days |

## Consequences

MVP-1 can validate the structural edge of the daily C-point setup without waiting for minute-level execution modeling.

The system must clearly label MVP-1 results as daily-proxy research results, not full-system live-trading results.

Future optimization should compare out-of-sample performance before accepting any parameter change.
