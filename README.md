# turtle-lite-ai
# Turtle Lite AI

Educational AI paper-trading coach using Backtrader and Alpaca.

## Purpose

This app helps users practise disciplined, rule-based trading in paper mode.

Version 1 uses a simplified Turtle-style trend-following strategy:

- Long only
- No leverage
- No options
- Paper trading first
- 20-day breakout entry
- 10-day low exit
- ATR-based position sizing
- Maximum 0.5% risk per paper trade

## Status

Prototype stage.

## Validate across assets and market periods

Run the complete validation matrix:

```bash
python run_validation.py
```

The runner automatically tests every CSV in `data/` over full history,
2005–2017, and 2018 onward. It prints a short comparison and saves detailed
results to `reports/validation_matrix.json` and
`reports/validation_matrix.csv`.

The validation report includes an idealized buy-and-hold benchmark,
annualized return, maximum drawdown, return-to-drawdown, and time invested.

Run the broader reliability suite:

```bash
python run_reliability_tests.py
```

This tests predeclared nearby parameters over fixed five-year windows,
stresses commission and slippage, and shuffles historical trade outcomes to
estimate losing-sequence risk. It reports every attempted configuration and
does not automatically replace the baseline with the best backtest.

Run the paper-inspired overfitting diagnostics:

```bash
python run_pbo_analysis.py
```

This approximates combinatorially symmetric cross-validation (CSCV) using
synchronized daily portfolio returns. It reports PBO, IS-to-OOS performance
degradation, MinTRL, sensitivity to the number of trials, stochastic
dominance, and bull/bear/high-volatility/low-volatility PBO. Results and plots
are saved under `reports/pbo/`.

Run the locked-baseline shared portfolio test:

```bash
python run_portfolio_test.py
```

This uses the same Turtle parameters for every asset, one shared cash account,
0.5% risk per trade, and a predeclared 2% total open-risk cap. It does not tune
parameters or change the strategy defaults.
