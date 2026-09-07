import unittest

from reborn.rules import REBORN_FLAGS, get_profile


class RulesProfileTests(unittest.TestCase):
    def test_reborn_profile_is_certified(self):
        self.assertEqual(REBORN_FLAGS, 12885092352)
        profile = get_profile('reborn')
        self.assertTrue(profile['certified_for_reborn'])
        self.assertFalse(profile['first_turn_draw'])
        self.assertEqual(profile['opening_hand'], 5)
        self.assertEqual(profile['starting_lp'], 8000)

    def test_experimental_alias_matches_reborn_for_old_reports(self):
        alias = get_profile('experimental_current_tcg')
        reborn = get_profile('reborn')
        self.assertEqual(alias['flags'], reborn['flags'])
        self.assertTrue(alias['certified_for_reborn'])

    def test_reference_profiles_remain_uncertified(self):
        self.assertTrue(get_profile('mr1_reference')['first_turn_draw'])
        self.assertTrue(get_profile('mr2_reference')['first_turn_draw'])
        self.assertFalse(get_profile('mr1_reference')['certified_for_reborn'])
        self.assertFalse(get_profile('mr2_reference')['certified_for_reborn'])


if __name__ == '__main__':
    unittest.main()
