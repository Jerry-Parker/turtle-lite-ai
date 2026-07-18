import unittest

from run_reliability_tests import (
    longest_losing_streak,
    monte_carlo_trade_order,
    percentile,
    sequence_drawdown_percent,
)


class ReliabilityTestUtilities(unittest.TestCase):
    def test_longest_losing_streak(self):
        self.assertEqual(longest_losing_streak([10, -2, -3, 4, -1]), 2)

    def test_sequence_drawdown(self):
        self.assertAlmostEqual(
            sequence_drawdown_percent([100, -50, -100], starting_cash=1000),
            (150 / 1100) * 100,
        )

    def test_percentile_is_deterministic(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], 0.95), 5)

    def test_monte_carlo_report_is_reproducible(self):
        first = monte_carlo_trade_order([10, -5, -8, 20], simulations=20, seed=7)
        second = monte_carlo_trade_order([10, -5, -8, 20], simulations=20, seed=7)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
