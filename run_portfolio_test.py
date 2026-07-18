"""Test the fixed Turtle baseline as one shared multi-asset portfolio."""

import argparse
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "turtle-lite-matplotlib")
)
import matplotlib.pyplot as plt

from run_backtest import COMMISSION_RATE, SLIPPAGE_RATE, STARTING_CASH


# These are the locked production-baseline assumptions. This runner does not
# optimize or select among alternatives.
BREAKOUT_PERIOD = 20
EXIT_PERIOD = 10
ATR_PERIOD = 14
RISK_PER_TRADE = 0.005
INITIAL_STOP_ATR = 2.0
ENTRY_BUFFER_ATR = 0.5
PORTFOLIO_RISK_CAP = 0.02


@dataclass
class Position:
    symbol: str
    size: int
    entry_price: float
    stop_price: float
    entry_commission: float
    entry_date: str
    committed_risk: float


def load_market_data(csv_path):
    frame = pd.read_csv(csv_path, parse_dates=["Date"]).set_index("Date").sort_index()
    previous_close = frame["Close"].shift(1)
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["atr"] = true_range.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean()
    frame["breakout_high"] = frame["High"].shift(1).rolling(BREAKOUT_PERIOD).max()
    frame["exit_low"] = frame["Low"].shift(1).rolling(EXIT_PERIOD).min()
    frame["sma50"] = frame["Close"].rolling(50).mean()
    frame["sma200"] = frame["Close"].rolling(200).mean()
    return frame


def calculate_position_size(entry_price, stop_price, risk_budget, cash):
    if entry_price <= stop_price or stop_price <= 0 or risk_budget <= 0 or cash <= 0:
        return 0
    risk_sized = int(risk_budget / (entry_price - stop_price))
    affordable = int(cash / (entry_price * (1 + COMMISSION_RATE)))
    return max(0, min(risk_sized, affordable))


def annualized_return(start_value, end_value, first_date, last_date):
    years = (last_date - first_date).days / 365.25
    if years <= 0 or start_value <= 0 or end_value <= 0:
        return 0.0
    return ((end_value / start_value) ** (1 / years) - 1) * 100


def maximum_drawdown(equity_values):
    values = np.asarray(equity_values, dtype=float)
    peaks = np.maximum.accumulate(values)
    drawdowns = np.where(peaks > 0, (peaks - values) / peaks, 0)
    return float(np.max(drawdowns) * 100) if len(values) else 0.0


def build_equal_weight_benchmark(market_data, dates, starting_cash):
    allocation = starting_cash / len(market_data)
    cash = starting_cash
    holdings = {}
    latest_close = {}
    values = []
    for current_date in dates:
        for symbol, frame in market_data.items():
            if current_date not in frame.index:
                continue
            close = float(frame.at[current_date, "Close"])
            latest_close[symbol] = close
            if symbol not in holdings:
                units = allocation / close
                holdings[symbol] = units
                cash -= allocation
        values.append(cash + sum(holdings[s] * latest_close[s] for s in holdings))
    return values


def run_portfolio(
    symbols,
    data_directory="data",
    start_date="2020-01-01",
    end_date=None,
    portfolio_risk_cap=PORTFOLIO_RISK_CAP,
):
    market_data = {
        symbol: load_market_data(Path(data_directory) / f"{symbol}.csv")
        for symbol in symbols
    }
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) if end_date else None
    all_dates = sorted(
        set().union(
            *[
                set(frame.index[(frame.index >= start) & ((frame.index <= end) if end else True)])
                for frame in market_data.values()
            ]
        )
    )
    if len(all_dates) < 2:
        raise ValueError("The selected portfolio period has insufficient market data.")

    cash = STARTING_CASH
    positions = {}
    pending_entries = {}
    pending_exits = set()
    latest_close = {}
    trades = []
    equity_curve = []
    open_risk_curve = []
    invested_capital_curve = []
    allocation_risk_percentages = []
    risk_cap_rejections = 0
    unfilled_entries = 0

    for current_date in all_dates:
        # Execute exits and stops before new entries on each asset's next bar.
        for symbol in sorted(list(positions)):
            frame = market_data[symbol]
            if current_date not in frame.index:
                continue
            row = frame.loc[current_date]
            position = positions[symbol]
            stop_hit = row["Open"] <= position.stop_price or row["Low"] <= position.stop_price
            channel_exit = symbol in pending_exits
            if not (stop_hit or channel_exit):
                continue
            if stop_hit and row["Open"] <= position.stop_price:
                raw_exit = float(row["Open"])
            elif stop_hit:
                raw_exit = position.stop_price
            else:
                raw_exit = float(row["Open"])
            exit_price = raw_exit * (1 - SLIPPAGE_RATE)
            proceeds = position.size * exit_price
            exit_commission = proceeds * COMMISSION_RATE
            cash += proceeds - exit_commission
            gross_pnl = (exit_price - position.entry_price) * position.size
            trades.append(
                {
                    "symbol": symbol,
                    "entry_date": position.entry_date,
                    "exit_date": current_date.date().isoformat(),
                    "exit_reason": "atr_stop" if stop_hit else "channel_exit",
                    "net_pnl": round(
                        gross_pnl - position.entry_commission - exit_commission, 2
                    ),
                }
            )
            positions.pop(symbol)
            pending_exits.discard(symbol)

        # Attempt yesterday's one-session capped limit entries.
        for symbol in sorted(list(pending_entries)):
            frame = market_data[symbol]
            if current_date not in frame.index:
                continue
            pending = pending_entries.pop(symbol)
            row = frame.loc[current_date]
            if row["Open"] <= pending["max_entry_price"]:
                raw_fill = float(row["Open"])
            elif row["Low"] <= pending["max_entry_price"]:
                raw_fill = pending["max_entry_price"]
            else:
                unfilled_entries += 1
                continue
            fill_price = min(
                pending["max_entry_price"], raw_fill * (1 + SLIPPAGE_RATE)
            )
            current_equity = cash + sum(
                position.size * latest_close.get(name, position.entry_price)
                for name, position in positions.items()
            )
            committed = sum(position.committed_risk for position in positions.values())
            available_risk = max(0.0, current_equity * portfolio_risk_cap - committed)
            risk_budget = min(pending["risk_budget"], available_risk)
            size = calculate_position_size(
                fill_price, pending["stop_price"], risk_budget, cash
            )
            if size <= 0:
                risk_cap_rejections += 1
                continue
            cost = size * fill_price
            commission = cost * COMMISSION_RATE
            cash -= cost + commission
            positions[symbol] = Position(
                symbol=symbol,
                size=size,
                entry_price=fill_price,
                stop_price=pending["stop_price"],
                entry_commission=commission,
                entry_date=current_date.date().isoformat(),
                committed_risk=size * (fill_price - pending["stop_price"]),
            )
            allocation_risk_percentages.append(
                (
                    sum(item.committed_risk for item in positions.values())
                    / current_equity
                )
                * 100
            )

        # Update marks, create exits, and reserve risk for new signals.
        for symbol, frame in market_data.items():
            if current_date not in frame.index:
                continue
            row = frame.loc[current_date]
            latest_close[symbol] = float(row["Close"])
            if symbol in positions:
                if row["Close"] < row["exit_low"]:
                    pending_exits.add(symbol)

        current_equity = cash + sum(
            position.size * latest_close.get(symbol, position.entry_price)
            for symbol, position in positions.items()
        )
        committed = sum(position.committed_risk for position in positions.values())
        reserved = 0.0
        for symbol in symbols:
            if symbol in positions or symbol in pending_entries:
                continue
            frame = market_data[symbol]
            if current_date not in frame.index:
                continue
            row = frame.loc[current_date]
            required = [
                row["atr"], row["breakout_high"], row["sma50"], row["sma200"]
            ]
            if any(pd.isna(value) for value in required):
                continue
            trend_ok = row["Close"] > row["sma200"] and row["sma50"] > row["sma200"]
            breakout_ok = row["Close"] > row["breakout_high"]
            if not (trend_ok and breakout_ok):
                continue
            available_risk = current_equity * portfolio_risk_cap - committed - reserved
            risk_budget = min(current_equity * RISK_PER_TRADE, max(0.0, available_risk))
            if risk_budget <= 0:
                risk_cap_rejections += 1
                continue
            stop_price = float(row["Close"] - INITIAL_STOP_ATR * row["atr"])
            max_entry_price = float(row["Close"] + ENTRY_BUFFER_ATR * row["atr"])
            pending_entries[symbol] = {
                "stop_price": stop_price,
                "max_entry_price": max_entry_price,
                "risk_budget": risk_budget,
            }
            reserved += risk_budget

        current_equity = cash + sum(
            position.size * latest_close.get(symbol, position.entry_price)
            for symbol, position in positions.items()
        )
        open_risk = sum(position.committed_risk for position in positions.values())
        invested_capital = sum(
            position.size * latest_close.get(symbol, position.entry_price)
            for symbol, position in positions.items()
        )
        equity_curve.append(current_equity)
        open_risk_curve.append(open_risk / current_equity if current_equity > 0 else 0)
        invested_capital_curve.append(
            invested_capital / current_equity if current_equity > 0 else 0
        )

    benchmark_curve = build_equal_weight_benchmark(market_data, all_dates, STARTING_CASH)
    daily_returns = pd.Series(equity_curve, index=all_dates).pct_change().dropna()
    periods_per_year = 365 if any("-USD" in symbol for symbol in symbols) else 252
    sharpe = (
        daily_returns.mean() / daily_returns.std(ddof=1) * math.sqrt(periods_per_year)
        if daily_returns.std(ddof=1) > 0 else 0.0
    )
    final_value = equity_curve[-1]
    total_return = (final_value / STARTING_CASH - 1) * 100
    benchmark_return = (benchmark_curve[-1] / STARTING_CASH - 1) * 100
    strategy_cagr = annualized_return(
        STARTING_CASH, final_value, all_dates[0], all_dates[-1]
    )
    strategy_drawdown = maximum_drawdown(equity_curve)
    benchmark_cagr = annualized_return(
        STARTING_CASH, benchmark_curve[-1], all_dates[0], all_dates[-1]
    )
    benchmark_drawdown = maximum_drawdown(benchmark_curve)
    return {
        "portfolio": list(symbols),
        "start_date": all_dates[0].date().isoformat(),
        "end_date": all_dates[-1].date().isoformat(),
        "locked_parameters": {
            "breakout_period": BREAKOUT_PERIOD,
            "exit_period": EXIT_PERIOD,
            "atr_period": ATR_PERIOD,
            "risk_per_trade": RISK_PER_TRADE,
            "initial_stop_atr": INITIAL_STOP_ATR,
            "entry_buffer_atr": ENTRY_BUFFER_ATR,
            "portfolio_risk_cap": portfolio_risk_cap,
            "trend_filter": "close > SMA200 and SMA50 > SMA200",
        },
        "final_value": round(final_value, 2),
        "total_return_percent": round(total_return, 2),
        "annualized_return_percent": round(strategy_cagr, 2),
        "max_drawdown_percent": round(strategy_drawdown, 2),
        "annualized_return_to_drawdown": round(
            strategy_cagr / strategy_drawdown, 2
        ) if strategy_drawdown else 0,
        "sharpe_ratio": round(float(sharpe), 3),
        "benchmark_total_return_percent": round(benchmark_return, 2),
        "benchmark_annualized_return_percent": round(benchmark_cagr, 2),
        "benchmark_max_drawdown_percent": round(benchmark_drawdown, 2),
        "benchmark_annualized_return_to_drawdown": round(
            benchmark_cagr / benchmark_drawdown, 2
        ) if benchmark_drawdown else 0,
        "time_with_any_position_percent": round(
            np.mean(np.asarray(invested_capital_curve) > 0) * 100, 2
        ),
        "average_capital_invested_percent": round(
            np.mean(invested_capital_curve) * 100, 2
        ),
        "maximum_allocated_entry_risk_percent": round(
            max(allocation_risk_percentages, default=0), 4
        ),
        "maximum_marked_open_risk_percent": round(max(open_risk_curve) * 100, 4),
        "closed_trades": len(trades),
        "risk_cap_rejections": risk_cap_rejections,
        "unfilled_entries": unfilled_entries,
        "trades_by_symbol": {
            symbol: sum(trade["symbol"] == symbol for trade in trades) for symbol in symbols
        },
        "equity_curve": [
            {"date": date.date().isoformat(), "value": round(value, 2)}
            for date, value in zip(all_dates, equity_curve)
        ],
        "benchmark_curve": [round(value, 2) for value in benchmark_curve],
        "marked_open_risk_curve_percent": [round(value * 100, 4) for value in open_risk_curve],
        "capital_invested_curve_percent": [
            round(value * 100, 2) for value in invested_capital_curve
        ],
    }


def save_report(report, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    curve_keys = {
        "equity_curve",
        "benchmark_curve",
        "marked_open_risk_curve_percent",
        "capital_invested_curve_percent",
    }
    summary = {key: value for key, value in report.items() if key not in curve_keys}
    output_path.write_text(json.dumps(summary, indent=2) + "\n")
    curve_path = output_path.with_name(f"{output_path.stem}_curve.csv")
    pd.DataFrame(
        {
            "date": [item["date"] for item in report["equity_curve"]],
            "portfolio_value": [item["value"] for item in report["equity_curve"]],
            "benchmark_value": report["benchmark_curve"],
            "marked_open_risk_percent": report["marked_open_risk_curve_percent"],
            "capital_invested_percent": report["capital_invested_curve_percent"],
        }
    ).to_csv(curve_path, index=False)
    return curve_path


def save_equity_plot(report, output_path):
    dates = pd.to_datetime([item["date"] for item in report["equity_curve"]])
    portfolio = np.array([item["value"] for item in report["equity_curve"]])
    benchmark = np.array(report["benchmark_curve"])
    figure, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    axes[0].plot(dates, portfolio / portfolio[0] * 100, label="Turtle portfolio")
    axes[0].plot(dates, benchmark / benchmark[0] * 100, label="Equal-weight buy and hold")
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Growth of $100 (log scale)")
    axes[0].set_title("Fixed-baseline portfolio versus benchmark")
    axes[0].grid(alpha=0.2)
    axes[0].legend()

    axes[1].plot(
        dates,
        report["capital_invested_curve_percent"],
        label="Capital invested",
    )
    axes[1].plot(
        dates,
        report["marked_open_risk_curve_percent"],
        label="Marked open risk",
    )
    axes[1].axhline(
        report["locked_parameters"]["portfolio_risk_cap"] * 100,
        color="darkred",
        linestyle="--",
        linewidth=1,
        label="Entry risk cap",
    )
    axes[1].set_ylabel("Percent")
    axes[1].grid(alpha=0.2)
    axes[1].legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description="Run the fixed multi-asset portfolio test.")
    parser.add_argument(
        "--symbols", nargs="+", default=["SPY", "QQQ", "AAPL", "GOOGL", "NVDA", "SOL-USD"]
    )
    parser.add_argument("--start-date", default="2020-04-10")
    parser.add_argument("--end-date")
    parser.add_argument("--risk-cap", type=float, default=PORTFOLIO_RISK_CAP)
    parser.add_argument("--output", default="reports/portfolio/fixed_baseline.json")
    args = parser.parse_args()

    report = run_portfolio(
        args.symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        portfolio_risk_cap=args.risk_cap,
    )
    curve_path = save_report(report, args.output)
    chart_path = Path(args.output).with_suffix(".png")
    save_equity_plot(report, chart_path)
    print("\nFIXED-BASELINE MULTI-ASSET PORTFOLIO")
    print(f"Assets: {', '.join(report['portfolio'])}")
    print(f"Return: {report['total_return_percent']:.2f}%")
    print(f"Annualized return: {report['annualized_return_percent']:.2f}%")
    print(f"Maximum drawdown: {report['max_drawdown_percent']:.2f}%")
    print(
        "Annualized return / drawdown: "
        f"{report['annualized_return_to_drawdown']:.2f}"
    )
    print(
        "Maximum allocated entry risk: "
        f"{report['maximum_allocated_entry_risk_percent']:.2f}%"
    )
    print(
        "Maximum marked open risk: "
        f"{report['maximum_marked_open_risk_percent']:.2f}%"
    )
    print(f"Average capital invested: {report['average_capital_invested_percent']:.2f}%")
    print(f"Benchmark annualized return: {report['benchmark_annualized_return_percent']:.2f}%")
    print(f"Detailed report saved to {args.output}")
    print(f"Daily monitoring data saved to {curve_path}")
    print(f"Equity and exposure chart saved to {chart_path}")


if __name__ == "__main__":
    main()
