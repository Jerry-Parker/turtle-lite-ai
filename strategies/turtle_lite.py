import backtrader as bt
from datetime import date


class TurtleLiteStrategy(bt.Strategy):
    """Educational, long-only Turtle-style breakout strategy."""

    params = dict(
        breakout_period=20,
        exit_period=10,
        atr_period=14,
        risk_pct=0.005,
        entry_buffer_atr=0.5,
        initial_stop_atr=2.0,
        use_trailing=False,
        trailing_activation_r=2.0,
        trailing_stop_atr=2.5,
        printlog=True,
    )

    def log(self, txt):
        if self.params.printlog:
            dt = self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()} - {txt}")

    def __init__(self):
        self.entry_order = None
        self.entry_order_bar = None
        self.stop_order = None
        self.exit_order = None
        self.pending_stop_price = None
        self.pending_exit = False
        self.pending_exit_reason = None
        self.pending_exit_signal_price = None
        self.entry_signal_date = None
        self.entry_signal_price = None
        self.active_trade = None
        self.entry_bar = None
        self.highest_since_entry = None
        self.initial_risk_per_share = None
        self.active_stop_price = None
        self.replacement_stop_price = None
        self.trailing_active = False
        self.trade_diagnostics = []
        self.rejected_entries = 0

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
        self.active_stop_price = price
        self.stop_order = self.sell(
            exectype=bt.Order.Stop,
            price=price,
            size=size,
        )

    def _reset_position_state(self):
        self.entry_bar = None
        self.highest_since_entry = None
        self.initial_risk_per_share = None
        self.active_stop_price = None
        self.replacement_stop_price = None
        self.trailing_active = False

    def _request_stop_replacement(self, price):
        """Cancel the live stop before submitting its higher replacement."""
        if self.stop_order is None or not self.position:
            return
        self.replacement_stop_price = price
        self.cancel(self.stop_order)

    def _submit_channel_exit(self):
        if self.exit_order is None and self.position:
            self.exit_order = self.sell(size=self.position.size)

    @staticmethod
    def _execution_date(order):
        if order.executed.dt:
            return bt.num2date(order.executed.dt).date().isoformat()
        return date.today().isoformat()

    def _finalize_trade(self, order, reason, expected_exit_price):
        if self.active_trade is None:
            return

        trade = self.active_trade
        exit_price = order.executed.price
        size = trade["size"]
        exit_commission = order.executed.comm
        entry_date = date.fromisoformat(trade["entry_date"])
        exit_date = date.fromisoformat(self._execution_date(order))
        gross_pnl = (exit_price - trade["entry_price"]) * size
        commission = trade["entry_commission"] + exit_commission
        entry_slippage = (trade["entry_price"] - trade["entry_signal_price"]) * size
        exit_slippage = (expected_exit_price - exit_price) * size

        trade.update(
            exit_date=exit_date.isoformat(),
            exit_price=round(exit_price, 6),
            exit_reason=reason,
            holding_days=(exit_date - entry_date).days,
            gross_pnl=round(gross_pnl, 2),
            commission=round(commission, 2),
            estimated_slippage=round(entry_slippage + exit_slippage, 2),
            net_pnl=round(gross_pnl - commission, 2),
        )
        self.trade_diagnostics.append(trade)
        self.active_trade = None
        self._reset_position_state()

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order == self.entry_order:
            if order.status == order.Completed:
                fill_price = order.executed.price
                size = abs(int(order.executed.size))
                stop_price = self.pending_stop_price
                self.log(f"BUY EXECUTED | Price: {fill_price:.2f} | Size: {size}")

                self.active_trade = {
                    "entry_date": self._execution_date(order),
                    "entry_signal_date": self.entry_signal_date,
                    "entry_signal_price": round(self.entry_signal_price, 6),
                    "entry_price": round(fill_price, 6),
                    "size": size,
                    "stop_price": round(stop_price, 6),
                    "entry_commission": order.executed.comm,
                    "initial_risk_per_share": round(fill_price - stop_price, 6),
                    "trailing_activated": False,
                }

                self.entry_bar = len(self)
                self.highest_since_entry = fill_price
                self.initial_risk_per_share = fill_price - stop_price
                self.trailing_active = False
                self.replacement_stop_price = None

                self._place_stop(stop_price, size)
            elif order.status in (
                order.Canceled,
                order.Expired,
                order.Margin,
                order.Rejected,
            ):
                self.rejected_entries += 1
                self.log("ENTRY NOT FILLED WITHIN RISK LIMIT")

            self.entry_order = None
            self.entry_order_bar = None
            self.pending_stop_price = None
            self.entry_signal_date = None
            self.entry_signal_price = None
            return

        if order == self.stop_order:
            if order.status == order.Completed:
                expected_exit_price = self.active_stop_price
                reason = "trailing_stop" if self.trailing_active else "atr_stop"
                self._finalize_trade(order, reason, expected_exit_price)
                self.log(
                    f"STOP EXECUTED | Price: {order.executed.price:.2f} | "
                    f"Size: {order.executed.size}"
                )
                self.stop_order = None
                self.pending_exit = False
                self.replacement_stop_price = None
            elif order.status == order.Canceled:
                self.stop_order = None
                if self.pending_exit:
                    self._submit_channel_exit()
                elif self.replacement_stop_price is not None and self.position:
                    replacement = self.replacement_stop_price
                    self.replacement_stop_price = None
                    self._place_stop(replacement, self.position.size)
            elif order.status in (order.Expired, order.Margin, order.Rejected):
                self.log("STOP MARGIN / REJECTED")
                self.stop_order = None
                self.replacement_stop_price = None
                # Never knowingly leave an open trade without protection.
                if self.position:
                    self.pending_exit = True
                    self.pending_exit_reason = "risk_stop_rejected"
                    self.pending_exit_signal_price = self.data.close[0]
                    self._submit_channel_exit()
            return

        if order == self.exit_order:
            if order.status == order.Completed:
                reason = self.pending_exit_reason or "channel_exit"
                expected_exit_price = self.pending_exit_signal_price or order.executed.price
                self._finalize_trade(order, reason, expected_exit_price)
                self.log(
                    f"EXIT EXECUTED | Price: {order.executed.price:.2f} | "
                    f"Size: {order.executed.size}"
                )
            elif order.status in (order.Canceled, order.Margin, order.Rejected):
                self.log("EXIT CANCELED / MARGIN / REJECTED")
            self.exit_order = None
            self.pending_exit = False
            self.pending_exit_reason = None
            self.pending_exit_signal_price = None

    def next(self):
        if self.entry_order:
            # Give the capped entry order one trading session to fill.
            if len(self) > self.entry_order_bar:
                self.cancel(self.entry_order)
            return

        if self.exit_order or self.pending_exit:
            return

        close = self.data.close[0]

        if self.position:
            self.highest_since_entry = max(
                self.highest_since_entry, float(self.data.high[0])
            )
            if close < self.lowest_10[0]:
                self.log(
                    f"EXIT SIGNAL | Close {close:.2f} below 10-day low "
                    f"{self.lowest_10[0]:.2f}"
                )
                if self.stop_order is not None:
                    self.pending_exit = True
                    self.pending_exit_reason = "channel_exit"
                    self.pending_exit_signal_price = close
                    self.replacement_stop_price = None
                    self.cancel(self.stop_order)
                else:
                    self.pending_exit_reason = "channel_exit"
                    self.pending_exit_signal_price = close
                    self._submit_channel_exit()
                return

            if (
                self.params.use_trailing
                and self.stop_order is not None
                and len(self) > self.entry_bar
            ):
                activation_price = (
                    self.active_trade["entry_price"]
                    + self.params.trailing_activation_r * self.initial_risk_per_share
                )
                if self.highest_since_entry >= activation_price:
                    self.trailing_active = True
                    self.active_trade["trailing_activated"] = True
                    candidate = (
                        self.highest_since_entry
                        - self.params.trailing_stop_atr * float(self.atr[0])
                    )
                    # A trail can tighten protection, but can never loosen it.
                    ratcheted_price = max(self.active_stop_price, candidate)
                    if ratcheted_price > self.active_stop_price:
                        self.active_trade["stop_price"] = round(ratcheted_price, 6)
                        self._request_stop_replacement(ratcheted_price)
            return

        trend_ok = close > self.sma200[0] and self.sma50[0] > self.sma200[0]
        breakout_ok = close > self.highest_20[0]
        if not (trend_ok and breakout_ok):
            return

        stop_price = close - (self.params.initial_stop_atr * self.atr[0])
        max_entry_price = close + (self.params.entry_buffer_atr * self.atr[0])
        size = self._calculate_position_size(
            entry_price=max_entry_price,
            stop_price=stop_price,
            account_value=self.broker.getvalue(),
            cash=self.broker.getcash(),
        )
        if size <= 0:
            self.rejected_entries += 1
            self.log("ENTRY REJECTED | Position size is zero")
            return

        self.log(
            f"ENTRY SIGNAL | Close: {close:.2f} | "
            f"20-day high: {self.highest_20[0]:.2f} | "
            f"ATR: {self.atr[0]:.2f} | Max fill: {max_entry_price:.2f} | "
            f"Size: {size}"
        )
        self.pending_stop_price = stop_price
        self.entry_signal_date = self.datas[0].datetime.date(0).isoformat()
        self.entry_signal_price = close
        self.entry_order = self.buy(
            exectype=bt.Order.Limit,
            price=max_entry_price,
            size=size,
        )
        self.entry_order_bar = len(self)
