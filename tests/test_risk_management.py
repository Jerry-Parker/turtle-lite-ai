import unittest

import backtrader as bt
import pandas as pd

from strategies.turtle_lite import TurtleLiteStrategy


class RecordingStrategy(TurtleLiteStrategy):
    def __init__(self):
        super().__init__()
        self.order_events = []
        self.entry_filled = False
        self.entry_rejected = False
        self.stop_cancel_confirmed = False
        self.stop_fill_price = None
        self.stop_fill_size = None
        self.exit_sell_count = 0
        self.buy_size = None

    def notify_order(self, order):
        is_stop_order = order == self.stop_order
        super().notify_order(order)

        self.order_events.append(
            {
                "status": order.status,
                "isbuy": order.isbuy(),
                "issell": order.issell(),
                "price": order.price,
                "executed_price": getattr(order.executed, "price", None),
                "size": getattr(order.executed, "size", None),
            }
        )

        if order.isbuy() and order.status == order.Completed:
            self.entry_filled = True
            self.buy_size = int(getattr(order.executed, "size", 0))
        elif order.isbuy() and order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.entry_rejected = True

        if order.issell() and order.status == order.Completed and is_stop_order:
            self.exit_sell_count += 1
            self.stop_fill_price = getattr(order.executed, "price", None)
            self.stop_fill_size = getattr(order.executed, "size", None)


class TurtleLiteStrategyRiskTests(unittest.TestCase):
    def _build_cerebro(self, strategy_cls, cash=10000.0):
        cerebro = bt.Cerebro()
        cerebro.addstrategy(strategy_cls)
        cerebro.broker.setcash(cash)
        cerebro.broker.setcommission(commission=0.0)
        return cerebro

    def _build_data(self, close_prices, gap_index=None, gap_open=None, exit_index=None, exit_low=None):
        closes = list(close_prices)
        opens = list(close_prices)
        highs = [price + 0.5 for price in close_prices]
        lows = [price - 0.5 for price in close_prices]

        if gap_index is not None and gap_open is not None:
            opens[gap_index] = gap_open
            highs[gap_index] = max(highs[gap_index], gap_open)
            lows[gap_index] = min(lows[gap_index], gap_open)
            closes[gap_index] = gap_open

        if exit_index is not None and exit_low is not None:
            opens[exit_index] = exit_low
            highs[exit_index] = max(highs[exit_index], exit_low + 0.2)
            lows[exit_index] = exit_low
            closes[exit_index] = exit_low

        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-01", periods=len(closes), freq="D"),
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": 1000,
            }
        ).set_index("datetime")
        return bt.feeds.PandasData(dataname=df)

    def test_entry_uses_exact_position_size_from_signal_and_fill(self):
        close_prices = [100 + i * 0.8 for i in range(250)]
        cerebro = self._build_cerebro(RecordingStrategy)
        cerebro.adddata(self._build_data(close_prices))

        strategies = cerebro.run()
        strategy = strategies[0]

        self.assertTrue(strategy.entry_filled)
        self.assertEqual(strategy.buy_size, 19)

    def test_rejected_entry_does_not_create_stop(self):
        close_prices = [100 + i * 0.05 for i in range(250)]
        cerebro = self._build_cerebro(RecordingStrategy, cash=150.0)
        cerebro.adddata(self._build_data(close_prices))

        strategies = cerebro.run()
        strategy = strategies[0]

        self.assertTrue(strategy.entry_rejected)
        self.assertIsNone(strategy.stop_order)
        self.assertIsNone(strategy.stop_price)

    def test_normal_exit_cancels_stop_before_exit_sell(self):
        close_prices = [100 + i * 0.05 for i in range(250)]
        exit_index = 205
        exit_low = 100.0 - 0.2
        close_prices[exit_index] = exit_low
        cerebro = self._build_cerebro(RecordingStrategy, cash=1000.0)
        cerebro.adddata(self._build_data(close_prices, exit_index=exit_index, exit_low=exit_low))

        strategies = cerebro.run()
        strategy = strategies[0]

        self.assertTrue(strategy.stop_cancel_confirmed)
        self.assertTrue(strategy.exit_sell_count >= 1)

    def test_stop_fill_does_not_trigger_second_sell(self):
        close_prices = [100 + i * 0.05 for i in range(250)]
        gap_index = 200
        gap_open = 99.5
        close_prices[gap_index] = gap_open
        cerebro = self._build_cerebro(RecordingStrategy, cash=1000.0)
        cerebro.adddata(self._build_data(close_prices, gap_index=gap_index, gap_open=gap_open))

        strategies = cerebro.run()
        strategy = strategies[0]

        self.assertEqual(strategy.exit_sell_count, 1)
        self.assertEqual(strategy.stop_fill_price, 255.0)

    def test_gap_through_stop_uses_executable_open_price(self):
        close_prices = [100 + i * 0.05 for i in range(250)]
        gap_index = 200
        gap_open = 99.5
        close_prices[gap_index] = gap_open
        cerebro = self._build_cerebro(RecordingStrategy, cash=1000.0)
        cerebro.adddata(self._build_data(close_prices, gap_index=gap_index, gap_open=gap_open))

        strategies = cerebro.run()
        strategy = strategies[0]

        self.assertEqual(strategy.stop_fill_price, 99.5)
        self.assertEqual(strategy.stop_fill_size, 1)


if __name__ == "__main__":
    unittest.main()
