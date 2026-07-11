# Quant Reference Review: NASDAQ Auto Trader

**Date**: 2026-06-23
**Scope**: Classical, interpretable NASDAQ equity/ETF auto-trading system with
Alpaca integration, backtesting, and explicit safety controls.

## Source Findings

1. **Alpaca order API constraints**
   - Alpaca's create-order endpoint accepts `symbol`, `side`, `type`,
     `time_in_force`, and either `notional` or `qty`; `notional` cannot be used
     with `qty` and is limited to market/day orders.
   - Market orders are likely to fill but can slip or fill at unexpected prices.
   - Project impact: keep default orders as market/day, serialize only one of
     `notional` or `qty`, and document slippage limits.
   - Source: https://docs.alpaca.markets/us/reference/postorder
   - Source: https://docs.alpaca.markets/us/docs/orders-at-alpaca

2. **Alpaca stock-bar data constraints**
   - Stock bars are paginated, `limit` is total data points rather than per
     symbol, and clients must follow `next_page_token`.
   - `feed` can be `iex`, `sip`, `boats`, or `otc`; IEX is a single exchange,
     while SIP is consolidated tape and may require a subscription for recent
     data.
   - Project impact: retain pagination, expose feed in config, default to IEX,
     and warn operators about SIP subscription behavior.
   - Source: https://docs.alpaca.markets/us/reference/stockbars
   - Source: https://docs.alpaca.markets/us/docs/market-data-faq

3. **Classical indicator set**
   - TA-Lib documentation identifies MACD as Gerald Appel's
     moving-average-convergence/divergence indicator, RSI and ATR as Welles
     Wilder indicators, and Bollinger Bands as John Bollinger's volatility-band
     method.
   - Project impact: keep indicator implementations transparent and dependency
     free; include MACD, RSI, Bollinger Bands, and ATR as first-class signals.
   - Sources:
     - https://ta-lib.github.io/ta-doc/indicator/MACD.htm
     - https://ta-lib.github.io/ta-doc/indicator/RSI.htm
     - https://ta-lib.github.io/ta-doc/indicator/BBANDS.htm
     - https://ta-lib.github.io/ta-doc/indicator/ATR.htm

4. **Trend following and breakout rules**
   - Research on simple technical trading rules discusses moving-average and
     trading-range-breakout rules, including short/long moving average
     penetration and prior range support/resistance breaks. It also cautions
     that transaction costs and data snooping can eliminate apparent edge.
   - Project impact: include SMA/EMA trend and Donchian-style breakout signals,
     but document that costs and out-of-sample validation are mandatory.
   - Source: https://arxiv.org/abs/1504.04254

5. **Momentum evidence**
   - Time-series momentum research reports persistence in 1-to-12-month returns
     across liquid instruments, with longer-horizon partial reversal.
   - Project impact: add a configurable rate-of-change momentum signal rather
     than relying only on moving-average crossover.
   - Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463

6. **Combining MACD with other signals**
   - A 2022 U.S. market MACD study found standalone MACD win rate below 50% in
     the tested setup, while combining MACD with momentum indicators such as RSI
     or MFI improved results.
   - A 2026 U.S. equity-index preprint reports that adding volume, volatility,
     and intraday price structure to MACD can improve risk-adjusted performance
     and downside-risk control in the studied period.
   - Project impact: treat MACD as one vote in a multi-signal score, add volume
     confirmation, and avoid single-indicator trading.
   - Sources:
     - https://arxiv.org/abs/2206.12282
     - https://arxiv.org/abs/2604.26063

7. **Regime and volatility controls**
   - Recent hybrid strategy research combines EMA/MACD trend capture,
     RSI/Bollinger mean reversion, and market-regime filtering based on
     volatility/return environments.
   - Project impact: use long-SMA regime gating and ATR-based stops/sizing as
     simple interpretable risk controls.
   - Source: https://arxiv.org/abs/2601.19504

8. **Risk sizing and performance metrics**
   - Position sizing references emphasize portfolio percentage, volatility, stop
     distance, and Kelly/fractional Kelly concepts; practical systems often
     cap risk per trade.
   - Sharpe ratio is a standard excess-return-per-unit-risk metric, but it has
     statistical limitations and should be interpreted with drawdown and trade
     data.
   - Project impact: add fixed-fraction risk sizing, max drawdown, Sharpe ratio,
     win rate, and trade count to the backtest output.
   - Sources:
     - https://www.investopedia.com/articles/trading/09/determine-position-size.asp
     - https://www.investopedia.com/terms/s/sharperatio.asp

## Implementation Decisions

| Decision | Rationale |
| --- | --- |
| No new dependencies | Keeps the project runnable in a restricted environment and makes formulas auditable. |
| Multi-signal score | Reduces reliance on any one lagging or noisy indicator. |
| Long-only default | Matches Alpaca fractional/notional equity order simplicity and avoids borrow/short-sale constraints. |
| Close-signal, next-open backtest | Avoids using same close both as signal input and execution price. |
| ATR and fixed stops | Combines absolute account-risk discipline with volatility-aware exits. |
| Dry-run default | Prevents accidental live order placement. |

## Known Limits

- No slippage, commission, tax, latency, partial-fill, halt, borrow, or corporate
  action event model beyond adjusted Alpaca bars.
- No walk-forward optimization or data-snooping correction.
- No portfolio correlation model across symbols.
- No persistent order ledger or kill switch beyond the live-mode config gate.
- Not a production investment system without extended paper-trading validation.
