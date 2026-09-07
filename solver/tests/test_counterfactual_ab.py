import unittest

from reborn.counterfactual_ab_eval import _paired_delta, _summary


class CounterfactualABTests(unittest.TestCase):
    def row(self, result, seed=1, seat=0, completed=True):
        return {
            'candidate': 'heldout',
            'pair': 0,
            'seed': seed,
            'learned_seat': seat,
            'completed': completed,
            'learned_result': result,
            'learned_fallback_decisions': 0,
            'observation_checks': 3,
            'policy_view_checks': 3,
        }

    def test_paired_delta_counts_improvement_and_degradation(self):
        control = [
            self.row('loss', seed=1, seat=0),
            self.row('win', seed=1, seat=1),
            self.row('draw', seed=2, seat=0),
        ]
        treatment = [
            self.row('win', seed=1, seat=0),
            self.row('loss', seed=1, seat=1),
            self.row('draw', seed=2, seat=0),
        ]
        self.assertEqual(
            _paired_delta(control, treatment),
            {'improved': 1, 'degraded': 1, 'unchanged': 1},
        )

    def test_paired_delta_rejects_misaligned_games(self):
        control = [self.row('loss', seed=1)]
        treatment = [self.row('win', seed=2)]
        with self.assertRaises(ValueError):
            _paired_delta(control, treatment)

    def test_summary_uses_only_completed_games_for_rate(self):
        rows = [self.row('win'), self.row('loss', seed=2), self.row(None, seed=3, completed=False)]
        summary = _summary(rows)
        self.assertEqual(summary['completed'], 2)
        self.assertEqual(summary['wins'], 1)
        self.assertEqual(summary['losses'], 1)
        self.assertAlmostEqual(summary['win_rate'], 0.5)
        self.assertEqual(summary['observation_checks'], 9)
        self.assertEqual(summary['policy_view_checks'], 9)


if __name__ == '__main__':
    unittest.main()
