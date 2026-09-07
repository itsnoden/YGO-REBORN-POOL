import json
import unittest

from reborn.import_pool import ROOT, apply_source_corrections, key, parse_pool


class SourceCorrectionTests(unittest.TestCase):
    def _corrected_cards(self):
        raw = (ROOT/'data/raw/MASTER.txt').read_text()
        cards = parse_pool(raw)
        spec = json.loads((ROOT/'data/source_corrections.json').read_text())
        applied = apply_source_corrections(cards, spec)
        return cards, applied, spec

    def test_double_summon_is_replaced_by_dragged_down(self):
        cards, applied, _ = self._corrected_cards()
        self.assertEqual(len(cards), 2273)
        by_id = {c['id']: c for c in cards}
        self.assertEqual(by_id['reborn-0530']['name'], 'Dragged Down into the Grave')
        self.assertNotIn(key('Double Summon'), {key(c['name']) for c in cards})
        self.assertEqual(applied[0]['from_name'], 'Double Summon')
        self.assertEqual(applied[0]['to_name'], 'Dragged Down into the Grave')
        self.assertEqual(applied[0]['state'], 'applied')

    def test_worm_warrior_is_replaced_by_wow_warrior(self):
        cards, applied, _ = self._corrected_cards()
        by_id = {c['id']: c for c in cards}
        names = {key(c['name']) for c in cards}
        self.assertEqual(by_id['reborn-2083']['name'], 'Wow Warrior')
        self.assertNotIn(key('Worm Warrior'), names)
        self.assertIn(key('Wow Warrior'), names)
        self.assertEqual(applied[1]['from_name'], 'Worm Warrior')
        self.assertEqual(applied[1]['to_name'], 'Wow Warrior')
        self.assertEqual(applied[1]['state'], 'applied')

    def test_long_nose_is_replaced_by_reviewed_longnose_blue_mammoth(self):
        cards, applied, _ = self._corrected_cards()
        by_id = {c['id']: c for c in cards}
        names = {key(c['name']) for c in cards}
        self.assertEqual(by_id['reborn-1117']['name'], 'Longnose Blue Mammoth')
        self.assertNotIn(key('Long Nose'), names)
        self.assertIn(key('Longnose Blue Mammoth'), names)
        self.assertIn(key('Great Long Nose'), names)
        self.assertEqual(applied[2]['from_name'], 'Long Nose')
        self.assertEqual(applied[2]['to_name'], 'Longnose Blue Mammoth')
        self.assertEqual(applied[2]['state'], 'applied')

    def test_corrections_are_idempotent_for_already_corrected_cache(self):
        cards, _, spec = self._corrected_cards()
        second = apply_source_corrections(cards, spec)
        self.assertTrue(all(row['state'] == 'already_corrected' for row in second))
        names = {key(c['name']) for c in cards}
        self.assertNotIn(key('Double Summon'), names)
        self.assertNotIn(key('Worm Warrior'), names)
        self.assertNotIn(key('Long Nose'), names)

    def test_correction_refuses_unexpected_source_row(self):
        cards = [{'id': 'reborn-0530', 'name': 'Something Else'}]
        spec = {
            'corrections': [{
                'reborn_id': 'reborn-0530',
                'from_name': 'Double Summon',
                'to_name': 'Dragged Down into the Grave',
            }]
        }
        with self.assertRaises(ValueError):
            apply_source_corrections(cards, spec)


if __name__ == '__main__':
    unittest.main()
