"""Run final stress diagnostics without changing the locked Turtle baseline."""

import argparse
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "turtle-lite-matplotlib"))
import matplotlib.pyplot as plt

from run_pbo_analysis import analyze_symbol, compact_result
from run_portfolio_test import maximum_drawdown, run_portfolio


SYMBOLS = ["SPY", "QQQ", "AAPL", "GOOGL", "NVDA", "SOL-USD"]
START_DATE = "2020-04-10"
RANDOM_SEED = 20260718


def equity_returns(report):
    values = pd.Series(
        [point["value"] for point in report["equity_curve"]],
        index=pd.to_datetime([point["date"] for point in report["equity_curve"]]),
        dtype=float,
    )
    return values.pct_change().fillna(0.0)


def high_volatility_mask(spy_path, dates):
    spy = pd.read_csv(spy_path, parse_dates=["Date"]).set_index("Date").sort_index()
    realized = spy["Close"].pct_change().rolling(20, min_periods=20).std()
    threshold = realized.rolling(252, min_periods=126).quantile(0.75)
    signal = (realized > threshold).reindex(dates).ffill().fillna(False)
    return signal.astype(bool)


def conditional_metrics(returns, mask, periods_per_year=365):
    selected = returns[mask]
    curve = (1 + selected).cumprod()
    deviation = selected.std(ddof=1)
    sharpe = selected.mean() / deviation * math.sqrt(periods_per_year) if deviation > 0 else 0.0
    annualized = ((curve.iloc[-1] ** (periods_per_year / len(selected))) - 1) * 100 if len(selected) else 0.0
    return {
        "observations": int(len(selected)),
        "percent_of_days": round(len(selected) / len(returns) * 100, 2),
        "annualized_return_percent": round(float(annualized), 2),
        "max_drawdown_percent": round(maximum_drawdown(curve), 2),
        "sharpe_ratio": round(float(sharpe), 3),
    }


def choose_start_dates(all_dates, count=50, seed=RANDOM_SEED):
    latest_start = all_dates[-1] - pd.Timedelta(days=730)
    candidates = [date for date in all_dates if date >= pd.Timestamp(START_DATE) and date <= latest_start]
    if len(candidates) < count:
        raise ValueError("Not enough eligible dates for start-date stress.")
    generator = np.random.default_rng(seed)
    indexes = np.sort(generator.choice(len(candidates), size=count, replace=False))
    return [candidates[index] for index in indexes]


def percentile_summary(values):
    values = np.asarray(values, dtype=float)
    return {
        "minimum": round(float(np.min(values)), 2),
        "p05": round(float(np.percentile(values, 5)), 2),
        "median": round(float(np.median(values)), 2),
        "p95": round(float(np.percentile(values, 95)), 2),
        "maximum": round(float(np.max(values)), 2),
    }


def run_suite(data_directory="data", start_samples=50):
    baseline = run_portfolio(SYMBOLS, data_directory=data_directory, start_date=START_DATE)
    bear_2022 = run_portfolio(
        SYMBOLS, data_directory=data_directory, start_date="2022-01-01", end_date="2022-12-31"
    )

    returns = equity_returns(baseline)
    high_vol = high_volatility_mask(Path(data_directory) / "SPY.csv", returns.index)
    high_volatility = conditional_metrics(returns, high_vol)

    all_dates = list(returns.index)
    sampled_dates = choose_start_dates(all_dates, start_samples)
    start_results = []
    for date in sampled_dates:
        report = run_portfolio(SYMBOLS, data_directory=data_directory, start_date=date.date().isoformat())
        start_results.append({
            "start_date": date.date().isoformat(),
            "annualized_return_percent": report["annualized_return_percent"],
            "max_drawdown_percent": report["max_drawdown_percent"],
            "sharpe_ratio": report["sharpe_ratio"],
            "closed_trades": report["closed_trades"],
        })

    pbo_results = [analyze_symbol(symbol, data_directory) for symbol in SYMBOLS]
    return {
        "method": {
            "baseline": "Locked parameters, unchanged",
            "assets": SYMBOLS,
            "data_last_dates": {
                symbol: pd.read_csv(Path(data_directory) / f"{symbol}.csv")["Date"].iloc[-1]
                for symbol in SYMBOLS
            },
            "high_volatility_definition": (
                "SPY 20-day realized volatility above its trailing 252-session 75th percentile; "
                "minimum 126 sessions; no future observations used"
            ),
            "start_date_method": f"{start_samples} dates sampled without replacement; seed {RANDOM_SEED}; at least two years remain",
            "warning": "Historical and simulated results do not guarantee future performance.",
        },
        "full_baseline": {
            "start_date": baseline["start_date"],
            "end_date": baseline["end_date"],
            "annualized_return_percent": baseline["annualized_return_percent"],
            "max_drawdown_percent": baseline["max_drawdown_percent"],
            "sharpe_ratio": baseline["sharpe_ratio"],
            "closed_trades": baseline["closed_trades"],
        },
        "bear_2022": {
            "annualized_return_percent": bear_2022["annualized_return_percent"],
            "max_drawdown_percent": bear_2022["max_drawdown_percent"],
            "sharpe_ratio": bear_2022["sharpe_ratio"],
            "closed_trades": bear_2022["closed_trades"],
            "benchmark_annualized_return_percent": bear_2022["benchmark_annualized_return_percent"],
            "benchmark_max_drawdown_percent": bear_2022["benchmark_max_drawdown_percent"],
        },
        "high_volatility_only": high_volatility,
        "random_start_dates": {
            "samples": len(start_results),
            "positive_annualized_return_percent": round(
                np.mean([item["annualized_return_percent"] > 0 for item in start_results]) * 100, 2
            ),
            "annualized_return_distribution": percentile_summary(
                [item["annualized_return_percent"] for item in start_results]
            ),
            "max_drawdown_distribution": percentile_summary(
                [item["max_drawdown_percent"] for item in start_results]
            ),
            "results": start_results,
        },
        "latest_pbo": [compact_result(result) for result in pbo_results],
    }


def save_suite(report, output_directory):
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    (output / "stress_suite.json").write_text(json.dumps(report, indent=2) + "\n")
    pd.DataFrame(report["random_start_dates"]["results"]).to_csv(
        output / "random_start_dates.csv", index=False
    )
    pd.DataFrame(report["latest_pbo"]).to_csv(output / "latest_pbo.csv", index=False)

    starts = report["random_start_dates"]["results"]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    axes[0].hist([item["annualized_return_percent"] for item in starts], bins=12)
    axes[0].axvline(0, color="darkred", linestyle="--", linewidth=1)
    axes[0].set_title("Return sensitivity to starting date")
    axes[0].set_xlabel("Annualized return (%)")
    axes[0].set_ylabel("Samples")
    names = [item["symbol"] for item in report["latest_pbo"]]
    pbo = [item["pbo"] for item in report["latest_pbo"]]
    axes[1].bar(names, pbo)
    axes[1].axhline(0.5, color="darkred", linestyle="--", linewidth=1)
    axes[1].set_ylim(0, 1)
    axes[1].set_title("Latest probability of backtest overfitting")
    axes[1].set_ylabel("PBO")
    figure.tight_layout()
    figure.savefig(output / "stress_summary.png", dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-directory", default="data")
    parser.add_argument("--start-samples", type=int, default=50)
    parser.add_argument("--output-directory", default="reports/final_stress")
    args = parser.parse_args()
    report = run_suite(args.data_directory, args.start_samples)
    save_suite(report, args.output_directory)
    print(json.dumps({
        "bear_2022": report["bear_2022"],
        "high_volatility_only": report["high_volatility_only"],
        "random_start_dates": {
            key: value for key, value in report["random_start_dates"].items() if key != "results"
        },
        "latest_pbo": [{"symbol": item["symbol"], "pbo": item["pbo"]} for item in report["latest_pbo"]],
    }, indent=2))


if __name__ == "__main__":
    main()
