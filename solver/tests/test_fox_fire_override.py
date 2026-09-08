import unittest

from reborn.import_pool import ROOT


class FoxFireOverrideTests(unittest.TestCase):
    def test_records_face_down_state_when_becoming_battle_target(self):
        text = (ROOT / 'script_overrides/c88753985.lua').read_text()
        self.assertIn('EVENT_BE_BATTLE_TARGET', text)
        self.assertIn('c:ResetFlagEffect(id)', text)
        self.assertIn('if c:IsFacedown() then', text)
        self.assertIn('c:RegisterFlagEffect(id,RESET_PHASE|PHASE_BATTLE,0,1)', text)

    def test_face_down_at_damage_step_case_does_not_register_end_phase_summon(self):
        text = (ROOT / 'script_overrides/c88753985.lua').read_text()
        self.assertIn('if c:GetFlagEffect(id)>0 then return end', text)
        self.assertIn('c:IsReason(REASON_BATTLE)', text)
        self.assertIn('c:IsPreviousPosition(POS_FACEUP)', text)
        self.assertIn('EVENT_PHASE+PHASE_END', text)

    def test_later_face_up_attack_clears_older_face_down_target_flag(self):
        text = (ROOT / 'script_overrides/c88753985.lua').read_text()
        # Every new attack-target event resets the old record before conditionally
        # registering the face-down marker for this new battle.
        self.assertLess(text.index('c:ResetFlagEffect(id)'), text.index('if c:IsFacedown() then'))

    def test_tribute_summon_restriction_is_preserved(self):
        text = (ROOT / 'script_overrides/c88753985.lua').read_text()
        self.assertIn('EFFECT_UNRELEASABLE_SUM', text)
        self.assertIn('e3:SetValue(1)', text)


if __name__ == '__main__':
    unittest.main()
