"""Run the Turtle Lite strategy across every local asset and time period."""

import argparse
import contextlib
import csv
import io
import json
import math
from datetime import datetime
from pathlib import Path

import backtrader as bt

from run_backtest import STARTING_CASH, configure_broker, safe_get
from strategies.turtle_lite import TurtleLiteStrategy


DEFAULT_PERIODS = (
    ("full_history", None, None),
    ("2005_2017", "2005-01-01", "2017-12-31"),
    ("2018_onward", "2018-01-01", None),
)


class ExposureAnalyzer(bt.Analyzer):
    """Measure test duration and the proportion of bars with an open position."""

    def start(self):
        self.bars = 0
        self.invested_bars = 0
        self.first_date = None
        self.last_date = None

    def _record(self):
        current_date = self.data.datetime.date(0)
        self.first_date = self.first_date or current_date
        self.last_date = current_date
        self.bars += 1
        if self.strategy.position:
            self.invested_bars += 1

    prenext = _record
    nextstart = _record
    next = _record

    def get_analysis(self):
        return {
            "bars": self.bars,
            "invested_bars": self.invested_bars,
            "first_date": self.first_date,
            "last_date": self.last_date,
        }


def discover_symbols(data_directory):
    """Return the symbols represented by CSV files in the data directory."""
    return sorted(path.stem.upper() for path in Path(data_directory).glob("*.csv"))


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d") if value else None


def annualized_return(starting_value, final_value, first_date, last_date):
    if starting_value <= 0 or final_value <= 0 or not first_date or not last_date:
        return 0.0
    years = (last_date - first_date).days / 365.25
    if years <= 0:
        return 0.0
    return ((final_value / starting_value) ** (1 / years) - 1) * 100


def benchmark_metrics(csv_path, start_date=None, end_date=None):
    """Calculate an idealized close-to-close buy-and-hold benchmark."""
    first_allowed = _parse_date(start_date).date() if start_date else None
    last_allowed = _parse_date(end_date).date() if end_date else None
    observations = []
    with Path(csv_path).open(newline="") as file:
        for row in csv.DictReader(file):
            row_date = _parse_date(row["Date"]).date()
            if first_allowed and row_date < first_allowed:
                continue
            if last_allowed and row_date > last_allowed:
                continue
            close = float(row["Close"])
            if math.isfinite(close) and close > 0:
                observations.append((row_date, close))
    if len(observations) < 2:
        return {
            "benchmark_return_percent": 0.0,
            "benchmark_annualized_return_percent": 0.0,
            "benchmark_max_drawdown_percent": 0.0,
        }

    peak = observations[0][1]
    max_drawdown = 0.0
    for _, close in observations:
        peak = max(peak, close)
        max_drawdown = max(max_drawdown, ((peak - close) / peak) * 100)
    first_date, first_close = observations[0]
    last_date, last_close = observations[-1]
    return {
        "benchmark_return_percent": round((last_close / first_close - 1) * 100, 2),
        "benchmark_annualized_return_percent": round(
            annualized_return(first_close, last_close, first_date, last_date), 2
        ),
        "benchmark_max_drawdown_percent": round(max_drawdown, 2),
    }


def observation_count(csv_path, start_date=None, end_date=None):
    first_allowed = _parse_date(start_date).date() if start_date else None
    last_allowed = _parse_date(end_date).date() if end_date else None
    count = 0
    with Path(csv_path).open(newline="") as file:
        for row in csv.DictReader(file):
            row_date = _parse_date(row["Date"]).date()
            if first_allowed and row_date < first_allowed:
                continue
            if last_allowed and row_date > last_allowed:
                continue
            count += 1
    return count


def run_period(
    symbol,
    csv_path,
    period_name,
    start_date=None,
    end_date=None,
    strategy_params=None,
    commission_rate=None,
    slippage_rate=None,
    include_trade_pnls=False,
):
    """Run one symbol/period combination and return its key measurements."""
    cerebro = bt.Cerebro()
    feed_options = {
        "dataname": str(csv_path),
        "dtformat": "%Y-%m-%d",
        "datetime": 0,
        "open": 1,
        "high": 2,
        "low": 3,
        "close": 4,
        "volume": 5,
        "openinterest": -1,
        "reverse": False,
        "header": 0,
    }
    if start_date:
        feed_options["fromdate"] = _parse_date(start_date)
    if end_date:
        feed_options["todate"] = _parse_date(end_date)

    cerebro.adddata(bt.feeds.GenericCSVData(**feed_options))
    cerebro.addstrategy(TurtleLiteStrategy, **(strategy_params or {}))
    broker_options = {"starting_cash": STARTING_CASH}
    if commission_rate is not None:
        broker_options["commission_rate"] = commission_rate
    if slippage_rate is not None:
        broker_options["slippage_rate"] = slippage_rate
    configure_broker(cerebro.broker, **broker_options)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(ExposureAnalyzer, _name="exposure")

    # The strategy logs individual orders; the matrix report only needs totals.
    with contextlib.redirect_stdout(io.StringIO()):
        strategy = cerebro.run()[0]

    final_value = cerebro.broker.getvalue()
    trade_data = strategy.analyzers.trades.get_analysis()
    drawdown_data = strategy.analyzers.drawdown.get_analysis()
    sharpe_data = strategy.analyzers.sharpe.get_analysis()
    exposure_data = strategy.analyzers.exposure.get_analysis()
    gross_profit = safe_get(trade_data, "won", "pnl", "total")
    gross_loss = abs(safe_get(trade_data, "lost", "pnl", "total"))

    cagr = annualized_return(
        STARTING_CASH,
        final_value,
        exposure_data["first_date"],
        exposure_data["last_date"],
    )
    max_drawdown = safe_get(drawdown_data, "max", "drawdown")
    benchmark = benchmark_metrics(csv_path, start_date, end_date)
    result = {
        "symbol": symbol,
        "period": period_name,
        "start_date": start_date,
        "end_date": end_date,
        "return_percent": round(((final_value - STARTING_CASH) / STARTING_CASH) * 100, 2),
        "annualized_return_percent": round(cagr, 2),
        "max_drawdown_percent": round(max_drawdown, 2),
        "return_to_drawdown": round(cagr / max_drawdown, 2) if max_drawdown else 0,
        "time_in_market_percent": round(
            (exposure_data["invested_bars"] / exposure_data["bars"]) * 100, 2
        ) if exposure_data["bars"] else 0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else 0,
        "sharpe_ratio": safe_get(sharpe_data, "sharperatio", default=None),
        "closed_trades": safe_get(trade_data, "total", "closed"),
        "rejected_entries": strategy.rejected_entries,
    }
    result.update(benchmark)
    result["annualized_return_vs_benchmark"] = round(
        result["annualized_return_percent"]
        - result["benchmark_annualized_return_percent"],
        2,
    )
    if include_trade_pnls:
        result["trade_net_pnls"] = [
            trade["net_pnl"] for trade in strategy.trade_diagnostics
        ]
    return result


def run_matrix(data_directory="data", periods=DEFAULT_PERIODS, symbols=None):
    """Run the validation matrix and return one record per symbol and period."""
    data_directory = Path(data_directory)
    symbols = symbols or discover_symbols(data_directory)
    if not symbols:
        raise ValueError(f"No CSV market data found in {data_directory}")

    results = []
    for symbol in symbols:
        csv_path = data_directory / f"{symbol}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing market data: {csv_path}")
        for period_name, start_date, end_date in periods:
            # The strategy needs a 200-day moving average before it can trade.
            if observation_count(csv_path, start_date, end_date) < 201:
                continue
            results.append(
                run_period(symbol, csv_path, period_name, start_date, end_date)
            )
    return results


def save_results(results, output_directory="reports"):
    """Save machine-readable JSON and spreadsheet-friendly CSV results."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "validation_matrix.json"
    csv_path = output_directory / "validation_matrix.csv"

    json_path.write_text(json.dumps(results, indent=2) + "\n")
    with csv_path.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=results[0].keys(),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(results)
    return json_path, csv_path


def print_summary(results):
    print("\nMULTI-ASSET SPLIT-PERIOD VALIDATION")
    print(
        "Symbol  Period          CAGR    Benchmark  Drawdown  Time invested  "
        "Profit factor"
    )
    for result in results:
        print(
            f"{result['symbol']:<7} {result['period']:<15} "
            f"{result['annualized_return_percent']:>6.2f}% "
            f"{result['benchmark_annualized_return_percent']:>9.2f}% "
            f"{result['max_drawdown_percent']:>8.2f}% "
            f"{result['time_in_market_percent']:>12.2f}% "
            f"{result['profit_factor']:>13.2f}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Validate Turtle Lite across all local assets and time periods."
    )
    parser.add_argument("--data-directory", default="data")
    parser.add_argument("--output-directory", default="reports")
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Optional symbol list; defaults to every CSV in the data directory.",
    )
    args = parser.parse_args()

    results = run_matrix(args.data_directory, symbols=args.symbols)
    print_summary(results)
    json_path, csv_path = save_results(results, args.output_directory)
    print(f"\nSaved detailed results to {json_path}")
    print(f"Saved spreadsheet results to {csv_path}")


if __name__ == "__main__":
    main()
