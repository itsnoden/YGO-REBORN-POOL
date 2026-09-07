import unittest

from reborn.import_pool import ROOT
from reborn.ocgcore import merge_nonstandard_card_data, resolve_script_path
from reborn.verified_data import load_nonstandard_cards, nonstandard_engine_rows


class NonstandardCardTests(unittest.TestCase):
    def test_level_down_is_exact_anime_identity_not_tcg_question_mark(self):
        cards = load_nonstandard_cards()
        self.assertIn('Level Down!', cards)
        spec = cards['Level Down!']
        self.assertEqual(spec['engine_id'], 100000250)
        self.assertEqual(spec['engine_name'], 'Level Down!')
        self.assertEqual(spec['status'], 'reviewed_anime_only_card')
        self.assertEqual(spec['placement'], 'main')
        self.assertNotEqual(spec['engine_id'], 90500169)

    def test_nonstandard_row_is_normal_spell_card_data(self):
        rows = nonstandard_engine_rows()
        row = next(r for r in rows if r['name'] == 'Level Down!')
        self.assertEqual(row['id'], 100000250)
        self.assertEqual(row['type'], 2)
        self.assertEqual(row['level'], 0)
        self.assertEqual(row['atk'], 0)
        self.assertEqual(row['def'], 0)

    def test_longnose_blue_mammoth_is_reviewed_video_game_normal_monster(self):
        cards = load_nonstandard_cards()
        spec = cards['Longnose Blue Mammoth']
        self.assertEqual(spec['engine_id'], 25737191)
        self.assertEqual(spec['status'], 'reviewed_video_game_only_normal_monster')
        self.assertEqual(spec['placement'], 'main')
        self.assertEqual(spec['data']['type'], 17)
        self.assertEqual(spec['data']['level'], 3)
        self.assertEqual(spec['data']['attribute'], 1)
        self.assertEqual(spec['data']['race'], 65536)
        self.assertEqual(spec['data']['atk'], 800)
        self.assertEqual(spec['data']['def'], 900)

    def test_longnose_engine_row_is_normal_monster_and_distinct_from_great_long_nose(self):
        rows = nonstandard_engine_rows()
        row = next(r for r in rows if r['name'] == 'Longnose Blue Mammoth')
        self.assertEqual(row['id'], 25737191)
        self.assertEqual(row['type'], 17)
        self.assertEqual(row['atk'], 800)
        self.assertEqual(row['def'], 900)
        self.assertNotEqual(row['id'], 2356994)

    def test_runtime_card_data_overlay_adds_level_down_and_longnose(self):
        data = {1: {'id': 1}}
        names = {1: 'Existing'}
        added = merge_nonstandard_card_data(data, names)
        self.assertIn(100000250, added)
        self.assertIn(25737191, added)
        self.assertEqual(names[100000250], 'Level Down!')
        self.assertEqual(names[25737191], 'Longnose Blue Mammoth')
        self.assertEqual(data[100000250]['type'], 2)
        self.assertEqual(data[25737191]['type'], 17)

    def test_runtime_overlay_rejects_id_collision(self):
        data = {100000250: {'id': 100000250}}
        with self.assertRaises(ValueError):
            merge_nonstandard_card_data(data, {})

    def test_level_down_uses_reviewed_solver_override(self):
        source, path = resolve_script_path(ROOT/'vendor/scripts', 'c100000250.lua')
        self.assertEqual(source, 'override')
        text = path.read_text()
        self.assertIn('-- Level Down!', text)
        self.assertIn('EFFECT_UPDATE_LEVEL', text)
        self.assertIn('e1:SetValue(-2)', text)


if __name__ == '__main__':
    unittest.main()
