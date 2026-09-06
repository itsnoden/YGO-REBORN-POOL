import struct
import unittest

from reborn.effects import UnsupportedInteraction
from reborn.protocol import (
    Action, Decision, extract_decision, parse_decision,
    encode_card_selection, encode_place_selection,
)


class ProtocolTests(unittest.TestCase):
    def test_idle_actions_and_phase_response(self):
        # player 0; one summonable card; no other card groups; to BP + EP.
        body = bytearray([11, 0])
        body += struct.pack('<I', 1)
        body += struct.pack('<IBBI', 123, 0, 2, 0)
        for _ in range(4):
            body += struct.pack('<I', 0)
        body += struct.pack('<I', 0)
        body += bytes([1, 1, 0])
        d = parse_decision(bytes(body))
        self.assertEqual(d.kind, 'idle')
        self.assertEqual([a.label for a in d.actions], ['normal_summon', 'battle_phase', 'end_phase'])
        self.assertEqual(d.actions[0].response, struct.pack('<I', 0))
        self.assertEqual(d.actions[1].response, struct.pack('<I', 6))
        self.assertEqual(d.actions[2].response, struct.pack('<I', 7))

    def test_decision_privacy_and_unsupported_prompt(self):
        msg = bytes([13, 1]) + struct.pack('<Q', 99)
        d = parse_decision(msg)
        self.assertEqual(d.view_for(1)['kind'], 'yesno')
        with self.assertRaises(UnsupportedInteraction):
            d.view_for(0)
        with self.assertRaises(UnsupportedInteraction):
            parse_decision(bytes([20, 0]))

    def test_select_card_u8_encoding_and_bounds(self):
        msg = bytearray([15, 0, 1])
        msg += struct.pack('<III', 1, 2, 2)
        for code, seq in ((100, 0), (200, 1)):
            msg += struct.pack('<IBBII', code, 0, 2, seq, 8)
        d = parse_decision(bytes(msg))
        self.assertEqual(d.minimum, 1)
        self.assertEqual(d.maximum, 2)
        self.assertEqual(encode_card_selection(d, [1]), struct.pack('<iI', 2, 1) + b'\x01')
        self.assertEqual(encode_card_selection(d, None), struct.pack('<i', -1))
        with self.assertRaises(ValueError):
            encode_card_selection(d, [])
        with self.assertRaises(ValueError):
            encode_card_selection(d, [0, 0])

    def test_chain_pass_only_when_not_forced(self):
        def message(forced):
            msg = bytearray([16, 0, 0, forced])
            msg += struct.pack('<III', 0, 0, 1)
            msg += struct.pack('<IBBIIQB', 333, 0, 4, 0, 1, 444, 0)
            return bytes(msg)
        self.assertEqual(parse_decision(message(0)).actions[0].label, 'pass_chain')
        self.assertNotIn('pass_chain', [a.label for a in parse_decision(message(1)).actions])

    def test_place_mask_and_encoder(self):
        # Only own MZONE 0 is allowed: all bits forbidden except bit 0.
        flag = 0xFFFFFFFF ^ 0x1
        d = parse_decision(bytes([18, 0, 1]) + struct.pack('<I', flag))
        self.assertEqual(d.meta['places'], [(0, 4, 0)])
        self.assertEqual(encode_place_selection(d, [(0, 4, 0)]), b'\x00\x04\x00')
        with self.assertRaises(ValueError):
            encode_place_selection(d, [(0, 4, 1)])

    def test_extract_rejects_two_prompts(self):
        a = bytes([13, 0]) + struct.pack('<Q', 1)
        b = bytes([13, 1]) + struct.pack('<Q', 2)
        with self.assertRaises(UnsupportedInteraction):
            extract_decision([a, b])


if __name__ == '__main__':
    unittest.main()
