"""Compare the locked portfolio baseline with a predeclared macro risk overlay."""

import argparse
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "turtle-lite-matplotlib"))
import matplotlib.pyplot as plt

from run_pbo_analysis import cscv_pbo
from run_portfolio_test import run_portfolio


SYMBOLS = ["SPY", "QQQ", "AAPL", "GOOGL", "NVDA", "SOL-USD"]
CONFIGURATIONS = [
    ("locked_baseline", {}),
    ("primary_sma200_vix25", {"use_macro_scaling": True, "regime_sma_period": 200, "vix_threshold": 25}),
    ("sensitivity_sma200_vix20", {"use_macro_scaling": True, "regime_sma_period": 200, "vix_threshold": 20}),
    ("sensitivity_sma200_vix30", {"use_macro_scaling": True, "regime_sma_period": 200, "vix_threshold": 30}),
    ("sensitivity_sma100_vix25", {"use_macro_scaling": True, "regime_sma_period": 100, "vix_threshold": 25}),
]


def return_series(report, name):
    values = pd.Series(
        [item["value"] for item in report["equity_curve"]],
        index=pd.to_datetime([item["date"] for item in report["equity_curve"]]),
        name=name,
        dtype=float,
    )
    return values.pct_change().fillna(0.0)


def compact(report):
    keys = [
        "annualized_return_percent", "max_drawdown_percent", "sharpe_ratio",
        "time_with_any_position_percent", "average_capital_invested_percent",
        "average_cash_available_percent",
        "closed_trades", "risk_cap_rejections", "unfilled_entries",
        "average_risk_rate_percent", "regime_days", "entries_by_regime",
    ]
    return {key: report[key] for key in keys}


def run_experiment(start_date="2020-04-10", end_date=None, data_directory="data"):
    portfolio_reports = {}
    sol_reports = {}
    for name, parameters in CONFIGURATIONS:
        portfolio_reports[name] = run_portfolio(
            SYMBOLS, data_directory=data_directory, start_date=start_date,
            end_date=end_date, **parameters,
        )
        sol_reports[name] = run_portfolio(
            ["SOL-USD"], data_directory=data_directory, start_date=start_date,
            end_date=end_date, **parameters,
        )

    portfolio_returns = pd.concat(
        [return_series(report, name) for name, report in portfolio_reports.items()], axis=1, join="inner"
    )
    sol_returns = pd.concat(
        [return_series(report, name) for name, report in sol_reports.items()], axis=1, join="inner"
    )
    baseline = portfolio_reports["locked_baseline"]
    primary = portfolio_reports["primary_sma200_vix25"]
    return {
        "experiment_policy": {
            "primary_rule_predeclared": "SPY > SMA200 and VIX < 25: 0.5% risk; otherwise 0.25% risk",
            "selection_policy": "Sensitivity variants are diagnostics only; no winner is selected.",
            "assets": SYMBOLS,
            "start_date": start_date,
            "end_date": end_date,
        },
        "portfolio_results": {name: compact(report) for name, report in portfolio_reports.items()},
        "sol_results": {name: compact(report) for name, report in sol_reports.items()},
        "primary_minus_baseline": {
            "annualized_return_percentage_points": round(primary["annualized_return_percent"] - baseline["annualized_return_percent"], 2),
            "max_drawdown_percentage_points": round(primary["max_drawdown_percent"] - baseline["max_drawdown_percent"], 2),
            "time_in_market_percentage_points": round(primary["time_with_any_position_percent"] - baseline["time_with_any_position_percent"], 2),
            "closed_trades": primary["closed_trades"] - baseline["closed_trades"],
        },
        "portfolio_overlay_pbo": cscv_pbo(portfolio_returns, blocks=8, periods_per_year=365),
        "sol_overlay_pbo": cscv_pbo(sol_returns, blocks=8, periods_per_year=365),
        "_portfolio_reports": portfolio_reports,
    }


def save_results(result, output_directory):
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    serializable = {key: value for key, value in result.items() if not key.startswith("_")}
    for pbo_key in ("portfolio_overlay_pbo", "sol_overlay_pbo"):
        serializable[pbo_key] = {
            key: value for key, value in serializable[pbo_key].items()
            if key not in {"logits", "selected_is_scores", "selected_oos_scores", "all_oos_scores", "selected_configuration_indexes", "stochastic_dominance"}
        }
    (output / "experiment.json").write_text(json.dumps(serializable, indent=2) + "\n")
    rows = [{"configuration": name, **metrics} for name, metrics in serializable["portfolio_results"].items()]
    pd.DataFrame(rows).to_csv(output / "comparison.csv", index=False)

    reports = result["_portfolio_reports"]
    figure, axes = plt.subplots(2, 1, figsize=(10, 8))
    for name, report in reports.items():
        dates = pd.to_datetime([item["date"] for item in report["equity_curve"]])
        values = np.asarray([item["value"] for item in report["equity_curve"]])
        axes[0].plot(dates, values / values[0] * 100, label=name.replace("_", " "))
    axes[0].set_title("Macro risk overlay: growth of $100")
    axes[0].set_ylabel("Portfolio value")
    axes[0].grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    names = list(serializable["portfolio_results"])
    cagr = [serializable["portfolio_results"][n]["annualized_return_percent"] for n in names]
    drawdown = [serializable["portfolio_results"][n]["max_drawdown_percent"] for n in names]
    x = np.arange(len(names))
    axes[1].bar(x - 0.18, cagr, 0.36, label="Annualized return")
    axes[1].bar(x + 0.18, drawdown, 0.36, label="Maximum drawdown")
    axes[1].set_xticks(x, [n.replace("sensitivity_", "").replace("_", "\n") for n in names], fontsize=8)
    axes[1].set_ylabel("Percent")
    axes[1].grid(axis="y", alpha=0.2)
    axes[1].legend()
    figure.tight_layout()
    figure.savefig(output / "comparison.png", dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2020-04-10")
    parser.add_argument("--end-date")
    parser.add_argument("--output-directory", default="reports/macro_risk")
    args = parser.parse_args()
    result = run_experiment(args.start_date, args.end_date)
    save_results(result, args.output_directory)
    print(json.dumps({
        "primary_minus_baseline": result["primary_minus_baseline"],
        "portfolio_overlay_pbo": result["portfolio_overlay_pbo"]["pbo"],
        "sol_overlay_pbo": result["sol_overlay_pbo"]["pbo"],
    }, indent=2))


if __name__ == "__main__":
    main()
