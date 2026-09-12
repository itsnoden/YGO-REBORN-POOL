import unittest

from reborn.phase_turn_context_ab_eval import PhaseTurnContextPolicy


def observation(viewer=0, phase=4, turn_player=0):
    return {
        'viewer': viewer,
        'phase': phase,
        'turn_player': turn_player,
        'chains': [],
        'players': [
            {'lp': 8000, 'hand_count': 2, 'grave_count': 0,
             'mzone': [], 'szone': []},
            {'lp': 8000, 'hand_count': 2, 'grave_count': 0,
             'mzone': [], 'szone': []},
        ],
    }


class PhaseTurnContextTests(unittest.TestCase):
    def test_phase_turn_context_can_condition_card_action(self):
        policy = PhaseTurnContextPolicy(seed=1)
        obs = observation()
        prompt = {'kind': 'idle'}
        a = {'label': 'activate', 'card': {'code': 100}}
        b = {'label': 'activate', 'card': {'code': 101}}
        fa = policy.action_features(prompt, obs, a)
        fb = policy.action_features(prompt, obs, b)
        token = 'phase_turn_ctx:phase:4|card_label:100|activate'
        self.assertIn(token, fa)
        self.assertNotIn(token, fb)

    def test_only_phase_and_turn_side_are_crossed(self):
        policy = PhaseTurnContextPolicy(seed=2)
        self.assertEqual(
            policy._contexts(observation(viewer=0, phase=8, turn_player=1)),
            ('phase:8', 'turn_side:opp'),
        )

    def test_hidden_or_count_state_not_added_to_crosses(self):
        policy = PhaseTurnContextPolicy(seed=3)
        obs = observation()
        obs['players'][0]['hand_count'] = 6
        obs['players'][1]['hand_count'] = 1
        features = policy.action_features(
            {'kind': 'yesno'}, obs, {'label': 'yes', 'description': 55}
        )
        crossed = [f for f in features if f.startswith('phase_turn_ctx:')]
        self.assertTrue(crossed)
        self.assertFalse(any('hand_diff' in f or 'lp_diff' in f or 'field_diff' in f for f in crossed))


if __name__ == '__main__':
    unittest.main()
