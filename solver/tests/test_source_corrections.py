import json
import unittest

from reborn.import_pool import ROOT, apply_source_corrections, key, parse_pool


class SourceCorrectionTests(unittest.TestCase):
    def test_double_summon_is_replaced_by_dragged_down(self):
        raw = (ROOT/'data/raw/MASTER.txt').read_text()
        cards = parse_pool(raw)
        spec = json.loads((ROOT/'data/source_corrections.json').read_text())
        applied = apply_source_corrections(cards, spec)

        self.assertEqual(len(cards), 2273)
        by_id = {c['id']: c for c in cards}
        self.assertEqual(by_id['reborn-0530']['name'], 'Dragged Down into the Grave')
        self.assertNotIn(key('Double Summon'), {key(c['name']) for c in cards})
        self.assertEqual(applied[0]['from_name'], 'Double Summon')
        self.assertEqual(applied[0]['to_name'], 'Dragged Down into the Grave')

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
