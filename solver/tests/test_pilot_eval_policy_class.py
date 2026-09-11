import unittest

from reborn.learning import SparsePolicy
from reborn.pilot_eval import frozen_policy_copy


class MarkerPolicy(SparsePolicy):
    def action_features(self, prompt, observation, action):
        return tuple(super().action_features(prompt, observation, action)) + ('marker',)


class PilotEvalPolicyClassTests(unittest.TestCase):
    def test_frozen_copy_preserves_policy_subclass_and_weights(self):
        original = MarkerPolicy(
            seed=7,
            temperature=0.75,
            learning_rate=0.05,
            weights={'marker': 1.25, 'card:123': -0.5},
        )
        clone = frozen_policy_copy(original, 99)
        self.assertIsInstance(clone, MarkerPolicy)
        self.assertEqual(clone.seed, 99)
        self.assertEqual(clone.temperature, original.temperature)
        self.assertEqual(clone.learning_rate, 0.0)
        self.assertEqual(clone.weights, original.weights)
        self.assertIsNot(clone.weights, original.weights)

    def test_subclass_feature_generator_remains_active(self):
        original = MarkerPolicy(seed=1, weights={'marker': 2.0})
        clone = frozen_policy_copy(original, 2)
        obs = {
            'viewer': 0,
            'phase': 4,
            'turn_player': 0,
            'players': [
                {'lp': 8000, 'hand_count': 0, 'grave_count': 0,
                 'mzone': [], 'szone': []},
                {'lp': 8000, 'hand_count': 0, 'grave_count': 0,
                 'mzone': [], 'szone': []},
            ],
        }
        features = clone.action_features(
            {'kind': 'yesno'}, obs, {'label': 'yes', 'description': 1}
        )
        self.assertIn('marker', features)


if __name__ == '__main__':
    unittest.main()
