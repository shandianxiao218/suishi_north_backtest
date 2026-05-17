# ADR-0001: Record architecture decisions in docs/adr

## Status

Accepted

## Context

The repo will evolve from an empty backtest prototype into a research system with data adapters, strategy rules, simulation logic, optimization workflows, and reporting.

Backtesting systems are vulnerable to hidden assumptions, especially around look-ahead bias, data boundaries, execution modeling, and parameter optimization.

## Decision

Architecture decisions will be recorded as ADRs under `docs/adr/`.

Each ADR should include:

- Status
- Context
- Decision
- Consequences

## Consequences

Future agents and contributors should read relevant ADRs before changing core behavior.
