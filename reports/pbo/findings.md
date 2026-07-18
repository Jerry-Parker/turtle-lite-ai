# Turtle Lite overfitting diagnostics

These results are historical and simulated. They do not predict future
performance or justify live trading.

## Method

The analysis approximates the combinatorially symmetric cross-validation
(CSCV) procedure described by Bailey, Borwein, López de Prado, and Zhu. For
each asset, ten predeclared Turtle parameter configurations produce
synchronized daily portfolio-return series. The return matrix is divided into
eight equal blocks. Every combination of four blocks is used in-sample and its
four-block complement is used out-of-sample, producing 70 symmetric splits.

For each split, the configuration with the highest in-sample Sharpe ratio is
ranked among all ten configurations out-of-sample. PBO is the proportion of
splits in which that selected configuration ranks below the OOS median.

## Results

| Asset | PBO | OOS loss | IS/OOS slope | First-order dominance | Second-order dominance | MinTRL passes |
|---|---:|---:|---:|---|---|---|
| SPY | 0.10 | 0.21 | -0.87 | No | Yes | No |
| QQQ | 0.31 | 0.00 | -0.96 | No | Yes | Yes |
| AAPL | 0.29 | 0.00 | -0.88 | No | Yes | Yes |
| GOOGL | 0.23 | 0.04 | -0.98 | No | No | No |
| NVDA | 0.57 | 0.00 | -0.70 | No | Yes | Yes |
| SOL | 0.66 | 0.16 | -1.04 | No | No | Yes* |

*SOL passes the formula's raw daily-observation MinTRL check, but its short
history, serial dependence, extreme returns, and lack of perpetual-market
costs make that pass insufficient evidence for deployment.

## Interpretation

- NVDA and SOL exceed 0.50 PBO, indicating a high risk that parameter selection
  identifies historical noise rather than a durable setting.
- QQQ and AAPL are close to 0.30. That is still a material selection-risk
  warning even though they remain below 0.50.
- Every degradation slope is negative. Higher in-sample Sharpe consistently
  predicts weaker OOS Sharpe in these tests.
- None of the IS-selected distributions has first-order stochastic dominance
  over the full set of OOS choices. GOOGL and SOL also fail the weaker
  second-order dominance test, so optimization adds no demonstrated
  distributional advantage for those assets.
- SPY's baseline daily Sharpe is so close to zero that the MinTRL formula asks
  for about 464,378 daily observations. GOOGL requires 10,934 but has 5,488.
  Their observed Sharpe ratios are not statistically supported at 95%
  confidence under this approximation.
- QQQ, AAPL, and NVDA pass the raw MinTRL calculation, but passing MinTRL does
  not remove their PBO or degradation warnings.

## Number of trials

Increasing trial count did not produce a perfectly monotonic PBO curve in this
finite sample. It increased the warning clearly for QQQ (0.00 at three trials
to 0.31 at ten), NVDA (0.29 to 0.57), and SOL (0.06 to 0.66). SPY, AAPL, and
GOOGL were mixed because the identity of the added configurations matters as
well as their count. This is why trial count and every attempted configuration
must be recorded rather than treating trial count as a mechanical adjustment.

## Regimes

- SOL bull-regime PBO is 0.93, the strongest regime warning.
- GOOGL PBO is about 0.51 in high volatility and 0.50 in low volatility.
- AAPL high-volatility PBO is 0.46.
- SPY high-volatility PBO rises to 0.37 despite its low overall PBO.
- Regime labels are retrospective diagnostics based on the 200-day moving
  average and median 20-day realized volatility. They are not entry signals.

## Decision

Do not optimize Turtle parameters separately for SOL or NVDA from this test.
Keep the existing baseline unchanged. The next design work should test a
single predeclared rule set as a diversified portfolio, with portfolio-wide
risk limits, before any forward paper-trading stage.
