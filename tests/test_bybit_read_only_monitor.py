import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from bybit_read_only_monitor import (
    BybitPublicClient, append_once, candles_to_frame, evaluate_locked_signal,
)


class BybitReadOnlyMonitorTests(unittest.TestCase):
    def test_client_rejects_any_non_public_path(self):
        client = BybitPublicClient()
        with self.assertRaises(ValueError):
            client._get("/v5/order/create", {})

    def test_current_unclosed_daily_candle_is_removed(self):
        now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
        candles = [
            ["1784332800000", "100", "101", "99", "100", "10", "1000"],
            ["1784246400000", "99", "101", "98", "100", "12", "1200"],
        ]
        frame = candles_to_frame(candles, now=now)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.index[-1].date().isoformat(), "2026-07-17")

    def test_locked_signal_keeps_half_percent_risk(self):
        rows = []
        for index in range(230):
            close = 100 + index * 0.1
            rows.append({
                "Open": close, "High": close + 0.5, "Low": close - 0.5,
                "Close": close, "Volume": 1000,
            })
        rows[-1]["Close"] += 3
        rows[-1]["High"] = rows[-1]["Close"] + 0.5
        frame = pd.DataFrame(rows, index=pd.date_range("2025-01-01", periods=230))
        instrument = {
            "symbol": "SOLUSDT", "status": "Trading", "qty_step": "0.1",
            "minimum_qty": "0.1", "minimum_notional": "5", "tick_size": "0.001",
        }
        event = evaluate_locked_signal(frame, instrument, 100_000)
        self.assertEqual(event["signal"], "HYPOTHETICAL_ENTRY")
        self.assertEqual(event["risk_percent"], 0.5)
        self.assertEqual(event["risk_budget"], 500.0)
        self.assertEqual(event["orders_submitted"], 0)

    def test_event_log_is_idempotent(self):
        event = {"event_id": "same", "orders_submitted": 0}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            self.assertTrue(append_once(event, path))
            self.assertFalse(append_once(event, path))
            self.assertEqual(len(path.read_text().splitlines()), 1)
            self.assertEqual(json.loads(path.read_text())["event_id"], "same")


if __name__ == "__main__":
    unittest.main()
