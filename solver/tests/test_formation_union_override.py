import unittest

from reborn.import_pool import ROOT


class FormationUnionOverrideTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT/'script_overrides/c26931058.lua').read_text()

    def test_targeting_is_mode_dependent_not_global(self):
        initial = self.text.split('function s.initial_effect(c)', 1)[1].split('end\ns.listed_card_types', 1)[0]
        self.assertNotIn('SetProperty(EFFECT_FLAG_CARD_TARGET)', initial)
        self.assertIn('e:SetProperty(EFFECT_FLAG_CARD_TARGET)', self.text)

    def test_mode_one_targets_only_the_union_monster(self):
        # Current PSCT targets only the face-up Union monster. The appropriate
        # equip recipient is chosen during resolution and is not a card target.
        self.assertEqual(self.text.count('Duel.SelectTarget('), 1)
        self.assertIn(
            'Duel.SelectTarget(tp,s.unioneqfilter,tp,LOCATION_MZONE,0,1,1,nil,tp)',
            self.text,
        )
        self.assertIn(
            'Duel.SelectMatchingCard(tp,s.eqfilter,tp,LOCATION_MZONE,0,1,1,ec,ec)',
            self.text,
        )

    def test_mode_two_selects_on_resolution_without_targeting(self):
        self.assertIn(
            'Duel.IsExistingMatchingCard(s.spfilter,tp,LOCATION_STZONE,0,1,nil,e,tp)',
            self.text,
        )
        self.assertIn(
            'Duel.SelectMatchingCard(tp,s.spfilter,tp,LOCATION_STZONE,0,1,1,nil,e,tp)',
            self.text,
        )
        self.assertNotIn('Duel.SelectTarget(tp,s.spfilter', self.text)
        self.assertIn(
            'Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,nil,1,tp,LOCATION_STZONE)',
            self.text,
        )


if __name__ == '__main__':
    unittest.main()
