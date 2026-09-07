import unittest

from reborn.verified_data import load_verified_official_records


class VerifiedAliasOfficialRecordTests(unittest.TestCase):
    def test_reviewed_alias_records_are_loaded_under_reborn_titles(self):
        records = load_verified_official_records()
        expected = {
            'Cemetery Bomb': 'Cemetary Bomb',
            'Fallen Down': 'Falling Down',
            'Firedarts': 'Fire Darts',
            'Lord D.': 'Lord of D.',
            'Raging Spirit': 'Radiant Spirit',
            'Reliable Guardian': 'The Reliable Guardian',
            'Sanctuary in the Sky': 'The Sanctuary in the Sky',
            'Sniper Hunter': 'Snipe Hunter',
            'Stone Shooter': 'Storm Shooter',
            'Super Vehicroid - Jumbo Drill': 'Super Vehicroid Jumbo Drill',
            'Teya': 'Teva',
            'Three-Hump Lacooda': '3-Hump Lacooda',
            'Twin-Headed Beast': 'Twinheaded Beast',
        }
        for pool_name, current_name in expected.items():
            with self.subTest(pool_name=pool_name):
                self.assertIn(pool_name, records)
                self.assertEqual(records[pool_name]['name'], current_name)
                self.assertTrue(records[pool_name]['text'])
                self.assertTrue(records[pool_name]['text_sha256'])
                self.assertIn('db.yugioh-card.com', records[pool_name]['source_url'])

    def test_fusion_alias_is_authoritatively_extra_deck(self):
        records = load_verified_official_records()
        self.assertEqual(records['Super Vehicroid - Jumbo Drill']['placement'], 'extra')

    def test_existing_verified_records_still_merge(self):
        records = load_verified_official_records()
        self.assertIn('Dragged Down into the Grave', records)
        self.assertIn('Wow Warrior', records)
        self.assertIn('Red-Eyes Black Chick', records)


if __name__ == '__main__':
    unittest.main()
