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

        # Prior 20-day high, excluding today's candle
        self.highest_20 = bt.ind.Highest(
            self.data.high(-1),
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

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(
                    f"BUY EXECUTED | Price: {order.executed.price:.2f} | "
                    f"Size: {order.executed.size}"
                )
            elif order.issell():
                self.log(
                    f"SELL EXECUTED | Price: {order.executed.price:.2f} | "
                    f"Size: {order.executed.size}"
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("ORDER CANCELED / MARGIN / REJECTED")

        self.order = None

    def next(self):
        if self.order:
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
                self.order = self.sell(size=self.position.size)
            return

        # Entry filters
        trend_ok = close > self.sma200[0] and self.sma50[0] > self.sma200[0]
        breakout_ok = close > self.highest_20[0]

        if trend_ok and breakout_ok:
            stop_price = close - (2 * self.atr[0])
            risk_per_share = close - stop_price

            if risk_per_share <= 0:
                return

            max_risk_dollars = account_value * self.params.risk_pct
            position_size = int(max_risk_dollars / risk_per_share)

            # Make sure we do not buy more than available cash
            max_affordable_size = int(cash / close)
            position_size = min(position_size, max_affordable_size)

            if position_size > 0:
                self.log(
                    f"ENTRY SIGNAL | Close: {close:.2f} | "
                    f"20-day high: {self.highest_20[0]:.2f} | "
                    f"ATR: {self.atr[0]:.2f} | "
                    f"Risk/share: {risk_per_share:.2f} | "
                    f"Size: {position_size}"
                )
                self.order = self.buy(size=position_size)