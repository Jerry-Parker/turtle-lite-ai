"""Paper-inspired CSCV/PBO diagnostics for Turtle Lite parameter selection."""

import argparse
import copy
import contextlib
import io
import itertools
import json
import math
import os
import tempfile
from pathlib import Path
from statistics import NormalDist

import backtrader as bt
os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "turtle-lite-matplotlib"),
)
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from run_backtest import STARTING_CASH, configure_broker
from run_reliability_tests import PARAMETER_CONFIGS
from strategies.turtle_lite import TurtleLiteStrategy


STOCK_SYMBOLS = ("SPY", "QQQ", "AAPL", "GOOGL", "NVDA")
DEFAULT_BLOCKS = 8


class DailyReturnAnalyzer(bt.Analyzer):
    def start(self):
        self.previous_value = self.strategy.broker.getvalue()
        self.dates = []
        self.returns = []

    def _record(self):
        value = self.strategy.broker.getvalue()
        daily_return = value / self.previous_value - 1 if self.previous_value else 0.0
        self.dates.append(self.data.datetime.date(0).isoformat())
        self.returns.append(daily_return)
        self.previous_value = value

    prenext = _record
    nextstart = _record
    next = _record

    def get_analysis(self):
        return {"dates": self.dates, "returns": self.returns}


def run_daily_returns(symbol, csv_path, strategy_params=None):
    cerebro = bt.Cerebro()
    cerebro.adddata(
        bt.feeds.GenericCSVData(
            dataname=str(csv_path),
            dtformat="%Y-%m-%d",
            datetime=0,
            open=1,
            high=2,
            low=3,
            close=4,
            volume=5,
            openinterest=-1,
            reverse=False,
            header=0,
        )
    )
    cerebro.addstrategy(TurtleLiteStrategy, **(strategy_params or {}))
    configure_broker(cerebro.broker, starting_cash=STARTING_CASH)
    cerebro.addanalyzer(DailyReturnAnalyzer, _name="daily_returns")
    with contextlib.redirect_stdout(io.StringIO()):
        strategy = cerebro.run()[0]
    result = strategy.analyzers.daily_returns.get_analysis()
    return pd.Series(
        result["returns"],
        index=pd.to_datetime(result["dates"]),
        name=symbol,
        dtype=float,
    )


def build_return_matrix(symbol, data_directory="data", configurations=PARAMETER_CONFIGS):
    csv_path = Path(data_directory) / f"{symbol}.csv"
    series = []
    for name, parameters in configurations:
        item = run_daily_returns(symbol, csv_path, parameters)
        item.name = name
        series.append(item)
    frame = pd.concat(series, axis=1, join="inner").fillna(0.0)
    return frame


def sharpe_ratio(values, periods_per_year=252):
    values = np.asarray(values, dtype=float)
    if values.size < 2:
        return 0.0
    deviation = np.std(values, ddof=1)
    if deviation <= 0 or not np.isfinite(deviation):
        return 0.0
    return float(np.mean(values) / deviation * math.sqrt(periods_per_year))


def relative_rank(values, selected_index):
    selected = values[selected_index]
    below = np.sum(values < selected)
    tied_others = max(0, np.sum(np.isclose(values, selected)) - 1)
    return float(1 + below + 0.5 * tied_others)


def stochastic_dominance(selected_values, random_values):
    selected = np.asarray(selected_values, dtype=float)
    random_values = np.asarray(random_values, dtype=float)
    thresholds = np.unique(np.concatenate([selected, random_values]))
    selected_cdf = np.array([np.mean(selected <= x) for x in thresholds])
    random_cdf = np.array([np.mean(random_values <= x) for x in thresholds])
    first_order = bool(
        np.all(selected_cdf <= random_cdf + 1e-12)
        and np.any(selected_cdf < random_cdf - 1e-12)
    )
    if len(thresholds) > 1:
        increments = np.diff(thresholds, prepend=thresholds[0])
        integrated = np.cumsum((random_cdf - selected_cdf) * increments)
        second_order = bool(
            np.all(integrated >= -1e-12) and np.any(integrated > 1e-12)
        )
    else:
        second_order = False
    return {
        "first_order_dominance": first_order,
        "second_order_dominance": second_order,
        "thresholds": thresholds.tolist(),
        "selected_cdf": selected_cdf.tolist(),
        "random_cdf": random_cdf.tolist(),
    }


def cscv_pbo(return_matrix, blocks=DEFAULT_BLOCKS, periods_per_year=252):
    matrix = np.asarray(return_matrix, dtype=float)
    if blocks % 2 or blocks < 4:
        raise ValueError("blocks must be an even number of at least four")
    usable_rows = (len(matrix) // blocks) * blocks
    if usable_rows < blocks * 2:
        raise ValueError("not enough synchronized observations for CSCV")
    matrix = matrix[-usable_rows:]
    block_indexes = np.array_split(np.arange(usable_rows), blocks)
    combinations = list(itertools.combinations(range(blocks), blocks // 2))

    logits = []
    is_scores = []
    selected_oos_scores = []
    all_oos_scores = []
    selected_indexes = []
    for chosen_blocks in combinations:
        chosen = set(chosen_blocks)
        is_index = np.concatenate([block_indexes[i] for i in range(blocks) if i in chosen])
        oos_index = np.concatenate([block_indexes[i] for i in range(blocks) if i not in chosen])
        is_performance = np.array(
            [sharpe_ratio(matrix[is_index, column], periods_per_year)
             for column in range(matrix.shape[1])]
        )
        oos_performance = np.array(
            [sharpe_ratio(matrix[oos_index, column], periods_per_year)
             for column in range(matrix.shape[1])]
        )
        selected = int(np.argmax(is_performance))
        rank = relative_rank(oos_performance, selected)
        omega = rank / (matrix.shape[1] + 1)
        logits.append(math.log(omega / (1 - omega)))
        is_scores.append(float(is_performance[selected]))
        selected_oos_scores.append(float(oos_performance[selected]))
        all_oos_scores.extend(oos_performance.tolist())
        selected_indexes.append(selected)

    if np.std(is_scores) > 1e-12:
        slope, intercept = np.polyfit(is_scores, selected_oos_scores, 1)
    else:
        slope, intercept = 0.0, float(np.mean(selected_oos_scores))
    if np.std(is_scores) > 1e-12 and np.std(selected_oos_scores) > 1e-12:
        correlation = float(np.corrcoef(is_scores, selected_oos_scores)[0, 1])
    else:
        correlation = 0.0
    dominance = stochastic_dominance(selected_oos_scores, all_oos_scores)
    return {
        "pbo": round(float(np.mean(np.asarray(logits) < 0)), 4),
        "combinations": len(combinations),
        "blocks": blocks,
        "observations": usable_rows,
        "configurations": matrix.shape[1],
        "probability_oos_loss": round(float(np.mean(np.asarray(selected_oos_scores) < 0)), 4),
        "degradation_slope": round(float(slope), 4),
        "degradation_intercept": round(float(intercept), 4),
        "is_oos_correlation": round(correlation, 4),
        "logits": logits,
        "selected_is_scores": is_scores,
        "selected_oos_scores": selected_oos_scores,
        "all_oos_scores": all_oos_scores,
        "selected_configuration_indexes": selected_indexes,
        "stochastic_dominance": dominance,
    }


def minimum_track_record_length(
    daily_returns,
    confidence=0.95,
    benchmark_sharpe=0.0,
    periods_per_year=252,
):
    values = np.asarray(daily_returns, dtype=float)
    values = values[np.isfinite(values)]
    deviation = np.std(values, ddof=1) if len(values) > 1 else 0.0
    daily_sharpe = np.mean(values) / deviation if deviation > 0 else 0.0
    if daily_sharpe <= benchmark_sharpe:
        return {
            "daily_sharpe": round(float(daily_sharpe), 8),
            "annualized_sharpe": round(float(daily_sharpe * math.sqrt(periods_per_year)), 4),
            "required_observations": None,
            "observed_observations": len(values),
            "passes": False,
            "reason": "Observed Sharpe does not exceed the benchmark.",
        }
    centered = values - np.mean(values)
    second = np.mean(centered ** 2)
    skew = np.mean(centered ** 3) / second ** 1.5 if second > 0 else 0.0
    kurtosis = np.mean(centered ** 4) / second ** 2 if second > 0 else 3.0
    z_score = NormalDist().inv_cdf(confidence)
    adjustment = 1 - skew * daily_sharpe + ((kurtosis - 1) / 4) * daily_sharpe ** 2
    required = 1 + adjustment * (z_score / (daily_sharpe - benchmark_sharpe)) ** 2
    return {
        "daily_sharpe": round(float(daily_sharpe), 8),
        "annualized_sharpe": round(float(daily_sharpe * math.sqrt(periods_per_year)), 4),
        "skewness": round(float(skew), 4),
        "kurtosis": round(float(kurtosis), 4),
        "confidence": confidence,
        "required_observations": int(math.ceil(required)),
        "required_years": round(float(required / periods_per_year), 2),
        "observed_observations": len(values),
        "observed_years": round(float(len(values) / periods_per_year), 2),
        "passes": bool(len(values) >= required),
    }


def market_regimes(csv_path, index):
    prices = pd.read_csv(csv_path, parse_dates=["Date"]).set_index("Date")["Close"]
    prices = prices.reindex(index).ffill()
    long_average = prices.rolling(200, min_periods=200).mean()
    daily_change = prices.pct_change()
    realized_volatility = daily_change.rolling(20, min_periods=20).std()
    volatility_median = realized_volatility.median()
    return {
        "bull": (prices >= long_average).fillna(False).to_numpy(),
        "bear": (prices < long_average).fillna(False).to_numpy(),
        "high_volatility": (realized_volatility >= volatility_median).fillna(False).to_numpy(),
        "low_volatility": (realized_volatility < volatility_median).fillna(False).to_numpy(),
    }


def analyze_symbol(symbol, data_directory="data", blocks=DEFAULT_BLOCKS):
    periods_per_year = 365 if "-USD" in symbol else 252
    configurations = list(PARAMETER_CONFIGS)
    frame = build_return_matrix(symbol, data_directory, configurations)
    main = cscv_pbo(frame.to_numpy(), blocks, periods_per_year)
    baseline_mintrl = minimum_track_record_length(
        frame["baseline"].to_numpy(), periods_per_year=periods_per_year
    )

    trial_sensitivity = []
    for count in (3, 5, 7, len(configurations)):
        subset = frame.iloc[:, :count]
        result = cscv_pbo(subset.to_numpy(), blocks, periods_per_year)
        trial_sensitivity.append({"trials": count, "pbo": result["pbo"]})

    regimes = {}
    csv_path = Path(data_directory) / f"{symbol}.csv"
    for name, mask in market_regimes(csv_path, frame.index).items():
        regime_matrix = frame.to_numpy()[mask]
        try:
            regimes[name] = cscv_pbo(regime_matrix, blocks, periods_per_year)
        except ValueError as error:
            regimes[name] = {"error": str(error), "observations": len(regime_matrix)}

    return {
        "symbol": symbol,
        "configuration_names": [name for name, _ in configurations],
        "cscv": main,
        "minimum_track_record_length": baseline_mintrl,
        "trial_count_sensitivity": trial_sensitivity,
        "regime_pbo": regimes,
    }


def save_degradation_plot(result, output_path):
    cscv = result["cscv"]
    x_values = np.asarray(cscv["selected_is_scores"])
    y_values = np.asarray(cscv["selected_oos_scores"])
    figure, axis = plt.subplots(figsize=(7, 5))
    axis.scatter(x_values, y_values, alpha=0.65, s=24)
    if len(x_values) > 1:
        line_x = np.linspace(x_values.min(), x_values.max(), 100)
        line_y = cscv["degradation_intercept"] + cscv["degradation_slope"] * line_x
        axis.plot(line_x, line_y, color="darkred", linewidth=2)
    axis.axhline(0, color="gray", linewidth=1)
    axis.set_title(f"{result['symbol']} CSCV performance degradation")
    axis.set_xlabel("Selected configuration in-sample Sharpe")
    axis.set_ylabel("Same configuration out-of-sample Sharpe")
    axis.xaxis.set_major_locator(MaxNLocator(nbins=7))
    axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def save_trial_plot(results, output_path):
    figure, axis = plt.subplots(figsize=(8, 5))
    for result in results:
        sensitivity = result["trial_count_sensitivity"]
        axis.plot(
            [item["trials"] for item in sensitivity],
            [item["pbo"] for item in sensitivity],
            marker="o",
            label=result["symbol"],
        )
    axis.axhline(0.5, color="darkred", linestyle="--", linewidth=1, label="PBO 0.50")
    axis.set_ylim(-0.03, 1.03)
    axis.set_title("PBO sensitivity to number of parameter trials")
    axis.set_xlabel("Number of predeclared trials")
    axis.set_ylabel("Probability of backtest overfitting")
    axis.grid(alpha=0.2)
    axis.legend(ncol=2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def save_regime_plot(results, output_path):
    regime_names = ("bull", "bear", "high_volatility", "low_volatility")
    x_positions = np.arange(len(results))
    width = 0.18
    figure, axis = plt.subplots(figsize=(9, 5))
    for index, regime in enumerate(regime_names):
        values = [result["regime_pbo"][regime].get("pbo", np.nan) for result in results]
        axis.bar(x_positions + (index - 1.5) * width, values, width, label=regime.replace("_", " "))
    axis.axhline(0.5, color="darkred", linestyle="--", linewidth=1)
    axis.set_xticks(x_positions, [result["symbol"] for result in results])
    axis.set_ylim(0, 1)
    axis.set_ylabel("Probability of backtest overfitting")
    axis.set_title("Regime-specific PBO")
    axis.legend(ncol=2)
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def save_dominance_plot(result, output_path):
    dominance = result["cscv"]["stochastic_dominance"]
    figure, axis = plt.subplots(figsize=(7, 5))
    axis.plot(dominance["thresholds"], dominance["selected_cdf"], label="IS-selected OOS")
    axis.plot(dominance["thresholds"], dominance["random_cdf"], label="All OOS choices")
    axis.set_title(f"{result['symbol']} OOS stochastic dominance check")
    axis.set_xlabel("Out-of-sample Sharpe")
    axis.set_ylabel("Cumulative probability")
    axis.grid(alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def compact_result(result):
    cscv = result["cscv"]
    return {
        "symbol": result["symbol"],
        "pbo": cscv["pbo"],
        "oos_loss_probability": cscv["probability_oos_loss"],
        "degradation_slope": cscv["degradation_slope"],
        "is_oos_correlation": cscv["is_oos_correlation"],
        "first_order_dominance": cscv["stochastic_dominance"]["first_order_dominance"],
        "second_order_dominance": cscv["stochastic_dominance"]["second_order_dominance"],
        "mintrl_passes": result["minimum_track_record_length"]["passes"],
        "mintrl_required": result["minimum_track_record_length"].get("required_observations"),
        "mintrl_observed": result["minimum_track_record_length"]["observed_observations"],
        "regime_pbo": {
            name: metrics.get("pbo") for name, metrics in result["regime_pbo"].items()
        },
    }


def report_detail(result):
    """Keep reproducible split results while omitting arrays already rendered as plots."""
    detail = copy.deepcopy(result)
    detail["cscv"].pop("all_oos_scores", None)
    dominance = detail["cscv"]["stochastic_dominance"]
    dominance.pop("thresholds", None)
    dominance.pop("selected_cdf", None)
    dominance.pop("random_cdf", None)
    for regime in detail["regime_pbo"].values():
        if "stochastic_dominance" in regime:
            regime.pop("all_oos_scores", None)
            regime_dominance = regime["stochastic_dominance"]
            regime_dominance.pop("thresholds", None)
            regime_dominance.pop("selected_cdf", None)
            regime_dominance.pop("random_cdf", None)
    return detail


def main():
    parser = argparse.ArgumentParser(description="Run CSCV/PBO overfitting diagnostics.")
    parser.add_argument("--data-directory", default="data")
    parser.add_argument("--output-directory", default="reports/pbo")
    parser.add_argument("--symbols", nargs="+", default=[*STOCK_SYMBOLS, "SOL-USD"])
    parser.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS)
    args = parser.parse_args()

    output_directory = Path(args.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    results = []
    for symbol in args.symbols:
        print(f"Running CSCV diagnostics for {symbol}...")
        result = analyze_symbol(symbol, args.data_directory, args.blocks)
        results.append(result)
        save_degradation_plot(result, output_directory / f"{symbol.lower()}_degradation.png")
        save_dominance_plot(result, output_directory / f"{symbol.lower()}_dominance.png")

    save_trial_plot(results, output_directory / "trial_count_sensitivity.png")
    save_regime_plot(results, output_directory / "regime_pbo.png")
    report = {
        "method": {
            "type": "CSCV approximation using synchronized daily portfolio returns",
            "blocks": args.blocks,
            "selection_metric": "annualized Sharpe ratio",
            "confidence_for_mintrl": 0.95,
            "limitations": [
                "Regime labels are retrospective diagnostics, not trading signals.",
                "MinTRL assumes sufficiently independent return observations.",
                "Historical and simulated results do not guarantee future performance.",
            ],
        },
        "summary": [compact_result(result) for result in results],
        "details": [report_detail(result) for result in results],
    }
    report_path = output_directory / "pbo_analysis.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    print("\nSymbol   PBO    OOS loss  Degradation  FSD   SSD   MinTRL")
    for item in report["summary"]:
        print(
            f"{item['symbol']:<8} {item['pbo']:>5.2f} "
            f"{item['oos_loss_probability']:>9.2f} "
            f"{item['degradation_slope']:>12.2f} "
            f"{str(item['first_order_dominance']):>5} "
            f"{str(item['second_order_dominance']):>5} "
            f"{str(item['mintrl_passes']):>8}"
        )
    print(f"\nDetailed report and plots saved to {output_directory}")


if __name__ == "__main__":
    main()
