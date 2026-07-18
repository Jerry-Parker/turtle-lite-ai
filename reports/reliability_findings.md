# Turtle Lite reliability findings

Historical and simulated results do not guarantee future performance. These
tests use daily data and do not represent live trading.

## Main conclusion

The current strategy is conservative, but not yet efficient enough for live
or master-trader use. It limits drawdowns, while annualized returns remain far
below an idealized buy-and-hold benchmark on every tested asset.

## What the tests found

- The strategy was invested only about 12% to 39% of available bars.
- Full-history annualized returns ranged from 0.04% for SPY to 3.28% for SOL.
- The baseline produced a positive return in 84% of the available fixed
  five-year asset windows, but its median annualized return was only 0.57%.
- Extending the channel exit from 10 to 20 days improved annualized return in
  20 of 25 paired tests, but increased the worst tested drawdown from 8.29% to
  13.88%.
- Raising risk from 0.5% to 0.75% improved annualized return in 21 of 25 paired
  tests, but mostly scaled both return and risk; it did not improve median
  return-to-drawdown.
- Wider 2.5 and 3 ATR stops underperformed the baseline in 20 of 25 paired
  tests. They should not be adopted.
- SPY was highly sensitive to costs: its full-history result moved from +1.05%
  at normal costs to -4.13% at double costs and -13.34% at four-times costs.
- AAPL, NVDA, BTC, ETH, and SOL were less cost-sensitive, largely because they
  traded less often or captured a small number of large trends.
- Historical longest losing streaks ranged from two trades in BTC and ETH to
  eight trades in GOOGL.
- In 2,000 shuffled trade-order simulations, SPY had a 95th-percentile
  sequence drawdown of 7.65% and a worst observed sequence drawdown of 10.18%.

## Crypto limitations

The crypto tests use public daily spot data for BTC, ETH, and SOL. They do not
include perpetual-futures funding, leverage, liquidation, intraday spread,
exchange outages, or Bybit-specific order behavior. SOL also has a much
shorter history than the equity datasets. These results are preliminary and
do not justify a live or leveraged deployment.

The eight market-data files passed structural quality checks: dates are unique
and increasing, required values are complete, prices are positive, volumes are
non-negative, and every high/low is consistent with its open and close. BTC
history begins in September 2014, ETH in November 2017, and SOL in April 2020;
the shorter crypto histories reduce confidence compared with the equity tests.

## Recommended next research step

Do not change a strategy parameter solely because it ranked first in this
batch. The next design study should examine portfolio construction and capital
utilization: run the unchanged rules across several assets at the same time,
with portfolio-wide risk and correlation limits. This is closer to how the
original Turtle approach diversified trends and directly addresses the large
amount of idle cash shown by these tests.
