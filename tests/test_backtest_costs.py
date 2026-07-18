import unittest

import backtrader as bt
import pandas as pd

from run_backtest import configure_broker


class RoundTripStrategy(bt.Strategy):
    def __init__(self):
        self.fills = []

    def next(self):
        if len(self) == 1:
            self.buy(size=1)
        elif len(self) == 2 and self.position:
            self.sell(size=1)

    def notify_order(self, order):
        if order.status == order.Completed:
            self.fills.append(
                ("buy" if order.isbuy() else "sell", order.executed.price, order.executed.comm)
            )


class BacktestCostTests(unittest.TestCase):
    def _run_round_trip(self, commission_rate=0.001, slippage_rate=0.01):
        rows = [
            {"open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0, "volume": 1}
            for _ in range(3)
        ]
        frame = pd.DataFrame(rows)
        frame.index = pd.date_range("2024-01-01", periods=3, freq="D")

        cerebro = bt.Cerebro()
        cerebro.addstrategy(RoundTripStrategy)
        cerebro.adddata(bt.feeds.PandasData(dataname=frame))
        configure_broker(
            cerebro.broker,
            starting_cash=1000.0,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
        )
        strategy = cerebro.run()[0]
        return strategy, cerebro.broker.getvalue()

    def test_slippage_worsens_buy_and_sell_fill_prices(self):
        strategy, _ = self._run_round_trip(commission_rate=0.0, slippage_rate=0.01)
        self.assertEqual(strategy.fills[0][0:2], ("buy", 101.0))
        self.assertEqual(strategy.fills[1][0:2], ("sell", 99.0))

    def test_commission_and_slippage_reduce_portfolio_value(self):
        strategy, final_value = self._run_round_trip()
        self.assertAlmostEqual(strategy.fills[0][2], 0.101)
        self.assertAlmostEqual(strategy.fills[1][2], 0.099)
        self.assertAlmostEqual(final_value, 997.8)

    def test_negative_cost_assumptions_are_rejected(self):
        broker = bt.Cerebro().broker
        with self.assertRaises(ValueError):
            configure_broker(broker, commission_rate=-0.001)
        with self.assertRaises(ValueError):
            configure_broker(broker, slippage_rate=-0.001)


if __name__ == "__main__":
    unittest.main()
