import unittest

from reborn.rules import EXPERIMENTAL_CURRENT_TCG_FLAGS, get_profile


class RulesProfileTests(unittest.TestCase):
    def test_existing_engine_flags_are_named_but_not_reborn_certified(self):
        self.assertEqual(EXPERIMENTAL_CURRENT_TCG_FLAGS, 12885092352)
        profile = get_profile('experimental_current_tcg')
        self.assertFalse(profile['certified_for_reborn'])
        self.assertFalse(profile['first_turn_draw'])
        self.assertEqual(profile['opening_hand'], 5)

    def test_reference_profiles_remain_uncertified(self):
        self.assertTrue(get_profile('mr1_reference')['first_turn_draw'])
        self.assertTrue(get_profile('mr2_reference')['first_turn_draw'])
        self.assertFalse(get_profile('mr1_reference')['certified_for_reborn'])
        self.assertFalse(get_profile('mr2_reference')['certified_for_reborn'])


if __name__ == '__main__':
    unittest.main()
