import unittest

from reborn.engine_bridge import mapping_suggestions


class EngineBridgeSuggestionTests(unittest.TestCase):
    def test_close_title_is_ranked_without_becoming_mapping(self):
        rows = [
            {'id': 1, 'name': 'Completely Different Card'},
            {'id': 2, 'name': 'The Sanctuary in the Sky'},
            {'id': 3, 'name': 'Another Card'},
        ]
        suggestions = mapping_suggestions('Sanctuary in the Sky', rows, 3)
        self.assertEqual(suggestions[0]['id'], 2)
        self.assertEqual(suggestions[0]['name'], 'The Sanctuary in the Sky')
        self.assertGreater(suggestions[0]['similarity'], suggestions[1]['similarity'])

    def test_suggestions_do_not_drop_candidate_identity(self):
        rows = [
            {'id': 74677422, 'name': 'Red-Eyes Black Dragon'},
            {'id': 46986414, 'name': 'Snipe Hunter'},
        ]
        suggestions = mapping_suggestions('Sniper Hunter', rows, 2)
        self.assertEqual(suggestions[0]['id'], 46986414)
        self.assertEqual(suggestions[0]['name'], 'Snipe Hunter')

    def test_limit_zero_is_empty(self):
        self.assertEqual(mapping_suggestions('Anything', [{'id': 1, 'name': 'Anything'}], 0), [])


if __name__ == '__main__':
    unittest.main()
