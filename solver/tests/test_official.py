import unittest

from reborn.official import (
    allowed_official_names,
    resolve_official_record,
    split_official_display_name,
)


class OfficialIdentityAliasTests(unittest.TestCase):
    def test_reviewed_alias_target_is_allowed_for_official_crawl(self):
        cards = [{'name': 'Vampire Orchis'}]
        aliases = {'Vampire Orchis': {'engine_name': 'Vampiric Orchis'}}
        allowed = allowed_official_names(cards, aliases)
        self.assertIn('vampire orchis', allowed)
        self.assertIn('vampiric orchis', allowed)

    def test_alias_can_attach_current_official_record_to_legacy_pool_name(self):
        card = {'name': 'Marie the Fallen One'}
        aliases = {'Marie the Fallen One': {'engine_name': 'Darklord Marie'}}
        matched = {'darklord marie': {'name': 'Darklord Marie', 'cid': '5209'}}
        record, source = resolve_official_record(card, matched, aliases)
        self.assertEqual(record['cid'], '5209')
        self.assertEqual(source, 'reviewed_identity_alias')

    def test_direct_pool_title_beats_alias(self):
        card = {'name': 'Old Name'}
        aliases = {'Old Name': {'engine_name': 'Current Name'}}
        matched = {
            'old name': {'name': 'Old Name', 'cid': '1'},
            'current name': {'name': 'Current Name', 'cid': '2'},
        }
        record, source = resolve_official_record(card, matched, aliases)
        self.assertEqual(record['cid'], '1')
        self.assertEqual(source, 'exact_pool_title')

    def test_unreviewed_near_match_is_not_accepted(self):
        card = {'name': 'Sniper Hunter'}
        matched = {'snipe hunter': {'name': 'Snipe Hunter', 'cid': '6879'}}
        record, source = resolve_official_record(card, matched, {})
        self.assertIsNone(record)
        self.assertIsNone(source)

    def test_official_updated_from_suffix_is_provenance_not_current_name(self):
        current, previous = split_official_display_name(
            'Slime Toad (Updated from: Frog the Jam)'
        )
        self.assertEqual(current, 'Slime Toad')
        self.assertEqual(previous, 'Frog the Jam')

    def test_arbitrary_parenthetical_card_name_is_not_stripped(self):
        current, previous = split_official_display_name('Card Name (Alpha)')
        self.assertEqual(current, 'Card Name (Alpha)')
        self.assertIsNone(previous)


if __name__ == '__main__':
    unittest.main()
