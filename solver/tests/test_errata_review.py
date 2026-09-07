import unittest

from reborn.errata_review import (
    build_review_report, normalized_text_sha256, validate_review,
)


class ErrataReviewTests(unittest.TestCase):
    def _card(self, text='Destroy 1 monster.'):
        return {'id': 'reborn-0001', 'official': {'text': text}}

    def _entry(self, text='Destroy one monster.'):
        return {
            'reborn_id': 'reborn-0001', 'name': 'Test Card', 'passcode': 123,
            'normal_monster': False, 'engine_text': text,
        }

    def _review(self, official='Destroy 1 monster.', engine='Destroy one monster.'):
        return {
            'reborn_id': 'reborn-0001',
            'passcode': 123,
            'status': 'behavior_equivalent_wording_reviewed',
            'official_text_sha256': normalized_text_sha256(official),
            'engine_text_sha256': normalized_text_sha256(engine),
            'rationale': 'Test-only reviewed wording pair.',
        }

    def test_exact_hash_bound_review_is_valid(self):
        ok, _, mismatches = validate_review(self._review(), self._card(), self._entry())
        self.assertTrue(ok)
        self.assertEqual(mismatches, [])

    def test_official_text_change_invalidates_review(self):
        ok, _, mismatches = validate_review(
            self._review(), self._card('Banish 1 monster.'), self._entry()
        )
        self.assertFalse(ok)
        self.assertIn('official_text_sha256', mismatches)

    def test_engine_text_change_invalidates_review(self):
        ok, _, mismatches = validate_review(
            self._review(), self._card(), self._entry('Destroy exactly one monster.')
        )
        self.assertFalse(ok)
        self.assertIn('engine_text_sha256', mismatches)

    def test_passcode_change_invalidates_review(self):
        entry = self._entry()
        entry['passcode'] = 999
        ok, _, mismatches = validate_review(self._review(), self._card(), entry)
        self.assertFalse(ok)
        self.assertIn('passcode', mismatches)

    def test_valid_review_clears_only_current_lexical_pair(self):
        report = build_review_report(
            [self._card()], [self._entry()], {'r': self._review()}
        )
        self.assertEqual(report['lexical_effect_rows'], 1)
        self.assertEqual(report['valid_behavior_equivalence_reviews'], 1)
        self.assertEqual(report['unresolved_lexical_behavior_blockers'], 0)

    def test_review_cannot_clear_exact_pair(self):
        card = self._card('Draw 1 card.')
        entry = self._entry('Draw 1 card.')
        review = self._review('Draw 1 card.', 'Draw 1 card.')
        report = build_review_report([card], [entry], {'r': review})
        self.assertEqual(report['valid_behavior_equivalence_reviews'], 0)
        self.assertEqual(report['stale_or_invalid_reviews'], 1)
        self.assertEqual(report['unresolved_lexical_behavior_blockers'], 0)

    def test_empty_ledger_leaves_all_lexical_rows_unresolved(self):
        report = build_review_report([self._card()], [self._entry()], {})
        self.assertEqual(report['lexical_effect_rows'], 1)
        self.assertEqual(report['valid_behavior_equivalence_reviews'], 0)
        self.assertEqual(report['unresolved_lexical_behavior_blockers'], 1)


if __name__ == '__main__':
    unittest.main()
