# PRD: NASDAQ Auto Trader

**Version**: 0.1
**Author**: Codex
**Date**: 2026-06-23
**Status**: Done
**Size**: L

---

## 1. Problem Statement

### 1.1 Background

The requested system is a NASDAQ auto-trading tool that actively uses
traditional quantitative trading techniques and is backed by deep reference
research. The repository started with a basic technical-indicator strategy,
Alpaca connectivity, CSV backtesting, and tests, but lacked durable
dev-pipeline artifacts, readable docs, richer classical quant signals, and
backtest risk metrics.

### 1.2 Problem Definition

Build an interpretable auto-trading system that can generate buy/sell/hold
decisions for NASDAQ symbols, cap risk before order submission, run historical
CSV backtests, and connect to Alpaca in dry-run, paper, or explicitly gated live
mode.

### 1.3 Impact of Not Solving

Without multi-signal strategy logic, explicit risk sizing, realistic backtest
metrics, and mode gates, users could overtrust a fragile single-indicator system
or accidentally send unsafe live orders.

## 2. Goals & Non-Goals

### 2.1 Goals

- [x] G1: Implement classical trend, momentum, breakout, mean-reversion,
  volatility, and volume signals.
- [x] G2: Add account and per-trade risk controls before broker order creation.
- [x] G3: Provide CSV backtesting with risk-adjusted metrics and reduced
  same-bar look-ahead bias.
- [x] G4: Integrate with Alpaca while defaulting to `dry_run` and requiring an
  explicit live-trading gate.
- [x] G5: Document research references, usage, tests, and operational limits.

### 2.2 Non-Goals

- NG1: Guarantee profitability or investment suitability.
- NG2: Optimize parameters with historical data mining.
- NG3: Implement options, short selling, leverage, margin, or intraday HFT.
- NG4: Build a web UI.
- NG5: Replace broker-side risk checks.

## 3. User Stories & Acceptance Criteria

### US-1: Configure And Inspect

**As a** user, **I want** a JSON-configured trader, **so that** I can control
symbols, strategy periods, risk caps, and Alpaca feed.

**Acceptance Criteria:**
- [x] AC-1.1: Given `config.example.json`, when `show-config` runs, then all
  strategy and risk fields are visible and credentials are masked.
- [x] AC-1.2: Given `mode=live` without `allow_live_trading=true`, when config
  is validated, then execution is blocked.

### US-2: Generate Quant Signals

**As a** trading-system operator, **I want** classical quant signals combined
into one decision, **so that** no single indicator controls the whole strategy.

**Acceptance Criteria:**
- [x] AC-2.1: Strong uptrends can produce buy decisions with regime, trend,
  momentum, breakout, and volume reasons.
- [x] AC-2.2: Existing positions can exit via fixed stop, ATR stop, trend
  breakdown, overextension, or breakout failure.
- [x] AC-2.3: Decisions include `risk_per_share` for risk sizing when buying.

### US-3: Risk-Managed Orders

**As a** user, **I want** all orders capped by portfolio and per-trade risk,
**so that** strategy confidence cannot bypass risk controls.

**Acceptance Criteria:**
- [x] AC-3.1: Buy notional is capped by max position percentage.
- [x] AC-3.2: Buy notional is capped by cash buffer and buying power.
- [x] AC-3.3: When risk distance is provided, fixed-fraction risk caps order
  notional.
- [x] AC-3.4: Sell orders are emitted only for an existing positive position.

### US-4: Backtest

**As a** researcher, **I want** to test CSV bars before paper/live execution,
**so that** I can inspect performance and failure modes.

**Acceptance Criteria:**
- [x] AC-4.1: CSV bars load by symbol and timestamp.
- [x] AC-4.2: Backtest signals are generated from known close data and executed
  at the next bar open.
- [x] AC-4.3: Output includes total return, max drawdown, Sharpe ratio, trade
  count, win rate, and trades.

### US-5: Broker Integration

**As a** paper trader, **I want** Alpaca integration, **so that** I can test the
system against broker APIs after local validation.

**Acceptance Criteria:**
- [x] AC-5.1: Dry-run broker records orders without external side effects.
- [x] AC-5.2: Alpaca order payloads use one of `notional` or `qty`.
- [x] AC-5.3: Stock-bar fetch follows Alpaca pagination.

## 4. Technical Design

### 4.1 Architecture Overview

`cli.py` loads config and dispatches commands. `engine.py` connects market data,
strategy, risk manager, and broker. `strategy.py` converts trailing bars into
decisions. `risk.py` converts decisions into safe order requests. `backtest.py`
simulates historical execution. `broker.py` handles Alpaca and dry-run broker
behavior.

### 4.2 Data Model Changes

- `TradeDecision.risk_per_share` was added for ATR/fixed-stop risk sizing.
- `BacktestResult` now includes equity curve, drawdown, Sharpe ratio, trade
  count, and win rate.

### 4.3 API Design

| Method | Endpoint | Description | Auth |
| --- | --- | --- | --- |
| POST | Alpaca `/v2/orders` | Submit approved market/day orders | Alpaca keys |
| GET | Alpaca `/v2/stocks/bars` | Fetch historical OHLCV bars | Alpaca keys |

### 4.4 Key Technical Decisions

| Decision | Options Considered | Chosen | Rationale |
| --- | --- | --- | --- |
| Indicators | Third-party TA package vs local formulas | Local formulas | Auditable and dependency-free. |
| Strategy | Single signal vs score blend | Score blend | Traditional indicators are noisy alone. |
| Backtest execution | Same-close vs next-open | Next-open | Reduces look-ahead bias. |
| Live mode | Config default live vs gated live | Gated live | Prevents accidental real orders. |

## 5. Edge Cases & Error Handling

| # | Scenario | Expected Behavior | Severity |
| --- | --- | --- | --- |
| E1 | Not enough bars | Hold with `not_enough_data` | P1 |
| E2 | Missing CSV columns | Raise `ValueError` listing missing columns | P1 |
| E3 | Invalid mode | Raise `ValueError` | P0 |
| E4 | Paper/live without credentials | Raise `ValueError` | P0 |
| E5 | Alpaca API error | Raise `RuntimeError` with response body | P1 |
| E6 | Order below minimum notional | Suppress order | P1 |

## 6. Security & Permissions

### 6.1 Authentication

Alpaca keys are read from environment variables or config. CLI config output
masks populated key values.

### 6.2 Authorization

| Role | Create | Read | Update | Delete |
| --- | --- | --- | --- | --- |
| Local user | config/orders by CLI mode | config/backtest/output | config | N/A |
| Broker | validates order permissions | account/positions/bars | broker-side orders | broker-side cancellation not implemented |

### 6.3 Data Protection

No PII is stored by this repo. Credentials should be supplied through
environment variables where possible.

## 7. Performance & Monitoring

| Metric | Target | Measurement |
| --- | --- | --- |
| Unit tests | < 5 seconds | `python -m unittest discover -s tests -v` |
| Backtest memory | Linear in bars | CSV backtest run |
| Broker timeout | Configurable, default 30 sec | Alpaca client timeout |

### 7.1 Monitoring & Alerting

N/A for this local CLI version. Production deployment should add persistent
logs, order IDs, rejected-order alerts, drawdown limits, and a kill switch.

## 8. Testing Strategy

### 8.1 Unit Tests

Indicator math, strategy decisions, risk caps, order serialization, mode
validation, injected engine execution, and backtest metrics.

### 8.2 Integration Tests

Local CLI config display. Live Alpaca calls are not run in automated tests
because they require credentials and external side effects.

### 8.3 Edge Case Tests

Covered: live-mode gate, risk notional cap, stop-loss exit, next-open backtest
trade execution, and config display.

## 9. Rollout Plan

### 9.1 Migration Strategy

No database migration. Existing JSON configs can continue to load because
unknown fields are ignored and new fields have dataclass defaults.

### 9.2 Feature Flag

`mode` plus `allow_live_trading` acts as the live-order gate.

### 9.3 Rollback Plan

Revert to the previous commit or set `mode=dry_run` and
`allow_live_trading=false`.

## 10. Dependencies & Risks

### 10.1 Dependencies

| Dependency | Owner | Status | Risk if Delayed |
| --- | --- | --- | --- |
| Python stdlib | Python | Available | App cannot run |
| Alpaca account | User | Optional | Paper/live unavailable |
| Historical CSV | User | Optional | Local backtest unavailable |

### 10.2 Risks

| Risk | Probability | Impact | Mitigation |
| --- | --- | --- | --- |
| Overfit parameters | Medium | High | No optimizer included; require out-of-sample validation. |
| Transaction costs ignored | High | High | Document limit and inspect paper results. |
| Slippage/halts | Medium | High | Keep max position/risk caps conservative. |
| Accidental live orders | Low | High | Dry-run default and explicit live gate. |

## 11. Success Metrics

| Metric | Baseline | Target | Measurement Method |
| --- | --- | --- | --- |
| Unit tests | 8 tests | 11+ passing tests | unittest |
| Signal breadth | SMA/EMA/RSI/MACD/Bollinger | Add ATR/Donchian/stochastic/momentum/volume/regime | code/tests |
| Backtest metrics | return only | return/drawdown/Sharpe/trades/win rate | CLI output |

## 12. Open Questions

- [ ] OQ-1: Which NASDAQ universe and rebalance cadence should be used for
  serious out-of-sample evaluation?
- [ ] OQ-2: What slippage and commission model should be applied for the target
  account size and trading frequency?
