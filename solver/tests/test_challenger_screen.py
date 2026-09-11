import unittest

from reborn.challenger_screen import _accumulate, deck_id


class ChallengerScreenTests(unittest.TestCase):
    def test_deck_id_is_order_invariant(self):
        a = ['b', 'a', 'c']
        b = ['c', 'b', 'a']
        self.assertEqual(deck_id(a), deck_id(b))

    def test_accumulate_challenger_win_by_seat(self):
        sample = {
            'wins': 0, 'losses': 0, 'draws': 0, 'games': 0,
            'unsupported': 0, 'timeouts': 0, 'fallback_decisions': 0,
        }
        _accumulate(
            sample,
            {'completed': True, 'winner': 1, 'fallback_decisions': 0},
            challenger_seat=1,
        )
        self.assertEqual(sample['wins'], 1)
        self.assertEqual(sample['losses'], 0)
        self.assertEqual(sample['games'], 1)

    def test_accumulate_blocked_result_invalidates_sample(self):
        sample = {
            'wins': 0, 'losses': 0, 'draws': 0, 'games': 0,
            'unsupported': 0, 'timeouts': 0, 'fallback_decisions': 0,
        }
        _accumulate(
            sample,
            {
                'completed': False,
                'blocker': 'UnsupportedInteraction: payoff duel exceeded 5000 engine steps',
                'fallback_decisions': 2,
            },
            challenger_seat=0,
        )
        self.assertEqual(sample['unsupported'], 1)
        self.assertEqual(sample['timeouts'], 1)
        self.assertEqual(sample['fallback_decisions'], 2)


if __name__ == '__main__':
    unittest.main()
