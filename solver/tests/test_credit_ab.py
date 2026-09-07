import unittest

from reborn.credit_ab_eval import EqualDuelCreditPolicy, _paired_summary
from reborn.learning import PolicyStep, SparsePolicy


class CreditNormalizationABTests(unittest.TestCase):
    def test_equal_duel_policy_matches_explicit_one_over_n_scale(self):
        options = [('choice:a',), ('choice:b',)]
        steps = [PolicyStep(0, options, 0) for _ in range(4)]
        treatment = EqualDuelCreditPolicy(seed=1, learning_rate=0.5)
        explicit = SparsePolicy(seed=1, learning_rate=0.5)
        treatment.update_episode(steps, winner=0)
        explicit.update_episode(steps, winner=0, scale=0.25)
        self.assertEqual(treatment.weights, explicit.weights)

    def test_equal_duel_policy_preserves_explicit_scale_override(self):
        options = [('choice:a',), ('choice:b',)]
        steps = [PolicyStep(0, options, 0) for _ in range(4)]
        treatment = EqualDuelCreditPolicy(seed=2, learning_rate=0.5)
        explicit = SparsePolicy(seed=2, learning_rate=0.5)
        treatment.update_episode(steps, winner=0, scale=0.75)
        explicit.update_episode(steps, winner=0, scale=0.75)
        self.assertEqual(treatment.weights, explicit.weights)

    def test_paired_summary_uses_win_draw_loss_order(self):
        base = {'candidate': 'x', 'pair': 0, 'seed': 10, 'learned_seat': 0}
        control = [
            {**base, 'learned_result': 'loss'},
            {**base, 'pair': 1, 'learned_result': 'draw'},
            {**base, 'pair': 2, 'learned_result': 'win'},
        ]
        treatment = [
            {**base, 'learned_result': 'draw'},
            {**base, 'pair': 1, 'learned_result': 'loss'},
            {**base, 'pair': 2, 'learned_result': 'win'},
        ]
        summary, _ = _paired_summary(control, treatment)
        self.assertEqual(summary, {
            'improved': 1, 'degraded': 1, 'unchanged': 1, 'unavailable': 0,
        })

    def test_paired_summary_rejects_misalignment(self):
        control = [{'candidate': 'x', 'pair': 0, 'seed': 10, 'learned_seat': 0, 'learned_result': 'win'}]
        treatment = [{'candidate': 'y', 'pair': 0, 'seed': 10, 'learned_seat': 0, 'learned_result': 'win'}]
        with self.assertRaises(RuntimeError):
            _paired_summary(control, treatment)


if __name__ == '__main__':
    unittest.main()
