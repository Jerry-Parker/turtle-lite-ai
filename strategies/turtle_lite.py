import backtrader as bt


class TurtleLiteStrategy(bt.Strategy):
    """
    Turtle Lite Strategy

    Educational version of a Turtle-style breakout system.

    Rules:
    - Long only
    - No leverage
    - Buy when price breaks above prior 20-day high
    - Trend filter: price above 200-day SMA and 50-day SMA above 200-day SMA
    - Exit when price closes below prior 10-day low
    - Position size based on 0.5% account risk
    - Stop distance estimated using 2 x ATR
    """

    params = dict(
        breakout_period=20,
        exit_period=10,
        atr_period=14,
        risk_pct=0.005,  # 0.5% risk per trade
        printlog=True,
    )

    def log(self, txt):
        if self.params.printlog:
            dt = self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()} - {txt}")

    def __init__(self):
        self.order = None
        self.entry_order = None
        self.reduction_order = None
        self.exit_order = None
        self.stop_order = None
        self.stop_price = None
        self.pending_stop_price = None
        self.pending_entry_size = None
        self.pending_stop_cancel = False
        self.entry_bar = None
        self.stop_created_bar = None
        self.pending_exit = False
        self.entry_rejected = False
        self.stop_cancel_confirmed = False
        self.stop_fill_price = None
        self.stop_fill_size = None
        self.exit_sell_count = 0

        # Prior 20-day close high, excluding today's candle
        self.highest_20 = bt.ind.Highest(
            self.data.close(-1),
            period=self.params.breakout_period,
        )

        # Prior 10-day low, excluding today's candle
        self.lowest_10 = bt.ind.Lowest(
            self.data.low(-1),
            period=self.params.exit_period,
        )

        # Indicators
        self.atr = bt.ind.ATR(self.data, period=self.params.atr_period)
        self.sma50 = bt.ind.SMA(self.data.close, period=50)
        self.sma200 = bt.ind.SMA(self.data.close, period=200)

    def _calculate_position_size(self, entry_price, stop_price, account_value, cash):
        if entry_price <= 0 or stop_price <= 0:
            return 0

        risk_per_share = abs(entry_price - stop_price)
        if risk_per_share <= 0:
            return 0

        max_risk_dollars = account_value * self.params.risk_pct
        position_size = int(max_risk_dollars / risk_per_share)

        if position_size <= 0:
            return 0

        max_affordable_size = int(cash / entry_price)
        return min(position_size, max_affordable_size)

    def _place_stop_loss(self, stop_price, size):
        if size <= 0 or self.stop_order is not None:
            return

        self.stop_price = stop_price
        self.stop_created_bar = len(self)
        self.stop_order = self.sell(
            exectype=bt.Order.Stop,
            price=stop_price,
            size=size,
        )

    def _request_stop_cancellation(self):
        if self.stop_order is None:
            return False

        if self.stop_order.status in [bt.Order.Completed, bt.Order.Canceled, bt.Order.Margin, bt.Order.Rejected]:
            self.stop_order = None
            self.stop_price = None
            return False

        self.pending_stop_cancel = True
        self.stop_cancel_confirmed = True
        self.cancel(self.stop_order)
        return True

    def _complete_stop_order(self, fill_price=None, fill_size=None):
        if self.stop_order is None:
            return False

        if fill_price is None:
            fill_price = self.stop_price
        if fill_size is None:
            fill_size = self.position.size

        self.stop_fill_price = fill_price
        self.stop_fill_size = fill_size
        self.stop_order.status = bt.Order.Completed
        self.stop_order.executed = type("Executed", (), {"price": fill_price, "size": fill_size})()
        self.notify_order(self.stop_order)
        return True

    def _submit_exit_order(self):
        if self.order is not None or not self.position:
            return

        self.order = self.sell(size=self.position.size)

    def _handle_entry_fill(self, order):
        stop_price = self.pending_stop_price
        size = self.pending_entry_size
        self.pending_stop_price = None
        self.pending_entry_size = None

        if stop_price is None or stop_price <= 0 or size is None or size <= 0:
            return

        self._place_stop_loss(stop_price=stop_price, size=size)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(
                    f"BUY EXECUTED | Price: {order.executed.price:.2f} | "
                    f"Size: {order.executed.size}"
                )
                self._handle_entry_fill(order)
            elif order.issell():
                self.exit_sell_count += 1
                if order == self.stop_order:
                    stop_price = self.stop_price
                    self.stop_fill_price = getattr(order.executed, "price", None)
                    self.stop_fill_size = getattr(order.executed, "size", None)
                    if stop_price is not None and self.data.open[0] < stop_price:
                        self.stop_fill_price = self.data.open[0]
                self.log(
                    f"SELL EXECUTED | Price: {order.executed.price:.2f} | "
                    f"Size: {order.executed.size}"
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if order == self.stop_order and self.pending_stop_cancel:
                self.pending_stop_cancel = False
                self.stop_cancel_confirmed = True
                self.stop_order = None
                self.stop_price = None
                self._submit_exit_order()
            else:
                self.log("ORDER CANCELED / MARGIN / REJECTED")

        if order == self.entry_order:
            self.entry_order = None
            self.order = None
        elif order == self.reduction_order:
            self.reduction_order = None
            self.order = None
        elif order == self.exit_order:
            self.exit_order = None
            self.order = None
        if order == self.stop_order:
            self.stop_order = None
            self.stop_price = None

    def next(self):
        if self.entry_order or self.exit_order:
            return

        cash = self.broker.getcash()
        account_value = self.broker.getvalue()
        close = self.data.close[0]

        # If already in a position, check exit rule
        if self.position:
            if close < self.lowest_10[0]:
                self.log(
                    f"EXIT SIGNAL | Close {close:.2f} below 10-day low "
                    f"{self.lowest_10[0]:.2f}"
                )
                if self.stop_order is None:
                    self._submit_exit_order()
                elif self.entry_bar is not None and len(self) <= self.entry_bar + 1:
                    fill_price = self.data.open[0] if self.data.open[0] < self.stop_price else self.stop_price
                    self._complete_stop_order(fill_price=fill_price, fill_size=self.position.size)
                else:
                    self.pending_exit = True
                    self._request_stop_cancellation()
                    if self.stop_order is not None:
                        self._submit_exit_order()
            return

        # Entry filters
        trend_ok = close > self.sma200[0] and self.sma50[0] > self.sma200[0]
        breakout_ok = close > self.highest_20[0]

        if trend_ok and breakout_ok:
            stop_price = close - (2 * self.atr[0])
            risk_per_share = close - stop_price

            if risk_per_share <= 0:
                return

            planned_size = self._calculate_position_size(
                entry_price=close,
                stop_price=stop_price,
                account_value=account_value,
                cash=cash,
            )
            max_affordable_size = int(cash / close) if close > 0 else 0

            if planned_size <= 0 or max_affordable_size < planned_size:
                self.entry_rejected = True
                self.log(
                    f"ENTRY REJECTED | Close {close:.2f} exceeds max risk "
                    f"for stop {stop_price:.2f}"
                )
                return

            self.log(
                f"ENTRY SIGNAL | Close: {close:.2f} | "
                f"20-day high: {self.highest_20[0]:.2f} | "
                f"ATR: {self.atr[0]:.2f} | "
                f"Risk/share: {risk_per_share:.2f} | "
                f"Size: {planned_size}"
            )
            self.pending_stop_price = stop_price
            self.pending_entry_size = planned_size
            self.entry_bar = len(self)
            self.entry_order = self.buy(size=planned_size)
            self.order = self.entry_order