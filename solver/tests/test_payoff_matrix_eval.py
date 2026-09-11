import unittest

from reborn.payoff_matrix_eval import build_matrix, matchup_schedule


class PayoffMatrixTests(unittest.TestCase):
    def setUp(self):
        self.population = [
            ('A', ['a'] * 40),
            ('B', ['b'] * 40),
            ('C', ['c'] * 40),
        ]

    def test_schedule_includes_unordered_pairs_and_diagonal(self):
        rows = matchup_schedule(self.population, [10, 11])
        self.assertEqual(len(rows), 6 * 2)
        keys = {(r['a'], r['b']) for r in rows}
        self.assertEqual(
            keys,
            {('A', 'A'), ('A', 'B'), ('A', 'C'),
             ('B', 'B'), ('B', 'C'), ('C', 'C')},
        )

    def test_build_matrix_records_both_seats_for_off_diagonal(self):
        result_a_first = {
            'completed': True, 'winner': 0, 'fallback_decisions': 0
        }
        result_a_second = {
            'completed': True, 'winner': 0, 'fallback_decisions': 0
        }
        rows = [{
            'a': 'A',
            'b': 'B',
            'seed': 1,
            'a_first_result': result_a_first,
            'a_second_result': result_a_second,
        }]
        matrix = build_matrix(self.population[:2], rows)

        self.assertEqual(matrix['A']['B']['first']['wins'], 1)
        self.assertEqual(matrix['A']['B']['second']['losses'], 1)
        self.assertEqual(matrix['B']['A']['first']['wins'], 1)
        self.assertEqual(matrix['B']['A']['second']['losses'], 1)

    def test_fallback_marks_sample_uncertified(self):
        row = {
            'completed': True,
            'winner': 0,
            'fallback_decisions': 1,
        }
        rows = [{
            'a': 'A', 'b': 'A', 'seed': 1,
            'a_first_result': row,
            'a_second_result': row,
        }]
        matrix = build_matrix(self.population[:1], rows)
        self.assertFalse(matrix['A']['A']['first']['certified'])
        self.assertFalse(matrix['A']['A']['second']['certified'])


if __name__ == '__main__':
    unittest.main()
