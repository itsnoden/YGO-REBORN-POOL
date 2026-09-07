import unittest

from reborn.text_audit import (
    build_report, classify_text_pair, lexical_tokens, rules_terminology_tokens,
)


class TextAuditTests(unittest.TestCase):
    def test_exact_text_is_exact(self):
        self.assertEqual(classify_text_pair('Draw 1 card.', 'Draw 1 card.'), 'exact')

    def test_official_html_br_is_normalized_as_line_break(self):
        self.assertEqual(
            classify_text_pair('First effect.<br>Second effect.', 'First effect.\nSecond effect.'),
            'exact',
        )
        self.assertEqual(
            classify_text_pair('First effect.<BR />Second effect.', 'First effect. Second effect.'),
            'exact',
        )

    def test_punctuation_case_only_is_not_certified_exact(self):
        self.assertEqual(
            classify_text_pair('Target 1 monster; destroy it.', 'TARGET 1 monster: destroy it!'),
            'token_sequence_identical_formatting_only',
        )

    def test_established_rules_vocabulary_is_separate_non_blocker(self):
        pairs = [
            ('Send this card to the GY.', 'Send this card to the Graveyard.'),
            ('Pay 500 LP.', 'Pay 500 Life Points.'),
            ('Target 1 Machine monster.', 'Target 1 Machine-Type monster.'),
        ]
        for modern, legacy in pairs:
            with self.subTest(modern=modern):
                self.assertEqual(
                    classify_text_pair(modern, legacy),
                    'rules_terminology_equivalent_only',
                )

    def test_generic_type_language_is_not_removed(self):
        modern = 'Declare 1 Type of monster.'
        changed = 'Declare 1 monster.'
        self.assertNotEqual(rules_terminology_tokens(modern), rules_terminology_tokens(changed))
        self.assertEqual(
            classify_text_pair(modern, changed),
            'lexical_difference_requires_audit',
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

    def test_lexical_tokens_ignore_only_case_punctuation_and_br_presentation(self):
        self.assertEqual(lexical_tokens('GY;<br>1 Card!'), ('gy', '1', 'card'))

    def test_report_prioritizes_lexical_differences(self):
        cards = [
            {'id': 'a', 'official': {'text': 'Draw 1 card.', 'text_sha256': 'a'}},
            {'id': 'b', 'official': {'text': 'Target 1 monster; destroy it.', 'text_sha256': 'b'}},
            {'id': 'c', 'official': {'text': 'Destroy 1 monster.', 'text_sha256': 'c'}},
            {'id': 'd', 'official': {'text': 'Send it to the GY.', 'text_sha256': 'd'}},
        ]
        mapped = [
            {'reborn_id': 'a', 'name': 'A', 'engine_name': 'A', 'passcode': 1,
             'normal_monster': False, 'engine_text': 'Draw 1 card.', 'latest_official_text_sha256': 'a'},
            {'reborn_id': 'b', 'name': 'B', 'engine_name': 'B', 'passcode': 2,
             'normal_monster': False, 'engine_text': 'TARGET 1 monster: destroy it!', 'latest_official_text_sha256': 'b'},
            {'reborn_id': 'c', 'name': 'C', 'engine_name': 'C', 'passcode': 3,
             'normal_monster': False, 'engine_text': 'Banish 1 monster.', 'latest_official_text_sha256': 'c'},
            {'reborn_id': 'd', 'name': 'D', 'engine_name': 'D', 'passcode': 4,
             'normal_monster': False, 'engine_text': 'Send it to the Graveyard.', 'latest_official_text_sha256': 'd'},
        ]
        report = build_report(cards, mapped)
        self.assertEqual(report['counts']['exact'], 1)
        self.assertEqual(report['counts']['token_sequence_identical_formatting_only'], 1)
        self.assertEqual(report['counts']['rules_terminology_equivalent_only'], 1)
        self.assertEqual(report['counts']['lexical_difference_requires_audit'], 1)
        self.assertEqual(report['behavior_text_audit_blockers'], 1)
        self.assertEqual(report['rows'][0]['name'], 'C')

    def test_reviewed_nonstandard_exact_record_is_not_tcg_missing_text_blocker(self):
        cards = [{'id': 'u', 'official': None}]
        mapped = [
            {'reborn_id': 'u', 'name': 'Anime Card', 'engine_name': 'Anime Card', 'passcode': 100,
             'normal_monster': False, 'engine_text': 'Reviewed anime effect.',
             'mapping_source': 'reviewed_nonstandard_card', 'nonstandard_text_match': True,
             'nonstandard_status': 'reviewed_anime_only_card',
             'nonstandard_implementation_source': 'reviewed-source',
             'latest_official_text_sha256': None},
        ]
        report = build_report(cards, mapped)
        self.assertEqual(report['counts']['reviewed_nonstandard_text_not_tcg_blocker'], 1)
        self.assertEqual(report['behavior_text_audit_blockers'], 0)
        self.assertEqual(report['rows'][0]['category'], 'reviewed_nonstandard_text_not_tcg_blocker')

    def test_nonstandard_without_exact_review_still_blocks(self):
        cards = [{'id': 'u', 'official': None}]
        mapped = [
            {'reborn_id': 'u', 'name': 'Anime Card', 'engine_name': 'Anime Card', 'passcode': 101,
             'normal_monster': False, 'engine_text': 'Unverified anime effect.',
             'mapping_source': 'reviewed_nonstandard_card', 'nonstandard_text_match': False,
             'latest_official_text_sha256': None},
        ]
        report = build_report(cards, mapped)
        self.assertEqual(report['counts']['missing_latest_official_text'], 1)
        self.assertEqual(report['behavior_text_audit_blockers'], 1)

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
