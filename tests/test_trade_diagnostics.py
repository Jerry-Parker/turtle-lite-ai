import unittest

from run_backtest import build_diagnostic_summary


class TradeDiagnosticTests(unittest.TestCase):
    def test_summary_groups_trades_and_costs(self):
        trades = [
            {
                "exit_date": "2025-01-10",
                "exit_reason": "atr_stop",
                "net_pnl": -12.5,
                "commission": 1.5,
                "estimated_slippage": 2.0,
            },
            {
                "exit_date": "2025-03-10",
                "exit_reason": "channel_exit",
                "net_pnl": 25.0,
                "commission": 2.0,
                "estimated_slippage": 1.0,
            },
        ]

        summary = build_diagnostic_summary(trades, rejected_entries=3)

        self.assertEqual(summary["recorded_trades"], 2)
        self.assertEqual(summary["rejected_entries"], 3)
        self.assertEqual(summary["total_commission"], 3.5)
        self.assertEqual(summary["estimated_slippage"], 3.0)
        self.assertEqual(summary["by_exit_reason"]["atr_stop"]["net_pnl"], -12.5)
        self.assertEqual(summary["by_exit_year"]["2025"]["net_pnl"], 12.5)


if __name__ == "__main__":
    unittest.main()
