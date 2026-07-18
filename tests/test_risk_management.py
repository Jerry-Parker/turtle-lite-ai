import unittest

import backtrader as bt
import pandas as pd

from strategies.turtle_lite import TurtleLiteStrategy


class RecordingStrategy(TurtleLiteStrategy):
    params = dict(printlog=False)

    def __init__(self):
        super().__init__()
        self.events = []

    def notify_order(self, order):
        kind = (
            "entry" if order == self.entry_order
            else "stop" if order == self.stop_order
            else "exit" if order == self.exit_order
            else "other"
        )
        self.events.append(
            (kind, order.status, order.executed.price, order.executed.size)
        )
        super().notify_order(order)


class TurtleLiteStrategyRiskTests(unittest.TestCase):
    def _run(self, rows, cash=10000.0):
        frame = pd.DataFrame(rows)
        frame.index = pd.date_range("2024-01-01", periods=len(frame), freq="D")
        cerebro = bt.Cerebro()
        cerebro.addstrategy(RecordingStrategy)
        cerebro.broker.setcash(cash)
        cerebro.broker.setcommission(commission=0.0)
        cerebro.adddata(bt.feeds.PandasData(dataname=frame))
        return cerebro.run()[0]

    def _base_rows(self, count=230):
        rows = []
        for index in range(count):
            close = 100.0 + (index * 0.05)
            if index >= 200:
                close += 1.0
            rows.append(
                {
                    "open": close,
                    "high": close + 0.50,
                    "low": close - 0.50,
                    "close": close,
                    "volume": 1000,
                }
            )
        # Fill the breakout entry at its signal price so these lifecycle tests
        # are not testing the separate adverse-entry-gap rejection path.
        rows[201]["open"] = rows[200]["close"]
        return rows

    def _completed(self, strategy, kind):
        return [
            event for event in strategy.events
            if event[0] == kind and event[1] == bt.Order.Completed
        ]

    def test_position_size_uses_risk_pct_and_stop_distance(self):
        strategy = self._run(self._base_rows())
        entries = self._completed(strategy, "entry")
        self.assertTrue(entries)
        # The one-point daily range gives an ATR near 1.0, so the two-ATR
        # stop risks about $2/share. A $10,000 account has a $50 budget.
        self.assertEqual(abs(int(entries[0][3])), 24)

    def test_zero_sized_entry_creates_no_stop(self):
        strategy = self._run(self._base_rows(), cash=1.0)
        self.assertFalse(self._completed(strategy, "entry"))
        self.assertFalse(self._completed(strategy, "stop"))

    def test_normal_exit_waits_for_stop_cancellation(self):
        rows = self._base_rows()
        # Entry fills around bar 201. Later close below the prior 10-day low,
        # but above the two-ATR stop, to exercise the channel exit path.
        rows[210].update(open=109.50, high=109.70, low=109.40, close=109.50)
        strategy = self._run(rows)
        canceled_stops = [
            event for event in strategy.events
            if event[0] == "stop" and event[1] == bt.Order.Canceled
        ]
        exits = self._completed(strategy, "exit")
        self.assertTrue(canceled_stops)
        self.assertTrue(exits)
        self.assertLess(strategy.events.index(canceled_stops[0]), strategy.events.index(exits[0]))

    def test_stop_fill_does_not_trigger_second_sell(self):
        rows = self._base_rows()
        rows[210].update(open=108.50, high=108.70, low=108.30, close=108.50)
        strategy = self._run(rows)
        stops = self._completed(strategy, "stop")
        exits = self._completed(strategy, "exit")
        self.assertEqual(len(stops), 1)
        self.assertEqual(len(exits), 0)

    def test_gap_through_stop_uses_open_price(self):
        rows = self._base_rows()
        rows[210].update(open=107.00, high=108.00, low=106.50, close=107.50)
        strategy = self._run(rows)
        stops = self._completed(strategy, "stop")
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0][2], 107.00)


if __name__ == "__main__":
    unittest.main()
