import unittest

from reborn.upstream_drift_audit import intersect_pool_changes, script_passcodes


class UpstreamDriftAuditTests(unittest.TestCase):
    def test_script_passcodes_extracts_only_official_card_scripts(self):
        paths = [
            'official/c123.lua',
            'official/c456789.lua',
            'unofficial/c999.lua',
            'official/utility.lua',
            'rush/c555.lua',
        ]
        self.assertEqual(script_passcodes(paths), {123, 456789})

    def test_script_passcodes_accepts_windows_separators(self):
        self.assertEqual(script_passcodes([r'official\\c12345678.lua']), {12345678})

    def test_intersection_reports_only_changed_reborn_cards(self):
        mapped = [
            {'reborn_id': 'reborn-0001', 'name': 'Alpha', 'engine_name': 'Alpha', 'passcode': 111},
            {'reborn_id': 'reborn-0002', 'name': 'Beta', 'engine_name': 'Beta', 'passcode': 222},
            {'reborn_id': 'reborn-0003', 'name': 'Beta Legacy', 'engine_name': 'Beta', 'passcode': 222},
        ]
        rows = intersect_pool_changes({222, 333}, mapped)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['passcode'], 222)
        self.assertEqual(rows[0]['reborn_ids'], ['reborn-0002', 'reborn-0003'])
        self.assertEqual(rows[0]['pool_names'], ['Beta', 'Beta Legacy'])
        self.assertEqual(rows[0]['engine_names'], ['Beta'])


if __name__ == '__main__':
    unittest.main()
