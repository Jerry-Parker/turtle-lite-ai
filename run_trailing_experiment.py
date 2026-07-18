"""Compare the optional 2R/2.5 ATR trailing stop with the locked baseline."""

import argparse
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "turtle-lite-matplotlib"))
import matplotlib.pyplot as plt

from run_final_stress_suite import (
    START_DATE, SYMBOLS, choose_start_dates, conditional_metrics,
    equity_returns, high_volatility_mask, percentile_summary,
)
from run_pbo_analysis import build_return_matrix, cscv_pbo
from run_portfolio_test import run_portfolio


def metrics(report):
    return {
        "annualized_return_percent": report["annualized_return_percent"],
        "max_drawdown_percent": report["max_drawdown_percent"],
        "sharpe_ratio": report["sharpe_ratio"],
        "closed_trades": report["closed_trades"],
        "time_with_any_position_percent": report["time_with_any_position_percent"],
        "trailing_stop_exits": report["exits_by_reason"]["trailing_stop"],
    }


def start_date_stress(use_trailing, dates, data_directory):
    results = []
    for date in dates:
        report = run_portfolio(
            SYMBOLS, data_directory=data_directory,
            start_date=date.date().isoformat(), use_trailing=use_trailing,
        )
        results.append(report)
    return {
        "positive_annualized_return_percent": round(
            np.mean([item["annualized_return_percent"] > 0 for item in results]) * 100, 2
        ),
        "annualized_return_distribution": percentile_summary(
            [item["annualized_return_percent"] for item in results]
        ),
        "max_drawdown_distribution": percentile_summary(
            [item["max_drawdown_percent"] for item in results]
        ),
    }


def run_experiment(data_directory="data", start_samples=50):
    baseline = run_portfolio(SYMBOLS, data_directory=data_directory, start_date=START_DATE)
    trailing = run_portfolio(
        SYMBOLS, data_directory=data_directory, start_date=START_DATE, use_trailing=True
    )
    baseline_2022 = run_portfolio(
        SYMBOLS, data_directory=data_directory, start_date="2022-01-01", end_date="2022-12-31"
    )
    trailing_2022 = run_portfolio(
        SYMBOLS, data_directory=data_directory, start_date="2022-01-01", end_date="2022-12-31",
        use_trailing=True,
    )
    mask = high_volatility_mask(Path(data_directory) / "SPY.csv", equity_returns(baseline).index)
    sampled_dates = choose_start_dates(list(equity_returns(baseline).index), start_samples)

    pbo = {}
    configurations = [("locked_baseline", {}), ("trailing_2r_2_5atr", {"use_trailing": True})]
    for symbol in SYMBOLS:
        matrix = build_return_matrix(symbol, data_directory, configurations)
        periods = 365 if "-USD" in symbol else 252
        result = cscv_pbo(matrix, blocks=8, periods_per_year=periods)
        pbo[symbol] = {"pbo": result["pbo"], "oos_loss_probability": result["probability_oos_loss"]}

    return {
        "method": {
            "baseline_unchanged": True,
            "trailing_rule": "activate at +2R; trail 2.5 ATR below highest high; ratchet upward only",
            "partial_exits": False,
            "risk_per_trade_percent": 0.5,
            "start_date_samples": start_samples,
        },
        "full_period": {"baseline": metrics(baseline), "trailing": metrics(trailing)},
        "bear_2022": {"baseline": metrics(baseline_2022), "trailing": metrics(trailing_2022)},
        "high_volatility_only": {
            "baseline": conditional_metrics(equity_returns(baseline), mask),
            "trailing": conditional_metrics(equity_returns(trailing), mask),
        },
        "random_start_dates": {
            "baseline": start_date_stress(False, sampled_dates, data_directory),
            "trailing": start_date_stress(True, sampled_dates, data_directory),
        },
        "two_configuration_pbo": pbo,
        "_curves": {"baseline": baseline["equity_curve"], "trailing": trailing["equity_curve"]},
    }


def save_results(report, output_directory):
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    serializable = {key: value for key, value in report.items() if not key.startswith("_")}
    (output / "trailing_experiment.json").write_text(json.dumps(serializable, indent=2) + "\n")
    rows = []
    for period in ("full_period", "bear_2022", "high_volatility_only"):
        for variant, values in serializable[period].items():
            rows.append({"period": period, "variant": variant, **values})
    pd.DataFrame(rows).to_csv(output / "comparison.csv", index=False)

    figure, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for name, curve in report["_curves"].items():
        dates = pd.to_datetime([item["date"] for item in curve])
        values = np.asarray([item["value"] for item in curve])
        axes[0].plot(dates, values / values[0] * 100, label=name)
    axes[0].set_title("Trailing stop versus locked baseline")
    axes[0].set_ylabel("Growth of $100")
    axes[0].grid(alpha=0.2)
    axes[0].legend()
    names = list(serializable["two_configuration_pbo"])
    axes[1].bar(names, [serializable["two_configuration_pbo"][name]["pbo"] for name in names])
    axes[1].axhline(0.5, color="darkred", linestyle="--", linewidth=1)
    axes[1].set_ylim(0, 1)
    axes[1].set_title("Two-choice PBO diagnostic")
    axes[1].set_ylabel("PBO")
    figure.tight_layout()
    figure.savefig(output / "comparison.png", dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-directory", default="data")
    parser.add_argument("--start-samples", type=int, default=50)
    parser.add_argument("--output-directory", default="reports/trailing_stop")
    args = parser.parse_args()
    report = run_experiment(args.data_directory, args.start_samples)
    save_results(report, args.output_directory)
    print(json.dumps({key: value for key, value in report.items() if key not in {"_curves"}}, indent=2))


if __name__ == "__main__":
    main()
