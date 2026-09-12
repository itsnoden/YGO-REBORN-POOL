import unittest

from reborn.iterative_challenger_search import challenger_key, identity


class IterativeChallengerSearchTests(unittest.TestCase):
    def test_identity_is_order_invariant(self):
        self.assertEqual(
            identity(['b', 'a', 'c']),
            identity(['c', 'b', 'a']),
        )

    def test_challenger_key_prefers_worst_case_bound_first(self):
        weaker = {
            'id': 'a',
            'aggregate': {
                'worst_opponent_win_wilson95_lower': 0.20,
                'mean_score_rate': 0.80,
                'wins': 20,
                'losses': 4,
            },
        }
        stronger = {
            'id': 'b',
            'aggregate': {
                'worst_opponent_win_wilson95_lower': 0.30,
                'mean_score_rate': 0.55,
                'wins': 12,
                'losses': 10,
            },
        }
        self.assertGreater(challenger_key(stronger), challenger_key(weaker))


if __name__ == '__main__':
    unittest.main()
