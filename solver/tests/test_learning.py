import struct
import unittest

from reborn.learning import SparsePolicy, PolicyStep
from reborn.learning_pilot import LearningPilot
from reborn.protocol import parse_decision


def observation(viewer=0):
    def player(p):
        return {
            'player': p, 'lp': 8000, 'hand_count': 5, 'grave_count': 0,
            'removed_count': 0, 'deck_count': 35, 'extra_count': 0, 'extra_faceup_count': 0,
            'mzone': [{'sequence': i, 'present': False} for i in range(7)],
            'szone': [{'sequence': i, 'present': False} for i in range(8)],
            'hand': [], 'grave': [], 'removed': [], 'extra': [],
        }
    return {'viewer': viewer, 'turn_player': viewer, 'phase': 4,
            'players': [player(0), player(1)], 'chains': []}


class LearningTests(unittest.TestCase):
    def test_zero_weights_start_uniform(self):
        policy = SparsePolicy(seed=1)
        probs = policy.probabilities([('a',), ('b',), ('c',)])
        self.assertAlmostEqual(probs[0], 1/3)
        self.assertAlmostEqual(probs[1], 1/3)
        self.assertAlmostEqual(probs[2], 1/3)

    def test_winning_choice_is_reinforced(self):
        policy = SparsePolicy(seed=1, learning_rate=1.0)
        options = [('choice:a',), ('choice:b',)]
        policy.update_episode([PolicyStep(0, options, 0)], winner=0, scale=1.0)
        self.assertGreater(policy.score(options[0]), policy.score(options[1]))
        policy.update_episode([PolicyStep(1, options, 0)], winner=0, scale=1.0)
        self.assertLess(policy.score(options[0]) - policy.score(options[1]), 1.0)

    def test_features_use_filtered_prompt_not_hidden_raw_code(self):
        policy = SparsePolicy(seed=2)
        prompt = {'kind': 'select_card', 'cards': [
            {'controller': 1, 'location': 4, 'sequence': 0},
            {'controller': 1, 'location': 4, 'sequence': 1, 'code': 123},
        ]}
        obs = observation(0)
        first = policy.card_features(prompt, obs, prompt['cards'][0])
        second = policy.card_features(prompt, obs, prompt['cards'][1])
        self.assertFalse(any('card:999' in f for f in first))
        self.assertTrue(any(f == 'card:123' for f in second))

    def test_learning_pilot_maps_filtered_action_index_to_response(self):
        decision = parse_decision(bytes([13, 0]) + struct.pack('<Q', 99))
        prompt = {
            'kind': 'yesno', 'player': 0, 'minimum': 0, 'maximum': 0,
            'cancelable': False, 'cards': [], 'meta': {},
            'actions': [{'choice_index': 0, 'label': 'no', 'description': 99},
                        {'choice_index': 1, 'label': 'yes', 'description': 99}],
        }
        policy = SparsePolicy(seed=4)
        pilot = LearningPilot(policy, seed=5)
        response = pilot.choose(decision, prompt, observation(0))
        self.assertIn(response, (struct.pack('<i', 0), struct.pack('<i', 1)))
        self.assertEqual(pilot.learned_decisions, 1)
        self.assertEqual(len(pilot.steps), 1)


if __name__ == '__main__':
    unittest.main()
