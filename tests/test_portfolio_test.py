import unittest
import tempfile
from pathlib import Path

from run_portfolio_test import (
    PORTFOLIO_RISK_CAP,
    RISK_PER_TRADE,
    calculate_position_size,
    run_portfolio,
    save_report,
)


class PortfolioTestTests(unittest.TestCase):
    def test_report_separates_summary_from_daily_curve(self):
        report = {
            "portfolio": ["SPY"],
            "equity_curve": [{"date": "2025-01-01", "value": 100_000}],
            "benchmark_curve": [100_000],
            "marked_open_risk_curve_percent": [0.0],
            "capital_invested_curve_percent": [0.0],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            curve_path = save_report(report, output)
            self.assertNotIn("equity_curve", output.read_text())
            self.assertIn("portfolio_value", curve_path.read_text())

    def test_position_size_obeys_risk_and_cash(self):
        self.assertEqual(
            calculate_position_size(100, 95, risk_budget=500, cash=100_000),
            100,
        )
        self.assertEqual(
            calculate_position_size(100, 95, risk_budget=500, cash=250),
            2,
        )

    def test_declared_portfolio_risk_exceeds_one_trade_but_remains_conservative(self):
        self.assertEqual(RISK_PER_TRADE, 0.005)
        self.assertEqual(PORTFOLIO_RISK_CAP, 0.02)

    def test_shared_portfolio_never_exceeds_risk_cap(self):
        report = run_portfolio(
            ["SPY", "QQQ"],
            start_date="2020-01-01",
            end_date="2021-12-31",
            portfolio_risk_cap=0.01,
        )
        self.assertLessEqual(report["maximum_allocated_entry_risk_percent"], 1.0001)
        self.assertEqual(report["locked_parameters"]["breakout_period"], 20)
        self.assertEqual(report["locked_parameters"]["initial_stop_atr"], 2.0)


if __name__ == "__main__":
    unittest.main()
