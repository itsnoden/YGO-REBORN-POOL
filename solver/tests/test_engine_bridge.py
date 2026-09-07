import json
import unittest

from reborn.engine_bridge import (
    _whitelist_lines, mapping_suggestions, reviewed_alias_match,
    unique_exact_text_match,
)
from reborn.import_pool import ROOT
from reborn.verified_data import load_identity_aliases


class EngineBridgeSuggestionTests(unittest.TestCase):
    def test_close_title_is_ranked_without_becoming_mapping(self):
        rows = [
            {'id': 1, 'name': 'Completely Different Card'},
            {'id': 2, 'name': 'The Sanctuary in the Sky'},
            {'id': 3, 'name': 'Another Card'},
        ]
        suggestions = mapping_suggestions('Sanctuary in the Sky', rows, 3)
        self.assertEqual(suggestions[0]['id'], 2)
        self.assertEqual(suggestions[0]['name'], 'The Sanctuary in the Sky')
        self.assertGreater(suggestions[0]['similarity'], suggestions[1]['similarity'])

    def test_suggestions_do_not_drop_candidate_identity(self):
        rows = [
            {'id': 74677422, 'name': 'Red-Eyes Black Dragon'},
            {'id': 46986414, 'name': 'Snipe Hunter'},
        ]
        suggestions = mapping_suggestions('Sniper Hunter', rows, 2)
        self.assertEqual(suggestions[0]['id'], 46986414)
        self.assertEqual(suggestions[0]['name'], 'Snipe Hunter')

    def test_limit_zero_is_empty(self):
        self.assertEqual(mapping_suggestions('Anything', [{'id': 1, 'name': 'Anything'}], 0), [])

    def test_unique_exact_text_can_resolve_renamed_title(self):
        rows = [
            {'id': 10, 'name': 'Current Name', 'alias': 0, 'desc': 'Exact current effect text.'},
            {'id': 11, 'name': 'Other Card', 'alias': 0, 'desc': 'Different text.'},
        ]
        match, candidates = unique_exact_text_match('Exact current effect text.', rows)
        self.assertEqual(match['id'], 10)
        self.assertEqual([r['id'] for r in candidates], [10])

    def test_exact_text_fallback_rejects_ambiguity(self):
        rows = [
            {'id': 10, 'name': 'Card A', 'alias': 0, 'desc': 'Same text.'},
            {'id': 11, 'name': 'Card B', 'alias': 0, 'desc': 'Same text.'},
        ]
        match, candidates = unique_exact_text_match('Same text.', rows)
        self.assertIsNone(match)
        self.assertEqual({r['id'] for r in candidates}, {10, 11})

    def test_exact_text_fallback_respects_reserved_id(self):
        rows = [{'id': 10, 'name': 'Current Name', 'alias': 0, 'desc': 'Exact text.'}]
        match, candidates = unique_exact_text_match('Exact text.', rows, blocked_ids={10})
        self.assertIsNone(match)
        self.assertEqual(candidates, [])

    def test_reviewed_alias_requires_exact_reviewed_target(self):
        records = {'current name': [{'id': 10, 'name': 'Current Name', 'alias': 0}]}
        aliases = {'Old Name': {'engine_name': 'Current Name', 'status': 'reviewed'}}
        match, spec = reviewed_alias_match('Old Name', records, aliases)
        self.assertEqual(match['id'], 10)
        self.assertEqual(spec['status'], 'reviewed')

    def test_reviewed_alias_rejects_reserved_collision(self):
        records = {'current name': [{'id': 10, 'name': 'Current Name', 'alias': 0}]}
        aliases = {'Old Name': {'engine_name': 'Current Name', 'status': 'reviewed'}}
        with self.assertRaises(ValueError):
            reviewed_alias_match('Old Name', records, aliases, blocked_ids={10})

    def test_shared_identity_alias_can_reuse_already_mapped_id_only(self):
        records = {'current name': [{'id': 10, 'name': 'Current Name', 'alias': 0}]}
        aliases = {'Legacy Name': {
            'engine_name': 'Current Name',
            'status': 'reviewed_shared_current_identity',
            'allow_shared_engine_identity': True,
        }}
        # Reserved-but-not-yet-mapped is still blocked.
        with self.assertRaises(ValueError):
            reviewed_alias_match(
                'Legacy Name', records, aliases, blocked_ids={10}, shared_ids=set()
            )
        # Reuse is permitted only once the same identity is already mapped.
        match, spec = reviewed_alias_match(
            'Legacy Name', records, aliases, blocked_ids={10}, shared_ids={10}
        )
        self.assertEqual(match['id'], 10)
        self.assertTrue(spec['allow_shared_engine_identity'])

    def test_whitelist_deduplicates_shared_passcode_and_keeps_strictest_limit(self):
        rows = [
            {'passcode': 10, 'copy_limit': 3, 'engine_name': 'Current Name'},
            {'passcode': 10, 'copy_limit': 1, 'engine_name': 'Current Name'},
            {'passcode': 20, 'copy_limit': 2, 'engine_name': 'Other Name'},
        ]
        self.assertEqual(
            _whitelist_lines(rows),
            ['10 1 -- Current Name', '20 2 -- Other Name'],
        )

    def test_identity_alias_file_keeps_level_down_distinct(self):
        data = json.loads((ROOT/'data/identity_aliases.json').read_text())
        self.assertNotIn('Level Down!', data['aliases'])
        self.assertEqual(
            data['explicit_non_aliases']['Level Down!']['status'],
            'do_not_map_to_level_down_interrobang',
        )

    def test_reviewed_pool_identity_aliases_are_explicit(self):
        data = json.loads((ROOT/'data/identity_aliases.json').read_text())
        expected = {
            'Cemetery Bomb': 'Cemetary Bomb',
            'Fallen Down': 'Falling Down',
            'Raging Spirit': 'Radiant Spirit',
            'Red-Eyes B. Dragon': 'Red-Eyes Black Dragon',
            'Sniper Hunter': 'Snipe Hunter',
            'Stone Shooter': 'Storm Shooter',
            'Teya': 'Teva',
            'Twin-Headed Beast': 'Twinheaded Beast',
        }
        self.assertEqual(
            {name: data['aliases'][name]['engine_name'] for name in expected},
            expected,
        )

    def test_long_nose_remains_distinct_but_red_eyes_chick_is_shared_identity(self):
        aliases, non_aliases = load_identity_aliases()
        self.assertNotIn('Long Nose', aliases)
        self.assertEqual(
            non_aliases['Long Nose']['status'],
            'do_not_map_to_great_long_nose',
        )
        self.assertNotIn('Red-Eyes Black Chick', non_aliases)
        chick = aliases['Red-Eyes Black Chick']
        self.assertEqual(chick['engine_name'], "Black Dragon's Chick")
        self.assertTrue(chick['allow_shared_engine_identity'])


if __name__ == '__main__':
    unittest.main()
