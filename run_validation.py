"""Run the Turtle Lite strategy across every local asset and time period."""

import argparse
import contextlib
import csv
import io
import json
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


def discover_symbols(data_directory):
    """Return the symbols represented by CSV files in the data directory."""
    return sorted(path.stem.upper() for path in Path(data_directory).glob("*.csv"))


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d") if value else None


def run_period(symbol, csv_path, period_name, start_date=None, end_date=None):
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
    cerebro.addstrategy(TurtleLiteStrategy)
    configure_broker(cerebro.broker, starting_cash=STARTING_CASH)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    # The strategy logs individual orders; the matrix report only needs totals.
    with contextlib.redirect_stdout(io.StringIO()):
        strategy = cerebro.run()[0]

    final_value = cerebro.broker.getvalue()
    trade_data = strategy.analyzers.trades.get_analysis()
    drawdown_data = strategy.analyzers.drawdown.get_analysis()
    sharpe_data = strategy.analyzers.sharpe.get_analysis()
    gross_profit = safe_get(trade_data, "won", "pnl", "total")
    gross_loss = abs(safe_get(trade_data, "lost", "pnl", "total"))

    return {
        "symbol": symbol,
        "period": period_name,
        "start_date": start_date,
        "end_date": end_date,
        "return_percent": round(((final_value - STARTING_CASH) / STARTING_CASH) * 100, 2),
        "max_drawdown_percent": round(
            safe_get(drawdown_data, "max", "drawdown"), 2
        ),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else 0,
        "sharpe_ratio": safe_get(sharpe_data, "sharperatio", default=None),
        "closed_trades": safe_get(trade_data, "total", "closed"),
        "rejected_entries": strategy.rejected_entries,
    }


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
        writer = csv.DictWriter(file, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    return json_path, csv_path


def print_summary(results):
    print("\nMULTI-ASSET SPLIT-PERIOD VALIDATION")
    print("Symbol  Period          Return    Drawdown   Profit factor  Trades")
    for result in results:
        print(
            f"{result['symbol']:<7} {result['period']:<15} "
            f"{result['return_percent']:>7.2f}% "
            f"{result['max_drawdown_percent']:>9.2f}% "
            f"{result['profit_factor']:>13.2f} "
            f"{result['closed_trades']:>7}"
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
