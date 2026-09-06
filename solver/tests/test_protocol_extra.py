import struct
import unittest

from reborn.effects import UnsupportedInteraction
from reborn.protocol_extra import (
    parse_decision, conservative_response,
    encode_tribute_selection, encode_counter_selection,
    encode_sum_selection, encode_sort,
)


class ProtocolExtraTests(unittest.TestCase):
    def test_tribute_counter_and_sum(self):
        msg = bytearray([20, 0, 0]) + struct.pack('<III', 2, 3, 3)
        msg += struct.pack('<IBBIB', 100, 0, 4, 0, 1)
        msg += struct.pack('<IBBIB', 200, 0, 4, 1, 2)
        msg += struct.pack('<IBBIB', 300, 0, 4, 2, 1)
        d = parse_decision(bytes(msg))
        expected = struct.pack('<iI', 2, 1) + b'\x01'
        self.assertEqual(conservative_response(d), expected)
        self.assertEqual(encode_tribute_selection(d, [1]), expected)

        msg = bytearray([22, 1]) + struct.pack('<HHI', 0x10, 3, 2)
        msg += struct.pack('<IBBBH', 100, 1, 4, 0, 2)
        msg += struct.pack('<IBBBH', 200, 1, 8, 1, 4)
        d = parse_decision(bytes(msg))
        self.assertEqual(encode_counter_selection(d, [2, 1]), struct.pack('<hh', 2, 1))
        self.assertEqual(conservative_response(d), struct.pack('<hh', 2, 1))

        msg = bytearray([23, 0, 0]) + struct.pack('<III', 5, 1, 2)
        msg += struct.pack('<I', 1)
        msg += struct.pack('<IBBIII', 10, 0, 4, 0, 1, 2)
        msg += struct.pack('<I', 2)
        msg += struct.pack('<IBBIII', 20, 0, 4, 1, 1, 3)
        msg += struct.pack('<IBBIII', 30, 0, 4, 2, 1, 4)
        d = parse_decision(bytes(msg))
        expected = struct.pack('<iI', 2, 1) + b'\x00'
        self.assertEqual(conservative_response(d), expected)
        self.assertEqual(encode_sum_selection(d, [0]), expected)
        with self.assertRaises(ValueError):
            encode_sum_selection(d, [1])

    def test_sort_unselect_announcements_and_rps(self):
        msg = bytearray([25, 0]) + struct.pack('<I', 2)
        msg += struct.pack('<IBII', 100, 0, 4, 0)
        msg += struct.pack('<IBII', 200, 0, 4, 1)
        d = parse_decision(bytes(msg))
        self.assertEqual(encode_sort(d, None), b'\xff')
        self.assertEqual(encode_sort(d, [1, 0]), b'\x01\x00')

        msg = bytearray([26, 0, 1, 0]) + struct.pack('<II', 1, 2)
        msg += struct.pack('<I', 1)
        msg += struct.pack('<IBBII', 100, 0, 4, 0, 1)
        msg += struct.pack('<I', 0)
        self.assertEqual(conservative_response(parse_decision(bytes(msg))), struct.pack('<i', -1))

        race = bytes([140, 0, 2]) + struct.pack('<Q', 0b1011)
        self.assertEqual(conservative_response(parse_decision(race)), struct.pack('<Q', 3))
        attr = bytes([141, 1, 1]) + struct.pack('<I', 0b10010)
        self.assertEqual(conservative_response(parse_decision(attr)), struct.pack('<I', 2))
        number = bytes([143, 0, 2]) + struct.pack('<QQ', 7, 11)
        self.assertEqual(conservative_response(parse_decision(number)), struct.pack('<i', 0))
        self.assertEqual(conservative_response(parse_decision(bytes([132, 1]))), struct.pack('<i', 1))

    def test_announce_card_stays_strict_until_database_evaluator_exists(self):
        d = parse_decision(bytes([142, 0, 1]) + struct.pack('<Q', 123))
        with self.assertRaises(UnsupportedInteraction):
            conservative_response(d)


if __name__ == '__main__':
    unittest.main()
