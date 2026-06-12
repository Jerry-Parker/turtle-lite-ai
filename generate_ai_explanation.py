import json
import os


REPORT_PATH = "reports/backtest_report.json"
OUTPUT_PATH = "reports/ai_explanation.md"


def format_money(value):
    return f"${value:,.2f}"


def format_percent(value):
    return f"{value:.2f}%"


def load_report():
    with open(REPORT_PATH, "r") as file:
        return json.load(file)


def create_explanation(report):
    strategy = report.get("strategy", "Unknown Strategy")
    symbol = report.get("symbol", "Unknown Symbol")

    starting_portfolio = report.get("starting_portfolio", 0)
    final_portfolio = report.get("final_portfolio", 0)
    net_profit_loss = report.get("net_profit_loss", 0)
    return_percent = report.get("return_percent", 0)

    total_trades = report.get("total_closed_trades", 0)
    winning_trades = report.get("winning_trades", 0)
    losing_trades = report.get("losing_trades", 0)
    win_rate = report.get("win_rate_percent", 0)

    profit_factor = report.get("profit_factor", 0)
    max_drawdown = report.get("max_drawdown_percent", 0)
    max_money_drawdown = report.get("max_money_drawdown", 0)

    average_win = report.get("average_win", 0)
    average_loss = report.get("average_loss", 0)

    if net_profit_loss > 0:
        result_summary = "made money"
    elif net_profit_loss < 0:
        result_summary = "lost money"
    else:
        result_summary = "finished close to breakeven"

    if average_win > abs(average_loss):
        winner_loser_summary = (
            "The average winning trade was larger than the average losing trade. "
            "That is a healthy sign for a trend-following system."
        )
    else:
        winner_loser_summary = (
            "The average winning trade was not larger than the average losing trade. "
            "That may be a weakness in the current version of the strategy."
        )

    explanation = f"""# {strategy} AI Coach Explanation

## 1. Simple Summary

This historical backtest tested the **{strategy}** strategy on **{symbol}**.

Over the tested period, the strategy **{result_summary}**.

It started with {format_money(starting_portfolio)} and finished with {format_money(final_portfolio)}.

The net result was {format_money(net_profit_loss)}, or {format_percent(return_percent)}.

## 2. Main Numbers

- Starting portfolio: {format_money(starting_portfolio)}
- Final portfolio: {format_money(final_portfolio)}
- Net profit/loss: {format_money(net_profit_loss)}
- Return: {format_percent(return_percent)}
- Total closed trades: {total_trades}
- Winning trades: {winning_trades}
- Losing trades: {losing_trades}
- Win rate: {format_percent(win_rate)}
- Profit factor: {profit_factor}
- Maximum drawdown: {format_percent(max_drawdown)}
- Maximum money drawdown: {format_money(max_money_drawdown)}

## 3. What This Means

This is a trend-following style system.

Trend-following systems often have a lower win rate than people expect. They can lose many small trades while waiting for a larger trend to develop.

In this backtest, the win rate was {format_percent(win_rate)}. That means the system did not win on most trades.

However, a trend-following system does not need to win every trade. The important question is whether the winners are large enough to pay for the losers.

{winner_loser_summary}

## 4. Risk Review

The maximum drawdown was {format_percent(max_drawdown)}, or about {format_money(max_money_drawdown)}.

Drawdown means the account fell from a previous high point before recovering or continuing lower.

A drawdown is normal in trading systems, even profitable ones. A profitable backtest does not mean the strategy is safe or guaranteed to work in live markets.

## 5. Beginner Lesson

The main lesson from this backtest is that discipline matters.

This strategy follows rules. It does not try to guess every market move.

The key lessons are:

- A strategy can make money with a win rate below 50% if the average winners are larger than the average losers.
- Position sizing matters because it controls how much is lost when the system is wrong.
- Backtesting is only the first step. The next step should be paper trading before any live trading is considered.

## 6. Final Caution

This is an educational backtest only.

It is not financial advice.

Past performance does not guarantee future results.
"""

    return explanation


def save_explanation(explanation):
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w") as file:
        file.write(explanation)

    print(f"AI explanation saved to: {OUTPUT_PATH}")


def main():
    report = load_report()
    explanation = create_explanation(report)
    save_explanation(explanation)

    print("\n==============================")
    print("AI EXPLANATION PREVIEW")
    print("==============================\n")
    print(explanation)


if __name__ == "__main__":
    main()