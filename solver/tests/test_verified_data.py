import unittest

from reborn.verified_data import (
    apply_verified_official_records,
    load_identity_aliases,
    load_verified_official_records,
)


class VerifiedDataTests(unittest.TestCase):
    def test_shared_identity_supersedes_old_conservative_non_alias_hold(self):
        aliases, non_aliases = load_identity_aliases()
        self.assertIn('Red-Eyes Black Chick', aliases)
        self.assertNotIn('Red-Eyes Black Chick', non_aliases)
        self.assertTrue(aliases['Red-Eyes Black Chick']['allow_shared_engine_identity'])

    def test_durable_official_gap_records_include_current_red_eyes_identity(self):
        records = load_verified_official_records()
        chick = records['Red-Eyes Black Chick']
        self.assertEqual(chick['name'], "Black Dragon's Chick")
        self.assertEqual(chick['cid'], '6109')
        self.assertEqual(chick['placement'], 'main')

    def test_verified_record_fills_missing_official_and_placement_only(self):
        cards = [
            {'name': 'Red-Eyes Black Chick', 'official': None, 'placement': None},
            {'name': 'Amazoness Archer', 'official': {'text': 'existing'}, 'placement': 'main'},
        ]
        applied = apply_verified_official_records(cards)
        self.assertEqual(applied, ['Red-Eyes Black Chick'])
        self.assertEqual(cards[0]['placement'], 'main')
        self.assertIn('Red-Eyes Black Dragon', cards[0]['official']['text'])
        self.assertEqual(cards[1]['official'], {'text': 'existing'})


if __name__ == '__main__':
    unittest.main()
