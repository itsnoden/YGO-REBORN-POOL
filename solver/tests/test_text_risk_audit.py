import unittest

from reborn.text_risk_audit import classify_risk


class TextRiskAuditTests(unittest.TestCase):
    def test_numeric_change_is_high_risk(self):
        row = classify_risk('Inflict 500 damage.', 'Inflict 800 damage.')
        self.assertEqual(row['risk_tier'], 'high')
        self.assertTrue(row['numeric_sequence_changed'])

    def test_targeting_change_is_high_risk(self):
        row = classify_risk('Target 1 monster; destroy it.', 'Destroy 1 monster.')
        self.assertEqual(row['risk_tier'], 'high')
        self.assertIn('targeting', row['high_signal_groups'])

    def test_once_per_turn_change_is_high_risk(self):
        row = classify_risk('Once per turn: You can draw 1 card.', 'You can draw 1 card.')
        self.assertEqual(row['risk_tier'], 'high')
        self.assertIn('frequency_or_restriction', row['high_signal_groups'])

    def test_scope_only_change_is_medium_when_no_high_group_changes(self):
        row = classify_risk('All monsters gain 300 ATK.', 'Each monster gains 300 ATK.')
        self.assertEqual(row['risk_tier'], 'medium')
        self.assertIn('player_or_scope', row['changed_signal_groups'])

    def test_non_signal_lexical_change_remains_low_not_certified(self):
        row = classify_risk('Select a creature.', 'Choose a creature.')
        self.assertEqual(row['risk_tier'], 'low')
        self.assertFalse(row['numeric_sequence_changed'])
        self.assertEqual(row['changed_signal_groups'], [])


if __name__ == '__main__':
    unittest.main()
