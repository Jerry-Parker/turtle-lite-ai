import backtrader as bt


class TurtleLiteStrategy(bt.Strategy):
    """Educational, long-only Turtle-style breakout strategy."""

    params = dict(
        breakout_period=20,
        exit_period=10,
        atr_period=14,
        risk_pct=0.005,
        printlog=True,
    )

    def log(self, txt):
        if self.params.printlog:
            dt = self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()} - {txt}")

    def __init__(self):
        self.entry_order = None
        self.stop_order = None
        self.exit_order = None
        self.pending_stop_price = None
        self.pending_exit = False

        # Exclude today's candle from both channel calculations.
        self.highest_20 = bt.ind.Highest(
            self.data.high(-1), period=self.params.breakout_period
        )
        self.lowest_10 = bt.ind.Lowest(
            self.data.low(-1), period=self.params.exit_period
        )
        self.atr = bt.ind.ATR(self.data, period=self.params.atr_period)
        self.sma50 = bt.ind.SMA(self.data.close, period=50)
        self.sma200 = bt.ind.SMA(self.data.close, period=200)

    def _calculate_position_size(self, entry_price, stop_price, account_value, cash):
        if entry_price <= 0 or stop_price <= 0 or stop_price >= entry_price:
            return 0

        risk_per_share = entry_price - stop_price
        risk_budget = account_value * self.params.risk_pct
        risk_sized = int(risk_budget / risk_per_share)
        affordable = int(cash / entry_price)
        return max(0, min(risk_sized, affordable))

    def _place_stop(self, price, size):
        self.stop_order = self.sell(
            exectype=bt.Order.Stop,
            price=price,
            size=size,
        )

    def _submit_channel_exit(self):
        if self.exit_order is None and self.position:
            self.exit_order = self.sell(size=self.position.size)

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order == self.entry_order:
            if order.status == order.Completed:
                fill_price = order.executed.price
                size = abs(int(order.executed.size))
                stop_price = self.pending_stop_price
                self.log(f"BUY EXECUTED | Price: {fill_price:.2f} | Size: {size}")

                # A gap above the signal can make the filled position exceed the
                # risk budget. Reject it rather than claiming the 0.5% limit held.
                allowed_size = self._calculate_position_size(
                    entry_price=fill_price,
                    stop_price=stop_price,
                    account_value=self.broker.getvalue(),
                    cash=self.broker.getcash() + (fill_price * size),
                )
                if allowed_size < size:
                    self.log("ENTRY REJECTED | Fill exceeded the risk budget")
                    self.exit_order = self.sell(size=size)
                else:
                    self._place_stop(stop_price, size)
            elif order.status in (order.Canceled, order.Margin, order.Rejected):
                self.log("ENTRY CANCELED / MARGIN / REJECTED")

            self.entry_order = None
            self.pending_stop_price = None
            return

        if order == self.stop_order:
            if order.status == order.Completed:
                self.log(
                    f"STOP EXECUTED | Price: {order.executed.price:.2f} | "
                    f"Size: {order.executed.size}"
                )
                self.stop_order = None
                self.pending_exit = False
            elif order.status == order.Canceled:
                self.stop_order = None
                if self.pending_exit:
                    self._submit_channel_exit()
            elif order.status in (order.Margin, order.Rejected):
                self.log("STOP MARGIN / REJECTED")
                self.stop_order = None
            return

        if order == self.exit_order:
            if order.status == order.Completed:
                self.log(
                    f"EXIT EXECUTED | Price: {order.executed.price:.2f} | "
                    f"Size: {order.executed.size}"
                )
            elif order.status in (order.Canceled, order.Margin, order.Rejected):
                self.log("EXIT CANCELED / MARGIN / REJECTED")
            self.exit_order = None
            self.pending_exit = False

    def next(self):
        if self.entry_order or self.exit_order or self.pending_exit:
            return

        close = self.data.close[0]

        if self.position:
            if close < self.lowest_10[0]:
                self.log(
                    f"EXIT SIGNAL | Close {close:.2f} below 10-day low "
                    f"{self.lowest_10[0]:.2f}"
                )
                if self.stop_order is not None:
                    self.pending_exit = True
                    self.cancel(self.stop_order)
                else:
                    self._submit_channel_exit()
            return

        trend_ok = close > self.sma200[0] and self.sma50[0] > self.sma200[0]
        breakout_ok = close > self.highest_20[0]
        if not (trend_ok and breakout_ok):
            return

        stop_price = close - (2 * self.atr[0])
        size = self._calculate_position_size(
            entry_price=close,
            stop_price=stop_price,
            account_value=self.broker.getvalue(),
            cash=self.broker.getcash(),
        )
        if size <= 0:
            self.log("ENTRY REJECTED | Position size is zero")
            return

        self.log(
            f"ENTRY SIGNAL | Close: {close:.2f} | "
            f"20-day high: {self.highest_20[0]:.2f} | "
            f"ATR: {self.atr[0]:.2f} | Size: {size}"
        )
        self.pending_stop_price = stop_price
        self.entry_order = self.buy(size=size)
