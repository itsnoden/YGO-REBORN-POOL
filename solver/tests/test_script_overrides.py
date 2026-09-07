import json
import tempfile
import unittest
from pathlib import Path

from reborn.import_pool import ROOT
from reborn.ocgcore import SCRIPT_OVERRIDE_DIR, resolve_script_path


class ScriptOverrideTests(unittest.TestCase):
    def test_double_spell_override_is_reviewed_and_present(self):
        path = SCRIPT_OVERRIDE_DIR/'c24096228.lua'
        self.assertTrue(path.is_file())
        text = path.read_text()
        self.assertIn('checking_double_spell', text)
        self.assertIn('CheckActivateEffect', text)
        self.assertIn('49b0af044cebcb92f3f23211ef436971e1fc16fb', text)

    def test_redmd_latest_errata_override_is_reviewed_and_present(self):
        path = SCRIPT_OVERRIDE_DIR/'c88264978.lua'
        self.assertTrue(path.is_file())
        text = path.read_text()
        self.assertIn('Red-Eyes Darkness Metal Dragon (88264978)', text)
        self.assertIn('49b0af044cebcb92f3f23211ef436971e1fc16fb', text)
        self.assertIn('local s,id=GetID()', text)
        self.assertIn('SetCountLimit(1,id,EFFECT_COUNT_CODE_OATH)', text)
        self.assertIn('SetCountLimit(1,{id,1})', text)
        self.assertIn('not c:IsCode(id)', text)
        self.assertIn('LOCATION_GRAVE|LOCATION_HAND', text)

    def test_engine_bridge_reports_redmd_override_as_available_unvalidated(self):
        rows = json.loads((ROOT/'data/processed/engine_cards.json').read_text())
        redmd = next(r for r in rows if r['name'] == 'Red-Eyes Darkness Metal Dragon')
        self.assertEqual(redmd['script_source'], 'reviewed_override')
        self.assertEqual(redmd['status'], 'reviewed_override_unvalidated')
        self.assertEqual(redmd['script_path'], 'script_overrides/c88264978.lua')
        coverage = json.loads((ROOT/'reports/engine_coverage.json').read_text())
        self.assertNotIn('Red-Eyes Darkness Metal Dragon', coverage['missing_script'])
        self.assertGreaterEqual(coverage['reviewed_overrides'], 1)

    def test_reviewed_override_precedes_pinned_official_script(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as od:
            scripts = Path(td); overrides = Path(od)
            (scripts/'official').mkdir()
            (scripts/'official'/'c123.lua').write_text('upstream')
            (overrides/'c123.lua').write_text('override')
            source, path = resolve_script_path(scripts, 'c123.lua', overrides)
            self.assertEqual(source, 'override')
            self.assertEqual(path.read_text(), 'override')

    def test_unreviewed_script_falls_back_to_pinned_official(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as od:
            scripts = Path(td); overrides = Path(od)
            (scripts/'official').mkdir()
            (scripts/'official'/'c456.lua').write_text('upstream')
            source, path = resolve_script_path(scripts, 'c456.lua', overrides)
            self.assertEqual(source, 'official')
            self.assertEqual(path.read_text(), 'upstream')


if __name__ == '__main__':
    unittest.main()
