import struct
import unittest

from reborn.pilot import StochasticLegalPilot
from reborn.protocol import parse_decision
from reborn.protocol_extra import parse_decision as parse_extra


class PilotTests(unittest.TestCase):
    def test_seeded_action_choice_is_reproducible(self):
        msg = bytes([13, 0]) + struct.pack('<Q', 99)
        decision = parse_decision(msg)
        obs = {'viewer': 0}
        a = StochasticLegalPilot(42).choose(decision, obs)
        b = StochasticLegalPilot(42).choose(decision, obs)
        self.assertEqual(a, b)
        self.assertIn(a, (struct.pack('<i', 0), struct.pack('<i', 1)))

    def test_seeded_select_card_response_is_legal_shape(self):
        msg = bytearray([15, 0, 0]) + struct.pack('<III', 1, 2, 3)
        for code, seq in ((100, 0), (200, 1), (300, 2)):
            msg += struct.pack('<IBBII', code, 0, 2, seq, 8)
        decision = parse_decision(bytes(msg))
        response = StochasticLegalPilot(9).choose(decision, {'viewer': 0})
        self.assertEqual(struct.unpack_from('<i', response, 0)[0], 2)
        count = struct.unpack_from('<I', response, 4)[0]
        self.assertIn(count, (1, 2))
        self.assertEqual(len(response), 8 + count)

    def test_counter_allocation_hits_exact_total(self):
        msg = bytearray([22, 1]) + struct.pack('<HHI', 0x10, 5, 3)
        msg += struct.pack('<IBBBH', 100, 1, 4, 0, 2)
        msg += struct.pack('<IBBBH', 200, 1, 8, 1, 4)
        msg += struct.pack('<IBBBH', 300, 1, 8, 2, 3)
        decision = parse_extra(bytes(msg))
        response = StochasticLegalPilot(7).choose(decision, {'viewer': 1})
        counts = struct.unpack('<hhh', response)
        self.assertEqual(sum(counts), 5)
        self.assertLessEqual(counts[0], 2)
        self.assertLessEqual(counts[1], 4)
        self.assertLessEqual(counts[2], 3)


if __name__ == '__main__':
    unittest.main()
