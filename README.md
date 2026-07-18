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
