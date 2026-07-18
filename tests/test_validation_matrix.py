import tempfile
import unittest
from pathlib import Path

from datetime import date

from run_validation import (
    DEFAULT_PERIODS,
    annualized_return,
    benchmark_metrics,
    discover_symbols,
    run_matrix,
    save_results,
)


class ValidationMatrixTests(unittest.TestCase):
    def test_annualized_return_accounts_for_test_length(self):
        result = annualized_return(
            100.0,
            121.0,
            date(2020, 1, 1),
            date(2022, 1, 1),
        )
        self.assertAlmostEqual(result, 10.0, places=1)

    def test_benchmark_reports_return_and_drawdown(self):
        metrics = benchmark_metrics("data/SPY.csv", "2018-01-01", "2018-12-31")
        self.assertIn("benchmark_annualized_return_percent", metrics)
        self.assertGreater(metrics["benchmark_max_drawdown_percent"], 0)

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
