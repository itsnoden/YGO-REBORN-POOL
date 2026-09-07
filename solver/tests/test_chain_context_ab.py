import unittest

from reborn.chain_context_ab_eval import ChainContextPolicy


def observation(viewer=0, turn_player=1, phase=8, chain_depth=2):
    def player(p):
        return {
            'player': p, 'lp': 8000, 'hand_count': 5, 'grave_count': 0,
            'removed_count': 0, 'deck_count': 35, 'extra_count': 0,
            'extra_faceup_count': 0,
            'mzone': [{'sequence': i, 'present': False} for i in range(7)],
            'szone': [{'sequence': i, 'present': False} for i in range(8)],
            'hand': [], 'grave': [], 'removed': [], 'extra': [],
        }
    return {
        'viewer': viewer,
        'turn_player': turn_player,
        'phase': phase,
        'players': [player(0), player(1)],
        'chains': [{} for _ in range(chain_depth)],
    }


class ChainContextABTests(unittest.TestCase):
    def test_chain_action_gets_only_small_safe_context_crosses(self):
        policy = ChainContextPolicy(seed=1)
        prompt = {'kind': 'chain'}
        action = {
            'label': 'activate',
            'card': {'code': 123, 'controller': 0, 'location': 8, 'sequence': 0},
            'description': 456,
        }
        features = policy.action_features(prompt, observation(), action)
        self.assertIn('chain_ctx:phase:8|kind_label:chain|activate', features)
        self.assertIn('chain_ctx:turn_side:opp|card_label:123|activate', features)
        self.assertIn('chain_ctx:chain_depth:2|desc_label:456|activate', features)
        self.assertFalse(any(f.startswith('known:') or f.startswith('known_chain:') for f in features))

    def test_non_chain_action_is_identical_to_canonical_features(self):
        treatment = ChainContextPolicy(seed=2)
        prompt = {'kind': 'idle'}
        action = {'label': 'end_phase'}
        obs = observation(turn_player=0, chain_depth=0)
        features = treatment.action_features(prompt, obs, action)
        self.assertFalse(any(f.startswith('chain_ctx:') for f in features))

    def test_chain_depth_is_bounded(self):
        policy = ChainContextPolicy(seed=3)
        features = policy.action_features(
            {'kind': 'chain'}, observation(chain_depth=20), {'label': 'pass'}
        )
        self.assertIn('chain_ctx:chain_depth:8|kind_label:chain|pass', features)
        self.assertFalse(any('chain_depth:20' in f for f in features))


if __name__ == '__main__':
    unittest.main()
