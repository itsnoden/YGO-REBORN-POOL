import unittest

from reborn.import_pool import ROOT


class BacksToTheWallOverrideTests(unittest.TestCase):
    def test_duplicate_gate_only_checks_activating_players_monster_zone(self):
        text = (ROOT / 'script_overrides/c32603633.lua').read_text()
        self.assertIn(
            'Duel.IsExistingMatchingCard(aux.FaceupFilter(Card.IsCode,c:GetCode()),tp,LOCATION_MZONE,0,1,nil)',
            text,
        )
        self.assertNotIn(
            'Duel.IsExistingMatchingCard(aux.FaceupFilter(Card.IsCode,c:GetCode()),0,LOCATION_ONFIELD,LOCATION_ONFIELD,1,nil)',
            text,
        )

    def test_override_preserves_different_names_within_same_resolution(self):
        text = (ROOT / 'script_overrides/c32603633.lua').read_text()
        self.assertIn("g:Remove(Card.IsCode,nil,sg:GetFirst():GetCode())", text)
        self.assertIn('Duel.SpecialSummonComplete()', text)

    def test_override_preserves_100_lp_cost(self):
        text = (ROOT / 'script_overrides/c32603633.lua').read_text()
        self.assertIn('Duel.GetLP(tp)>100', text)
        self.assertIn('Duel.PayLPCost(tp,Duel.GetLP(tp)-100)', text)


if __name__ == '__main__':
    unittest.main()
