"""Read-only Bybit monitor for the locked Turtle baseline.

This module deliberately supports public GET requests only. It has no API-key,
authentication, order-placement, amendment, or cancellation capability.
"""

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd


# Bybit documents both hosts as official mainnet endpoints. GitHub-hosted
# runners are commonly rejected by api.bybit.com because their IPs are in the
# US, so the scheduled observation uses the alternate official host.
BYBIT_PUBLIC_URL = "https://api.bytick.com"
ALLOWED_PUBLIC_PATHS = frozenset({"/v5/market/kline", "/v5/market/instruments-info"})
RISK_PCT = 0.005
INITIAL_STOP_ATR = 2.0
ENTRY_BUFFER_ATR = 0.5


class BybitPublicClient:
    """Minimal public-market-data client with an explicit read-only allowlist."""

    def __init__(self, base_url=BYBIT_PUBLIC_URL, timeout=15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path, parameters):
        if path not in ALLOWED_PUBLIC_PATHS:
            raise ValueError(f"Non-public or unsupported Bybit path: {path}")
        url = f"{self.base_url}{path}?{urlencode(parameters)}"
        with urlopen(url, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit public API error: {payload.get('retMsg', 'unknown error')}")
        return payload["result"]

    def daily_candles(self, symbol, category="linear", limit=1000):
        result = self._get(
            "/v5/market/kline",
            {"category": category, "symbol": symbol.upper(), "interval": "D", "limit": limit},
        )
        return candles_to_frame(result["list"])

    def instrument(self, symbol, category="linear"):
        result = self._get(
            "/v5/market/instruments-info",
            {"category": category, "symbol": symbol.upper()},
        )
        if not result["list"]:
            raise ValueError(f"Unknown Bybit instrument: {symbol}")
        item = result["list"][0]
        lot = item["lotSizeFilter"]
        return {
            "symbol": item["symbol"],
            "status": item["status"],
            "qty_step": lot["qtyStep"],
            "minimum_qty": lot["minOrderQty"],
            "minimum_notional": lot.get("minNotionalValue", "0"),
            "tick_size": item["priceFilter"]["tickSize"],
        }


def candles_to_frame(candles, now=None):
    """Convert reverse-ordered Bybit candles and remove the open daily bar."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for candle in candles:
        opened = datetime.fromtimestamp(int(candle[0]) / 1000, tz=timezone.utc)
        if opened.date() >= now.date():
            continue
        rows.append(
            {
                "Date": pd.Timestamp(opened.date()),
                "Open": float(candle[1]),
                "High": float(candle[2]),
                "Low": float(candle[3]),
                "Close": float(candle[4]),
                "Volume": float(candle[5]),
            }
        )
    if not rows:
        raise ValueError("Bybit returned no completed daily candles.")
    return pd.DataFrame(rows).drop_duplicates("Date").set_index("Date").sort_index()


def add_locked_indicators(frame):
    frame = frame.copy()
    previous_close = frame["Close"].shift(1)
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["atr"] = true_range.ewm(alpha=1 / 14, adjust=False).mean()
    frame["breakout_high"] = frame["High"].shift(1).rolling(20).max()
    frame["exit_low"] = frame["Low"].shift(1).rolling(10).min()
    frame["sma50"] = frame["Close"].rolling(50).mean()
    frame["sma200"] = frame["Close"].rolling(200).mean()
    return frame


def round_down(value, step):
    value = Decimal(str(value))
    step = Decimal(str(step))
    if step <= 0:
        raise ValueError("Quantity step must be positive.")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def evaluate_locked_signal(frame, instrument, paper_equity):
    """Evaluate only the existing locked entry rules on the last closed bar."""
    if paper_equity <= 0:
        raise ValueError("Paper equity must be positive.")
    enriched = add_locked_indicators(frame)
    if len(enriched) < 200:
        raise ValueError("At least 200 completed daily candles are required.")
    row = enriched.iloc[-1]
    required = [row["atr"], row["breakout_high"], row["exit_low"], row["sma50"], row["sma200"]]
    if any(pd.isna(value) for value in required):
        raise ValueError("The latest candle does not have complete indicators.")

    trend_ok = bool(row["Close"] > row["sma200"] and row["sma50"] > row["sma200"])
    breakout_ok = bool(row["Close"] > row["breakout_high"])
    stop_price = float(row["Close"] - INITIAL_STOP_ATR * row["atr"])
    maximum_entry = float(row["Close"] + ENTRY_BUFFER_ATR * row["atr"])
    risk_budget = paper_equity * RISK_PCT
    risk_per_unit = maximum_entry - stop_price
    raw_size = min(risk_budget / risk_per_unit, paper_equity / maximum_entry)
    size = round_down(raw_size, instrument["qty_step"])
    minimum_qty = Decimal(str(instrument["minimum_qty"]))
    minimum_notional = Decimal(str(instrument["minimum_notional"]))
    valid_size = size >= minimum_qty and size * Decimal(str(maximum_entry)) >= minimum_notional
    signal = trend_ok and breakout_ok and valid_size and instrument["status"] == "Trading"
    date_text = enriched.index[-1].date().isoformat()
    identity = f"{instrument['symbol']}:{date_text}:locked-turtle-entry"
    return {
        "event_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
        "mode": "READ_ONLY_HYPOTHETICAL",
        "symbol": instrument["symbol"],
        "candle_date": date_text,
        "signal": "HYPOTHETICAL_ENTRY" if signal else "NO_ENTRY",
        "close": round(float(row["Close"]), 8),
        "atr": round(float(row["atr"]), 8),
        "prior_20_day_high": round(float(row["breakout_high"]), 8),
        "prior_10_day_low": round(float(row["exit_low"]), 8),
        "sma50": round(float(row["sma50"]), 8),
        "sma200": round(float(row["sma200"]), 8),
        "trend_filter_passed": trend_ok,
        "breakout_passed": breakout_ok,
        "paper_equity": paper_equity,
        "risk_percent": RISK_PCT * 100,
        "risk_budget": round(risk_budget, 2),
        "hypothetical_maximum_entry": round(maximum_entry, 8),
        "hypothetical_initial_stop": round(stop_price, 8),
        "hypothetical_quantity": format(size, "f"),
        "instrument_rules_passed": valid_size and instrument["status"] == "Trading",
        "orders_submitted": 0,
    }


def append_once(event, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = set()
    if output_path.exists():
        for line in output_path.read_text().splitlines():
            if line.strip():
                existing_ids.add(json.loads(line)["event_id"])
    if event["event_id"] in existing_ids:
        return False
    with output_path.open("a") as file:
        file.write(json.dumps(event, sort_keys=True) + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SOLUSDT")
    parser.add_argument("--category", choices=("spot", "linear", "inverse"), default="linear")
    parser.add_argument("--paper-equity", type=float, default=100_000)
    parser.add_argument("--output", default="logs/bybit_read_only_signals.jsonl")
    args = parser.parse_args()

    client = BybitPublicClient()
    instrument = client.instrument(args.symbol, args.category)
    candles = client.daily_candles(args.symbol, args.category)
    event = evaluate_locked_signal(candles, instrument, args.paper_equity)
    saved = append_once(event, args.output)
    print(json.dumps(event, indent=2))
    print(f"Saved: {saved} | Log: {args.output} | Orders submitted: 0")


if __name__ == "__main__":
    main()
