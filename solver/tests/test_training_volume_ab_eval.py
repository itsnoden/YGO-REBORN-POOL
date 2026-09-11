import unittest

from reborn.training_volume_ab_eval import training_schedule


class TrainingVolumeABTests(unittest.TestCase):
    def setUp(self):
        self.pool = [
            ('a', ['reborn-a']),
            ('b', ['reborn-b']),
            ('c', ['reborn-c']),
            ('d', ['reborn-d']),
        ]

    def public(self, row):
        return {k: v for k, v in row.items() if not k.startswith('_')}

    def test_long_arm_has_exact_control_prefix(self):
        short = training_schedule(self.pool, 16, 151000)
        long = training_schedule(self.pool, 64, 151000)
        self.assertEqual(
            [self.public(r) for r in short],
            [self.public(r) for r in long[:16]],
        )

    def test_seat_order_alternates_on_same_pair(self):
        rows = training_schedule(self.pool, 2, 10)
        self.assertEqual((rows[0]['seat0'], rows[0]['seat1']), ('a', 'b'))
        self.assertEqual((rows[1]['seat0'], rows[1]['seat1']), ('c', 'b'))

    def test_seed_sequence_is_contiguous(self):
        rows = training_schedule(self.pool, 5, 100)
        self.assertEqual([r['seed'] for r in rows], [100, 101, 102, 103, 104])


if __name__ == '__main__':
    unittest.main()
