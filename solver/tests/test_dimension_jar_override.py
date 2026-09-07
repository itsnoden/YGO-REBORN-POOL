import unittest

from reborn.import_pool import ROOT


class DimensionJarOverrideTests(unittest.TestCase):
    def test_reviewed_override_requires_monster_before_spirit_elimination_filter(self):
        text = (ROOT/'script_overrides/c73414375.lua').read_text()
        self.assertIn(
            'return c:IsMonster() and c:IsAbleToRemove(tp) and aux.SpElimFilter(c)',
            text,
        )

    def test_override_keeps_spirit_elimination_compatible_locations(self):
        text = (ROOT/'script_overrides/c73414375.lua').read_text()
        # Do not "simplify" the upstream MZONE|GRAVE search to GY-only: Spirit
        # Elimination can substitute monsters on the field for monsters in the GY.
        self.assertIn('LOCATION_MZONE|LOCATION_GRAVE', text)
        self.assertIn('Duel.Remove(g,POS_FACEUP,REASON_EFFECT)', text)


if __name__ == '__main__':
    unittest.main()
