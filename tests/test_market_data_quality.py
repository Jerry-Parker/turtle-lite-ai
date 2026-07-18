import csv
import unittest
from datetime import date
from pathlib import Path


class MarketDataQualityTests(unittest.TestCase):
    def test_all_market_files_have_valid_daily_ohlcv_rows(self):
        files = sorted(Path("data").glob("*.csv"))
        self.assertTrue(files)

        for path in files:
            with self.subTest(symbol=path.stem):
                with path.open(newline="") as file:
                    reader = csv.DictReader(file)
                    self.assertEqual(
                        reader.fieldnames,
                        ["Date", "Open", "High", "Low", "Close", "Volume"],
                    )
                    previous_date = None
                    seen_dates = set()
                    rows = 0
                    for row in reader:
                        current_date = date.fromisoformat(row["Date"])
                        self.assertNotIn(current_date, seen_dates)
                        if previous_date is not None:
                            self.assertGreater(current_date, previous_date)
                        seen_dates.add(current_date)
                        previous_date = current_date

                        open_price = float(row["Open"])
                        high = float(row["High"])
                        low = float(row["Low"])
                        close = float(row["Close"])
                        volume = float(row["Volume"])
                        self.assertGreater(min(open_price, high, low, close), 0)
                        self.assertGreaterEqual(high, max(open_price, low, close))
                        self.assertLessEqual(low, min(open_price, high, close))
                        self.assertGreaterEqual(volume, 0)
                        rows += 1

                    self.assertGreaterEqual(rows, 201)


if __name__ == "__main__":
    unittest.main()
