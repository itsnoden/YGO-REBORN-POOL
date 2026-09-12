import struct
import unittest

from reborn.learning import SparsePolicy
from reborn.learning_pilot import LearningPilot
from reborn.protocol import CardRef, Decision


def observation():
    return {
        'viewer': 0,
        'phase': 4,
        'turn_player': 0,
        'chains': [],
        'players': [
            {
                'lp': 8000, 'hand_count': 13, 'grave_count': 0,
                'mzone': [], 'szone': [],
            },
            {
                'lp': 8000, 'hand_count': 0, 'grave_count': 0,
                'mzone': [], 'szone': [],
            },
        ],
    }


class LargeSelectLearningTests(unittest.TestCase):
    def test_large_subset_space_is_learned_not_fallback(self):
        cards = tuple(
            CardRef(1000 + i, 0, 0x02, i)
            for i in range(13)
        )
        decision = Decision(
            'select_card', 0, cards=cards,
            minimum=1, maximum=12, cancelable=False,
        )
        prompt = decision.view_for(0)
        policy = SparsePolicy(seed=123)
        pilot = LearningPilot(policy, seed=456, max_complex_options=512)

        response = pilot.choose(decision, prompt, observation())

        mode, count = struct.unpack('<iI', response[:8])
        self.assertEqual(mode, 2)
        self.assertGreaterEqual(count, 1)
        self.assertLessEqual(count, 12)
        self.assertEqual(len(response), 8 + count)
        self.assertEqual(pilot.fallback_decisions, 0)
        self.assertGreater(pilot.learned_decisions, 0)
        self.assertGreater(pilot.complex_learned_decisions, 0)


if __name__ == '__main__':
    unittest.main()
