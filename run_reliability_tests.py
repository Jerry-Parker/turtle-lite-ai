"""Run robustness tests without automatically choosing a winning configuration."""

import argparse
import json
import random
import statistics
from pathlib import Path

from run_backtest import COMMISSION_RATE, SLIPPAGE_RATE, STARTING_CASH
from run_validation import discover_symbols, observation_count, run_period


WALK_FORWARD_PERIODS = (
    ("2005_2009", "2005-01-01", "2009-12-31"),
    ("2010_2014", "2010-01-01", "2014-12-31"),
    ("2015_2019", "2015-01-01", "2019-12-31"),
    ("2020_onward", "2020-01-01", None),
)

# Change one assumption at a time. The baseline is declared in advance and is
# never replaced automatically by whichever alternative scores highest.
PARAMETER_CONFIGS = (
    ("baseline", {}),
    ("breakout_15", {"breakout_period": 15}),
    ("breakout_30", {"breakout_period": 30}),
    ("exit_5", {"exit_period": 5}),
    ("exit_20", {"exit_period": 20}),
    ("stop_1_5_atr", {"initial_stop_atr": 1.5}),
    ("stop_2_5_atr", {"initial_stop_atr": 2.5}),
    ("stop_3_atr", {"initial_stop_atr": 3.0}),
    ("risk_0_25_pct", {"risk_pct": 0.0025}),
    ("risk_0_75_pct", {"risk_pct": 0.0075}),
)

COST_SCENARIOS = (
    ("normal", 1),
    ("double", 2),
    ("four_times", 4),
)


def longest_losing_streak(trade_pnls):
    longest = current = 0
    for pnl in trade_pnls:
        if pnl < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def sequence_drawdown_percent(trade_pnls, starting_cash=STARTING_CASH):
    equity = peak = starting_cash
    maximum = 0.0
    for pnl in trade_pnls:
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            maximum = max(maximum, ((peak - equity) / peak) * 100)
    return maximum


def percentile(values, probability):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * probability))))
    return ordered[index]


def monte_carlo_trade_order(trade_pnls, simulations=2000, seed=20260718):
    """Estimate sequence risk by shuffling the observed trade outcomes."""
    if not trade_pnls:
        return {"simulations": simulations, "p95_drawdown_percent": 0.0,
                "p99_drawdown_percent": 0.0, "worst_drawdown_percent": 0.0}
    generator = random.Random(seed)
    drawdowns = []
    for _ in range(simulations):
        shuffled = list(trade_pnls)
        generator.shuffle(shuffled)
        drawdowns.append(sequence_drawdown_percent(shuffled))
    return {
        "simulations": simulations,
        "p95_drawdown_percent": round(percentile(drawdowns, 0.95), 2),
        "p99_drawdown_percent": round(percentile(drawdowns, 0.99), 2),
        "worst_drawdown_percent": round(max(drawdowns), 2),
    }


def summarize_parameter_results(results):
    summaries = []
    for config_name, _ in PARAMETER_CONFIGS:
        subset = [item for item in results if item["configuration"] == config_name]
        summaries.append(
            {
                "configuration": config_name,
                "tests": len(subset),
                "positive_test_percent": round(
                    sum(item["return_percent"] > 0 for item in subset)
                    / len(subset) * 100,
                    2,
                ) if subset else 0,
                "median_annualized_return_percent": round(
                    statistics.median(item["annualized_return_percent"] for item in subset), 2
                ) if subset else 0,
                "median_return_to_drawdown": round(
                    statistics.median(item["return_to_drawdown"] for item in subset), 2
                ) if subset else 0,
                "worst_drawdown_percent": round(
                    max((item["max_drawdown_percent"] for item in subset), default=0), 2
                ),
            }
        )
    return summaries


def run_reliability_suite(data_directory="data", symbols=None, simulations=2000):
    data_directory = Path(data_directory)
    symbols = symbols or discover_symbols(data_directory)

    parameter_results = []
    for config_name, parameters in PARAMETER_CONFIGS:
        for symbol in symbols:
            csv_path = data_directory / f"{symbol}.csv"
            for period_name, start_date, end_date in WALK_FORWARD_PERIODS:
                if observation_count(csv_path, start_date, end_date) < 201:
                    continue
                result = run_period(
                    symbol,
                    csv_path,
                    period_name,
                    start_date,
                    end_date,
                    strategy_params=parameters,
                )
                result["configuration"] = config_name
                parameter_results.append(result)

    cost_results = []
    sequence_results = []
    for symbol in symbols:
        csv_path = data_directory / f"{symbol}.csv"
        for scenario_name, multiplier in COST_SCENARIOS:
            result = run_period(
                symbol,
                csv_path,
                "full_history",
                commission_rate=COMMISSION_RATE * multiplier,
                slippage_rate=SLIPPAGE_RATE * multiplier,
            )
            result["cost_scenario"] = scenario_name
            cost_results.append(result)

        baseline = run_period(
            symbol,
            csv_path,
            "full_history",
            include_trade_pnls=True,
        )
        pnls = baseline.pop("trade_net_pnls")
        sequence_results.append(
            {
                "symbol": symbol,
                "trades": len(pnls),
                "historical_longest_losing_streak": longest_losing_streak(pnls),
                **monte_carlo_trade_order(pnls, simulations=simulations),
            }
        )

    return {
        "method": {
            "declared_baseline": "baseline",
            "parameter_trials": len(PARAMETER_CONFIGS),
            "selection_policy": (
                "Report every declared trial; do not automatically replace the baseline."
            ),
            "warning": (
                "Historical and simulated results do not guarantee future performance."
            ),
        },
        "parameter_stability_summary": summarize_parameter_results(parameter_results),
        "parameter_walk_forward_results": parameter_results,
        "execution_cost_results": cost_results,
        "trade_sequence_results": sequence_results,
    }


def print_findings(report):
    print("\nPARAMETER STABILITY (fixed five-year test windows)")
    print("Configuration    Positive tests  Median CAGR  Median return/DD  Worst DD")
    for item in report["parameter_stability_summary"]:
        print(
            f"{item['configuration']:<16} {item['positive_test_percent']:>12.2f}% "
            f"{item['median_annualized_return_percent']:>11.2f}% "
            f"{item['median_return_to_drawdown']:>16.2f} "
            f"{item['worst_drawdown_percent']:>8.2f}%"
        )

    print("\nEXECUTION-COST STRESS (full history return)")
    for item in report["execution_cost_results"]:
        print(
            f"{item['symbol']:<8} {item['cost_scenario']:<11} "
            f"{item['return_percent']:>8.2f}%"
        )

    print("\nTRADE-SEQUENCE STRESS")
    for item in report["trade_sequence_results"]:
        print(
            f"{item['symbol']:<8} streak {item['historical_longest_losing_streak']:>2} | "
            f"95% shuffled DD {item['p95_drawdown_percent']:>5.2f}% | "
            f"worst {item['worst_drawdown_percent']:>5.2f}%"
        )


def main():
    parser = argparse.ArgumentParser(description="Run Turtle Lite reliability tests.")
    parser.add_argument("--data-directory", default="data")
    parser.add_argument("--output", default="reports/reliability_tests.json")
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--simulations", type=int, default=2000)
    args = parser.parse_args()

    report = run_reliability_suite(
        args.data_directory,
        symbols=args.symbols,
        simulations=args.simulations,
    )
    print_findings(report)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nDetailed report saved to {output_path}")


if __name__ == "__main__":
    main()
