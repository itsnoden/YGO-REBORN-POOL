import unittest

from reborn.import_pool import ROOT


class PoisonDrawFrogOverrideTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT/'script_overrides/c56840658.lua').read_text()

    def test_records_face_down_attack_target_state_before_damage(self):
        self.assertIn('SetCode(EVENT_BE_BATTLE_TARGET)', self.text)
        self.assertIn('SetOperation(s.regop)', self.text)
        self.assertIn('c:ResetFlagEffect(id)', self.text)
        self.assertIn('if c:IsFacedown() then', self.text)
        self.assertIn(
            'c:RegisterFlagEffect(id,RESET_PHASE|PHASE_BATTLE,0,1)',
            self.text,
        )

    def test_flag_survives_flip_and_move_to_grave_for_trigger_check(self):
        # RESET_EVENT would erase the state when battle flips/moves the card,
        # defeating the TCG-specific exception check at EVENT_TO_GRAVE.
        regop = self.text.split('function s.regop', 1)[1].split('function s.condition', 1)[0]
        self.assertNotIn('RESET_EVENT', regop)
        self.assertNotIn('RESETS_STANDARD', regop)

    def test_suppresses_only_battle_send_after_face_down_attack(self):
        condition = self.text.split('function s.condition', 1)[1].split('function s.target', 1)[0]
        self.assertIn('c:IsPreviousLocation(LOCATION_ONFIELD)', condition)
        self.assertIn('c:IsPreviousPosition(POS_FACEUP)', condition)
        self.assertIn('c:IsReason(REASON_BATTLE)', condition)
        self.assertIn('c:GetFlagEffect(id)>0', condition)
        self.assertIn('and not (c:IsReason(REASON_BATTLE)', condition)

    def test_later_face_up_attack_clears_old_face_down_flag(self):
        # regop always clears the old state first and only re-adds it if the
        # card is face-down at the new attack-target event.
        regop = self.text.split('function s.regop', 1)[1].split('function s.condition', 1)[0]
        reset_pos = regop.index('c:ResetFlagEffect(id)')
        facedown_pos = regop.index('if c:IsFacedown() then')
        register_pos = regop.index('c:RegisterFlagEffect(id,RESET_PHASE|PHASE_BATTLE,0,1)')
        self.assertLess(reset_pos, facedown_pos)
        self.assertLess(facedown_pos, register_pos)

    def test_non_battle_send_is_not_suppressed_after_canceled_attack(self):
        # The exception is conjunctive: the remembered face-down attack state
        # alone is insufficient; the actual send-to-GY reason must be battle.
        condition = self.text.split('function s.condition', 1)[1].split('function s.target', 1)[0]
        self.assertIn(
            'not (c:IsReason(REASON_BATTLE) and c:GetFlagEffect(id)>0)',
            condition,
        )


if __name__ == '__main__':
    unittest.main()
