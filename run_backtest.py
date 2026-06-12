import backtrader as bt
from strategies.turtle_lite import TurtleLiteStrategy


def main():
    cerebro = bt.Cerebro()

    data = bt.feeds.GenericCSVData(
        dataname="data/SPY.csv",
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

    cerebro.broker.setcash(100000.00)
    cerebro.broker.setcommission(commission=0.001)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    print(f"Starting Portfolio Value: ${cerebro.broker.getvalue():,.2f}")

    results = cerebro.run()
    strategy = results[0]

    print(f"Final Portfolio Value: ${cerebro.broker.getvalue():,.2f}")
    print("Sharpe:", strategy.analyzers.sharpe.get_analysis())
    print("Drawdown:", strategy.analyzers.drawdown.get_analysis())
    print("Trades:", strategy.analyzers.trades.get_analysis())


if __name__ == "__main__":
    main()