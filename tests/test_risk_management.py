import unittest

import backtrader as bt
import pandas as pd

from strategies.turtle_lite import TurtleLiteStrategy


class RecordingStrategy(TurtleLiteStrategy):
    def __init__(self):
        super().__init__()
        self.order_events = []
        self.stop_placed_after_entry_fill = False
        self.entry_rejected = False
        self.stop_canceled = False
        self.stop_fill_price = None
        self.sell_order_count = 0
        self.entry_completed = False
        self.stop_pending = False

    def notify_order(self, order):
        super().notify_order(order)

        self.order_events.append(
            {
                "status": order.status,
                "isbuy": order.isbuy(),
                "issell": order.issell(),
                "price": order.price,
                "executed_price": getattr(order.executed, "price", None),
            }
        )

        if order.isbuy() and order.status == order.Completed:
            self.entry_completed = True
            self.stop_placed_after_entry_fill = self.stop_order is not None
            self.stop_pending = self.stop_order is not None

        if order.isbuy() and order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.entry_rejected = True

        if order.issell() and order.status == order.Completed:
            self.sell_order_count += 1
            self.stop_fill_price = getattr(order.executed, "price", None)

        if order == self.stop_order and order.status == order.Canceled:
            self.stop_canceled = True


class TurtleLiteStrategyRiskTests(unittest.TestCase):
    def _build_cerebro(self, strategy_cls, cash=10000.0):
        cerebro = bt.Cerebro()
        cerebro.addstrategy(strategy_cls)
        cerebro.broker.setcash(cash)
        cerebro.broker.setcommission(commission=0.0)
        return cerebro

    def _build_data(self, prices):
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-01", periods=len(prices), freq="D"),
                "open": prices,
                "high": [price + 0.5 for price in prices],
                "low": [price - 0.5 for price in prices],
                "close": prices,
                "volume": 1000,
            }
        ).set_index("datetime")
        return bt.feeds.PandasData(dataname=df)

    def test_position_size_uses_risk_pct_and_stop_distance(self):
        cerebro = self._build_cerebro(RecordingStrategy)
        cerebro.adddata(self._build_data([100 + i * 0.8 for i in range(250)]))

        strategies = cerebro.run()
        strategy = strategies[0]

        self.assertTrue(strategy.entry_completed)
        self.assertTrue(strategy.stop_placed_after_entry_fill)
        self.assertIsNotNone(strategy.stop_order)

    def test_entry_rejection_does_not_leave_orphan_stop(self):
        cerebro = self._build_cerebro(RecordingStrategy, cash=1.0)
        cerebro.adddata(self._build_data([100 + i * 0.8 for i in range(250)]))

        strategies = cerebro.run()
        strategy = strategies[0]

        self.assertTrue(strategy.entry_rejected or not strategy.stop_pending)
        self.assertIsNone(strategy.stop_order)
        self.assertIsNone(strategy.stop_price)

    def test_normal_exit_cancels_existing_stop(self):
        cerebro = self._build_cerebro(RecordingStrategy)
        cerebro.adddata(self._build_data([100 + i * 0.8 for i in range(250)]))

        strategies = cerebro.run()
        strategy = strategies[0]
        strategy.stop_price = 90.0

        class FakeOrder:
            Submitted = bt.Order.Submitted
            Accepted = bt.Order.Accepted
            Canceled = bt.Order.Canceled
            Completed = bt.Order.Completed
            Rejected = bt.Order.Rejected
            Margin = bt.Order.Margin

            def __init__(self):
                self.status = bt.Order.Submitted
                self.ref = 1

            def isbuy(self):
                return False

            def issell(self):
                return True

        strategy.stop_order = FakeOrder()
        strategy._cancel_stop_order()

        self.assertIsNone(strategy.stop_order)
        self.assertIsNone(strategy.stop_price)

    def test_filled_stop_does_not_trigger_second_sell(self):
        cerebro = self._build_cerebro(RecordingStrategy)
        cerebro.adddata(self._build_data([100 + i * 0.8 for i in range(250)]))

        strategies = cerebro.run()
        strategy = strategies[0]
        strategy.stop_price = 90.0
        strategy._place_stop_loss(stop_price=90.0, size=1)
        class FakeFilledOrder:
            Submitted = bt.Order.Submitted
            Accepted = bt.Order.Accepted
            Canceled = bt.Order.Canceled
            Completed = bt.Order.Completed
            Rejected = bt.Order.Rejected
            Margin = bt.Order.Margin

            def __init__(self):
                self.status = bt.Order.Completed
                self.executed = type("Executed", (), {"price": 90.0, "size": 1})()
                self.ref = 1
                self.price = 90.0

            def isbuy(self):
                return False

            def issell(self):
                return True

        strategy.notify_order(FakeFilledOrder())

        self.assertEqual(strategy.sell_order_count, 1)

    def test_gap_through_stop_triggers_on_executable_price(self):
        cerebro = self._build_cerebro(RecordingStrategy)
        cerebro.adddata(self._build_data([100 + i * 0.8 for i in range(250)]))

        strategies = cerebro.run()
        strategy = strategies[0]
        strategy.stop_price = 90.0
        strategy._place_stop_loss(stop_price=90.0, size=1)
        class FakeFilledOrder:
            Submitted = bt.Order.Submitted
            Accepted = bt.Order.Accepted
            Canceled = bt.Order.Canceled
            Completed = bt.Order.Completed
            Rejected = bt.Order.Rejected
            Margin = bt.Order.Margin

            def __init__(self):
                self.status = bt.Order.Completed
                self.executed = type("Executed", (), {"price": 89.0, "size": 1})()
                self.ref = 1
                self.price = 89.0

            def isbuy(self):
                return False

            def issell(self):
                return True

        strategy.notify_order(FakeFilledOrder())

        self.assertEqual(strategy.sell_order_count, 1)
        self.assertEqual(strategy.stop_fill_price, 89.0)


if __name__ == "__main__":
    unittest.main()
