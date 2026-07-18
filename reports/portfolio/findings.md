# Fixed-baseline portfolio test

Historical and simulated results do not guarantee future performance. This is
a research test, not a live trading system.

## Locked framework

The same settings were applied to every asset:

- 20-day breakout entry
- 10-day channel exit
- 14-day ATR
- initial stop at 2 ATR
- 0.5% risk per trade
- close above the 200-day average and 50-day average above the 200-day average
- 0.1% commission and 0.05% slippage
- one shared cash account
- maximum 2% allocated open risk at entry

No asset-specific tuning, macro scaling, or extreme-volatility filter was
applied.

## Results

| Measurement | Five stocks, 2005-2026 | Five stocks + SOL, 2020-2026 |
|---|---:|---:|
| Annualized return | 3.42% | 9.13% |
| Maximum drawdown | 10.61% | 6.87% |
| Annualized return / drawdown | 0.32 | 1.33 |
| Sharpe ratio | 0.63 | 1.30 |
| Average capital invested | 27.35% | 25.56% |
| Time with any position | 65.72% | 71.35% |
| Maximum allocated entry risk | 2.00% | 2.00% |
| Maximum marked risk after price movement | 2.03% | 2.03% |
| Closed trades | 399 | 133 |
| Benchmark annualized return | 30.06% | 62.48% |
| Benchmark maximum drawdown | 65.98% | 93.60% |
| Benchmark annualized return / drawdown | 0.46 | 0.67 |

## What this teaches us

- Portfolio construction improves the recent stock-plus-SOL baseline's risk
  efficiency. Its return-to-drawdown ratio of 1.33 is about twice the
  benchmark's 0.67.
- The long-history five-stock version does not beat its benchmark on return or
  return-to-drawdown. Diversification alone does not repair the weak stock
  baseline.
- The strategy still leaves roughly three quarters of capital unused. This is
  a major reason returns remain conservative.
- The 2% entry risk limit works. Marked risk can drift slightly above 2% after
  equity changes; no new risk is accepted above the cap.
- The SOL-inclusive result is based on only about six years and remains subject
  to the high SOL PBO found previously. It is evidence for further study, not
  evidence for live deployment.

## How this fits the research framework

- **Lock baseline:** complete. The same rules are used everywhere.
- **Basic trend filter:** already present in the strategy and this test.
- **Portfolio-level risk:** now implemented and tested with one shared account.
- **Macro regime risk scaling:** not implemented yet. It should be tested as a
  separate, predeclared risk overlay against this frozen portfolio baseline.
- **Extreme-volatility guard:** not implemented yet. It should follow the macro
  overlay, one change at a time.
- **Forward paper test:** not started. Begin only after selecting and freezing
  the portfolio risk rules.
- **Monitoring:** equity, benchmark, time invested, capital invested, open risk,
  drawdown, and PBO research reports now exist. Scheduled rolling-PBO updates
  still need to be built before forward testing.

## Next small test

Test one simple macro risk overlay without changing entry or exit parameters:
retain normal 0.5% trade risk in supportive conditions and reduce new-trade
risk to 0.25% when the broad-market regime is weak. Compare it only against
this locked portfolio baseline, including PBO and drawdown degradation.
