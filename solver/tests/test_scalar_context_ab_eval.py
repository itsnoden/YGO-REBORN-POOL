import unittest

from reborn.scalar_context_ab_eval import ScalarContextPolicy


def observation(viewer=0):
    empty_zone = [{'present': False} for _ in range(5)]
    return {
        'viewer': viewer,
        'phase': 4,
        'turn_player': viewer,
        'chains': [],
        'players': [
            {
                'lp': 8000, 'hand_count': 3, 'grave_count': 0,
                'removed_count': 0, 'deck_count': 35,
                'mzone': list(empty_zone), 'szone': list(empty_zone),
                'hand': [], 'grave': [], 'removed': [], 'extra': [],
            },
            {
                'lp': 8000, 'hand_count': 3, 'grave_count': 0,
                'removed_count': 0, 'deck_count': 35,
                'mzone': list(empty_zone), 'szone': list(empty_zone),
                'hand': [{'hidden': True}, {'hidden': True}, {'hidden': True}],
                'grave': [], 'removed': [], 'extra': [],
            },
        ],
    }


class ScalarContextTests(unittest.TestCase):
    def test_scalar_context_can_change_action_preference(self):
        policy = ScalarContextPolicy(seed=1)
        obs = observation()
        prompt = {'kind': 'idle'}
        a = {'label': 'activate', 'card': {'code': 100}}
        b = {'label': 'activate', 'card': {'code': 101}}
        fa = policy.action_features(prompt, obs, a)
        fb = policy.action_features(prompt, obs, b)
        token = 'scalar_ctx:phase:4|card_label:100|activate'
        self.assertIn(token, fa)
        self.assertNotIn(token, fb)
        policy.weights[token] = 2.0
        pa, pb = policy.probabilities([fa, fb])
        self.assertGreater(pa, pb)

    def test_hidden_opponent_card_identity_never_enters_scalar_context(self):
        policy = ScalarContextPolicy(seed=2)
        obs = observation()
        prompt = {'kind': 'yesno'}
        action = {'label': 'yes', 'description': 55}
        features = policy.action_features(prompt, obs, action)
        self.assertFalse(any('known:' in f for f in features))
        self.assertFalse(any('hidden' in f for f in features))

    def test_contexts_are_only_canonical_scalar_state_tokens(self):
        policy = ScalarContextPolicy(seed=3)
        ctx = policy._contexts(observation())
        self.assertEqual(
            ctx,
            (
                'phase:4',
                'turn_side:self',
                'lp_diff:0',
                'hand_diff:0',
                'field_diff:0',
                'grave_diff:0',
            ),
        )


if __name__ == '__main__':
    unittest.main()
