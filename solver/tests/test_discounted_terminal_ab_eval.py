import unittest

from reborn.discounted_terminal_ab_eval import DiscountedTerminalPolicy


class DiscountedTerminalPolicyTests(unittest.TestCase):
    def test_terminal_weight_half_life(self):
        p = DiscountedTerminalPolicy
        self.assertAlmostEqual(p.terminal_weight(0), 1.0)
        self.assertAlmostEqual(p.terminal_weight(256), 0.5)
        self.assertAlmostEqual(p.terminal_weight(512), 0.25)

    def test_weight_decreases_monotonically(self):
        p = DiscountedTerminalPolicy
        values = [p.terminal_weight(x) for x in (0, 64, 128, 256, 512)]
        self.assertTrue(all(a > b for a, b in zip(values, values[1:])))

    def test_far_credit_remains_positive(self):
        self.assertGreater(DiscountedTerminalPolicy.terminal_weight(1024), 0.0)


if __name__ == '__main__':
    unittest.main()
