import tempfile
import unittest
from pathlib import Path

from run_validation import DEFAULT_PERIODS, discover_symbols, run_matrix, save_results


class ValidationMatrixTests(unittest.TestCase):
    def test_discovers_symbols_in_stable_order(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "SPY.csv").touch()
            Path(directory, "aapl.csv").touch()
            Path(directory, "notes.txt").touch()

            self.assertEqual(discover_symbols(directory), ["AAPL", "SPY"])

    def test_runs_every_requested_symbol_and_period(self):
        periods = (("recent", "2018-01-01", None),)
        results = run_matrix("data", periods=periods, symbols=["SPY", "QQQ"])

        self.assertEqual(
            [(item["symbol"], item["period"]) for item in results],
            [("SPY", "recent"), ("QQQ", "recent")],
        )
        for item in results:
            self.assertIn("return_percent", item)
            self.assertIn("max_drawdown_percent", item)
            self.assertIn("profit_factor", item)
            self.assertGreater(item["closed_trades"], 0)

    def test_saves_json_and_csv_reports(self):
        sample = [
            {
                "symbol": "SPY",
                "period": "full_history",
                "start_date": None,
                "end_date": None,
                "return_percent": 1.0,
                "max_drawdown_percent": 2.0,
                "profit_factor": 1.1,
                "sharpe_ratio": None,
                "closed_trades": 3,
                "rejected_entries": 0,
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            json_path, csv_path = save_results(sample, directory)
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertIn('"symbol": "SPY"', json_path.read_text())
            self.assertIn("SPY,full_history", csv_path.read_text())

    def test_default_periods_cover_full_and_split_history(self):
        self.assertEqual(
            DEFAULT_PERIODS,
            (
                ("full_history", None, None),
                ("2005_2017", "2005-01-01", "2017-12-31"),
                ("2018_onward", "2018-01-01", None),
            ),
        )


if __name__ == "__main__":
    unittest.main()
