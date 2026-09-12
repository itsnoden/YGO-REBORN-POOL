import unittest

from reborn.opponent_field_context_ab_eval import OpponentFieldContextPolicy


def observation():
    return {
        'viewer': 0,
        'phase': 4,
        'turn_player': 0,
        'chains': [],
        'players': [
            {
                'lp': 8000, 'hand_count': 2, 'grave_count': 0,
                'mzone': [], 'szone': [],
            },
            {
                'lp': 8000, 'hand_count': 2, 'grave_count': 0,
                'mzone': [
                    {'present': True, 'card': {'code': 777, 'position': 1}},
                    {'present': True, 'card': {'position': 8}},
                ],
                'szone': [
                    {'present': True, 'card': {'code': 888, 'position': 4}},
                    {'present': True, 'card': {'hidden': True}},
                ],
            },
        ],
    }


class OpponentFieldContextTests(unittest.TestCase):
    def test_only_public_opponent_field_codes_become_context(self):
        policy = OpponentFieldContextPolicy(seed=1)
        ctx = policy._opponent_field_context(observation())
        self.assertIn('opp_field:mzone|card:777', ctx)
        self.assertIn('opp_field:szone|card:888', ctx)
        self.assertEqual(len(ctx), 2)

    def test_context_can_condition_an_action(self):
        policy = OpponentFieldContextPolicy(seed=2)
        obs = observation()
        features = policy.action_features(
            {'kind': 'chain'},
            obs,
            {'label': 'chain', 'card': {'code': 123}, 'description': 55},
        )
        self.assertIn(
            'opp_field_ctx:opp_field:mzone|card:777|card_label:123|chain',
            features,
        )

    def test_hidden_field_identity_never_appears(self):
        policy = OpponentFieldContextPolicy(seed=3)
        features = policy.action_features(
            {'kind': 'yesno'}, observation(),
            {'label': 'yes', 'description': 1},
        )
        joined = '\n'.join(features)
        self.assertNotIn('hidden', joined)


if __name__ == '__main__':
    unittest.main()
