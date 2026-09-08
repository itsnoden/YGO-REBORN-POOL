from pathlib import Path
import unittest

from reborn.import_pool import ROOT


class FushiohRichieOverrideTests(unittest.TestCase):
    def test_override_blocks_generic_special_summons(self):
        text = (ROOT/'script_overrides/c39711336.lua').read_text()
        self.assertIn('c:EnableReviveLimit()', text)
        self.assertIn('c:AddCannotBeSpecialSummoned()', text)
        self.assertIn('aux.DoubleSnareValidity(c,LOCATION_MZONE)', text)

    def test_great_dezard_preserves_only_intended_hand_deck_summon(self):
        great_dezard = ROOT/'vendor/scripts/official/c88989706.lua'
        self.assertTrue(great_dezard.exists())
        text = great_dezard.read_text()
        self.assertIn('LOCATION_DECK|LOCATION_HAND', text)
        self.assertIn('Duel.SpecialSummon(g,0,tp,tp,true,false,POS_FACEUP)', text)
        self.assertIn('g:GetFirst():CompleteProcedure()', text)
        self.assertNotIn('LOCATION_GRAVE|LOCATION_HAND', text)


if __name__ == '__main__':
    unittest.main()
