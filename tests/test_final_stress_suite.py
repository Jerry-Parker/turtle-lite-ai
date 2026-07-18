import unittest

import numpy as np
import pandas as pd

from run_final_stress_suite import choose_start_dates, conditional_metrics, percentile_summary


class FinalStressSuiteTests(unittest.TestCase):
    def test_start_date_sampling_is_reproducible_and_leaves_two_years(self):
        dates = list(pd.date_range("2020-04-10", "2026-07-17", freq="D"))
        first = choose_start_dates(dates, count=10)
        second = choose_start_dates(dates, count=10)
        self.assertEqual(first, second)
        self.assertEqual(len(set(first)), 10)
        self.assertLessEqual(max(first), dates[-1] - pd.Timedelta(days=730))

    def test_conditional_metrics_use_only_selected_observations(self):
        returns = pd.Series([0.0, 0.10, -0.05, 0.20])
        mask = pd.Series([False, True, True, False])
        result = conditional_metrics(returns, mask, periods_per_year=2)
        self.assertEqual(result["observations"], 2)
        self.assertEqual(result["percent_of_days"], 50.0)
        self.assertGreater(result["max_drawdown_percent"], 0)

    def test_percentile_summary_is_order_independent(self):
        self.assertEqual(percentile_summary([3, 1, 2]), percentile_summary(np.array([1, 2, 3])))


if __name__ == "__main__":
    unittest.main()
