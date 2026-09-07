import unittest

from reborn.text_audit import build_report, classify_text_pair, lexical_tokens


class TextAuditTests(unittest.TestCase):
    def test_exact_text_is_exact(self):
        self.assertEqual(classify_text_pair('Draw 1 card.', 'Draw 1 card.'), 'exact')

    def test_punctuation_case_only_is_not_certified_exact(self):
        self.assertEqual(
            classify_text_pair('Target 1 monster; destroy it.', 'TARGET 1 monster: destroy it!'),
            'token_sequence_identical_formatting_only',
        )

    def test_lexical_change_stays_audit_blocker(self):
        self.assertEqual(
            classify_text_pair('Destroy 1 monster.', 'Banish 1 monster.'),
            'lexical_difference_requires_audit',
        )

    def test_missing_official_text_is_explicit(self):
        self.assertEqual(
            classify_text_pair('', 'Some engine text.'),
            'missing_latest_official_text',
        )

    def test_lexical_tokens_ignore_only_case_and_punctuation(self):
        self.assertEqual(lexical_tokens('GY; 1 Card!'), ('gy', '1', 'card'))

    def test_report_prioritizes_lexical_differences(self):
        cards = [
            {'id': 'a', 'official': {'text': 'Draw 1 card.', 'text_sha256': 'a'}},
            {'id': 'b', 'official': {'text': 'Target 1 monster; destroy it.', 'text_sha256': 'b'}},
            {'id': 'c', 'official': {'text': 'Destroy 1 monster.', 'text_sha256': 'c'}},
        ]
        mapped = [
            {'reborn_id': 'a', 'name': 'A', 'engine_name': 'A', 'passcode': 1,
             'normal_monster': False, 'engine_text': 'Draw 1 card.', 'latest_official_text_sha256': 'a'},
            {'reborn_id': 'b', 'name': 'B', 'engine_name': 'B', 'passcode': 2,
             'normal_monster': False, 'engine_text': 'TARGET 1 monster: destroy it!', 'latest_official_text_sha256': 'b'},
            {'reborn_id': 'c', 'name': 'C', 'engine_name': 'C', 'passcode': 3,
             'normal_monster': False, 'engine_text': 'Banish 1 monster.', 'latest_official_text_sha256': 'c'},
        ]
        report = build_report(cards, mapped)
        self.assertEqual(report['counts']['exact'], 1)
        self.assertEqual(report['counts']['token_sequence_identical_formatting_only'], 1)
        self.assertEqual(report['counts']['lexical_difference_requires_audit'], 1)
        self.assertEqual(report['behavior_text_audit_blockers'], 1)
        self.assertEqual(report['rows'][0]['name'], 'C')

    def test_normal_monster_lore_difference_is_not_behavior_blocker(self):
        cards = [
            {'id': 'n', 'official': {'text': 'A blue mammoth swings its nose.', 'text_sha256': 'n'}},
        ]
        mapped = [
            {'reborn_id': 'n', 'name': 'Normal', 'engine_name': 'Normal', 'passcode': 7,
             'normal_monster': True, 'engine_text': 'Old translated flavor text.',
             'latest_official_text_sha256': 'n'},
        ]
        report = build_report(cards, mapped)
        self.assertEqual(
            report['counts']['normal_monster_lore_only_not_behavior_blocker'], 1
        )
        self.assertEqual(report['behavior_text_audit_blockers'], 0)
        self.assertEqual(report['rows'][0]['category'], 'normal_monster_lore_only_not_behavior_blocker')

    def test_normal_monster_missing_lore_is_still_not_behavior_blocker(self):
        cards = [{'id': 'n', 'official': None}]
        mapped = [
            {'reborn_id': 'n', 'name': 'Normal', 'engine_name': 'Normal', 'passcode': 8,
             'normal_monster': True, 'engine_text': 'Legacy flavor text.',
             'latest_official_text_sha256': None},
        ]
        report = build_report(cards, mapped)
        self.assertEqual(
            report['counts']['normal_monster_lore_only_not_behavior_blocker'], 1
        )
        self.assertEqual(report['behavior_text_audit_blockers'], 0)


if __name__ == '__main__':
    unittest.main()
