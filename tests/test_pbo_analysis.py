import unittest

import numpy as np

from run_pbo_analysis import (
    cscv_pbo,
    minimum_track_record_length,
    relative_rank,
    sharpe_ratio,
    stochastic_dominance,
)


class PboAnalysisTests(unittest.TestCase):
    def test_sharpe_ratio_handles_flat_returns(self):
        self.assertEqual(sharpe_ratio([0, 0, 0]), 0)

    def test_relative_rank_uses_average_rank_for_ties(self):
        self.assertEqual(relative_rank(np.array([1.0, 2.0, 2.0]), 1), 2.5)

    def test_cscv_detects_deliberately_unstable_winner(self):
        first = np.tile([[0.02, -0.01]], (40, 1))
        second = np.tile([[-0.01, 0.02]], (40, 1))
        noise = np.linspace(-0.001, 0.001, 80).reshape(-1, 1)
        matrix = np.vstack([first, second]) + np.hstack([noise, -noise])
        result = cscv_pbo(matrix, blocks=4)
        self.assertGreaterEqual(result["pbo"], 0.5)

    def test_eight_blocks_generate_all_symmetric_combinations(self):
        generator = np.random.default_rng(7)
        matrix = generator.normal(0.001, 0.01, size=(160, 3))
        result = cscv_pbo(matrix, blocks=8)
        self.assertEqual(result["combinations"], 70)

    def test_mintrl_rejects_non_positive_sharpe(self):
        result = minimum_track_record_length([-0.01, 0.0, 0.01, -0.02])
        self.assertFalse(result["passes"])
        self.assertIsNone(result["required_observations"])

    def test_stochastic_dominance_identifies_better_distribution(self):
        result = stochastic_dominance([2, 3, 4], [0, 1, 2])
        self.assertTrue(result["first_order_dominance"])
        self.assertTrue(result["second_order_dominance"])


if __name__ == "__main__":
    unittest.main()
