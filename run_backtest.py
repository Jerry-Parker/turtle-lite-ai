import json
import os
import sys

import backtrader as bt

from strategies.turtle_lite import TurtleLiteStrategy


def safe_get(dictionary, *keys, default=0):
    """
    Safely get nested values from Backtrader analyzer dictionaries.
    If a value does not exist, return the default.
    """
    value = dictionary

    for key in keys:
        try:
            value = value[key]
        except Exception:
            return default

    return value


def format_money(value):
    return f"${value:,.2f}"


def format_percent(value):
    return f"{value:.2f}%"


def save_json_report(report, output_path="reports/backtest_report.json"):
    """
    Save the backtest report to a JSON file.
    This file can later be used by the AI coach or front-end app.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as file:
        json.dump(report, file, indent=2)

    print(f"\nJSON report saved to: {output_path}")


def main():
    symbol = "SPY"

    if len(sys.argv) > 1:
        symbol = sys.argv[1].upper()

    cerebro = bt.Cerebro()

    data = bt.feeds.GenericCSVData(
        dataname=f"data/{symbol}.csv",
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

    cerebro.adddata(data)
    cerebro.addstrategy(TurtleLiteStrategy)

    starting_cash = 100000.00

    cerebro.broker.setcash(starting_cash)
    cerebro.broker.setcommission(commission=0.001)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    print("\nRunning Turtle Lite backtest...\n")
    print(f"Starting Portfolio Value: {format_money(starting_cash)}")

    results = cerebro.run()
    strategy = results[0]

    final_value = cerebro.broker.getvalue()
    net_profit = final_value - starting_cash
    return_percent = (net_profit / starting_cash) * 100

    sharpe_data = strategy.analyzers.sharpe.get_analysis()
    drawdown_data = strategy.analyzers.drawdown.get_analysis()
    trade_data = strategy.analyzers.trades.get_analysis()

    total_trades = safe_get(trade_data, "total", "closed")
    winning_trades = safe_get(trade_data, "won", "total")
    losing_trades = safe_get(trade_data, "lost", "total")

    gross_profit = safe_get(trade_data, "won", "pnl", "total")
    gross_loss = abs(safe_get(trade_data, "lost", "pnl", "total"))

    average_win = safe_get(trade_data, "won", "pnl", "average")
    average_loss = safe_get(trade_data, "lost", "pnl", "average")

    if total_trades > 0:
        win_rate = (winning_trades / total_trades) * 100
    else:
        win_rate = 0

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = 0

    max_drawdown = safe_get(drawdown_data, "max", "drawdown")
    max_drawdown_money = safe_get(drawdown_data, "max", "moneydown")
    sharpe_ratio = safe_get(sharpe_data, "sharperatio", default=None)

    report = {
        "strategy": "Turtle Lite",
        "symbol": symbol,
        "starting_portfolio": round(starting_cash, 2),
        "final_portfolio": round(final_value, 2),
        "net_profit_loss": round(net_profit, 2),
        "return_percent": round(return_percent, 2),
        "max_drawdown_percent": round(max_drawdown, 2),
        "max_money_drawdown": round(max_drawdown_money, 2),
        "sharpe_ratio": sharpe_ratio,
        "total_closed_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate_percent": round(win_rate, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "average_win": round(average_win, 2),
        "average_loss": round(average_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "summary": {
            "profitable": net_profit > 0,
            "average_winner_larger_than_average_loser": average_win > abs(average_loss),
            "style": "Trend-following breakout system",
            "risk_note": "This is a historical backtest only. Past results do not guarantee future performance.",
        },
    }

    print("\n==============================")
    print("TURTLE LITE BACKTEST REPORT")
    print("==============================")

    print(f"Starting Portfolio: {format_money(starting_cash)}")
    print(f"Final Portfolio:    {format_money(final_value)}")
    print(f"Net Profit/Loss:    {format_money(net_profit)}")
    print(f"Return:             {format_percent(return_percent)}")

    print("\n--- Risk ---")
    print(f"Max Drawdown:       {format_percent(max_drawdown)}")
    print(f"Max Money Drawdown: {format_money(max_drawdown_money)}")
    print(f"Sharpe Ratio:       {sharpe_ratio}")

    print("\n--- Trades ---")
    print(f"Total Closed Trades: {total_trades}")
    print(f"Winning Trades:      {winning_trades}")
    print(f"Losing Trades:       {losing_trades}")
    print(f"Win Rate:            {format_percent(win_rate)}")
    print(f"Average Win:         {format_money(average_win)}")
    print(f"Average Loss:        {format_money(average_loss)}")
    print(f"Profit Factor:       {profit_factor:.2f}")

    print("\n--- Plain English Summary ---")

    if net_profit > 0:
        print("The strategy made money over the tested period.")
    elif net_profit < 0:
        print("The strategy lost money over the tested period.")
    else:
        print("The strategy ended close to breakeven.")

    if total_trades > 0:
        print(
            "This is a trend-following style system. It does not need to win every trade. "
            "The key question is whether the average winner is larger than the average loser."
        )

    if average_win > abs(average_loss):
        print("The average winning trade was larger than the average losing trade.")
    else:
        print("The average winning trade was not larger than the average losing trade.")

    print("\nBacktest complete.")

    save_json_report(report)


if __name__ == "__main__":
    main()