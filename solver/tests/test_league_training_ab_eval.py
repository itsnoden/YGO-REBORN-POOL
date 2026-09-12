import unittest

from reborn.learning import SparsePolicy
from reborn.league_training_ab_eval import _pair_for_game, _snapshot


class LeagueTrainingTests(unittest.TestCase):
    def test_snapshot_is_frozen_copy(self):
        policy = SparsePolicy(
            seed=7,
            temperature=0.8,
            learning_rate=0.05,
            weights={'a': 1.25},
        )
        snap = _snapshot(policy, 99)
        self.assertIsInstance(snap, SparsePolicy)
        self.assertEqual(snap.seed, 99)
        self.assertEqual(snap.temperature, 0.8)
        self.assertEqual(snap.learning_rate, 0.0)
        self.assertEqual(snap.weights, policy.weights)
        self.assertIsNot(snap.weights, policy.weights)

    def test_pair_schedule_matches_existing_training_rotation(self):
        pool = [
            ('a', ['a']),
            ('b', ['b']),
            ('c', ['c']),
            ('d', ['d']),
        ]
        seat0, seat1 = _pair_for_game(pool, 0)
        self.assertEqual((seat0[0], seat1[0]), ('a', 'b'))
        seat0, seat1 = _pair_for_game(pool, 1)
        self.assertEqual((seat0[0], seat1[0]), ('c', 'b'))


if __name__ == '__main__':
    unittest.main()
