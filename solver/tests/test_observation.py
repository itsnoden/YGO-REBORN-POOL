import struct
import unittest
from unittest.mock import patch

from reborn.observation import (
    PublicTracker, parse_card_query, parse_field_query, _identity_for,
    QUERY_CODE, QUERY_POSITION, QUERY_IS_PUBLIC, QUERY_IS_HIDDEN, QUERY_END,
    LOCATION_HAND, LOCATION_MZONE,
)


def item(tag, payload):
    return struct.pack('<HI', 4 + len(payload), tag) + payload


def card_query(code=123, position=8, public=False, hidden=False):
    return b''.join([
        item(QUERY_CODE, struct.pack('<I', code)),
        item(QUERY_POSITION, struct.pack('<I', position)),
        item(QUERY_IS_PUBLIC, bytes([public])),
        item(QUERY_IS_HIDDEN, bytes([hidden])),
        item(QUERY_END, b''),
    ])


class ObservationTests(unittest.TestCase):
    def test_card_query_tlv_and_public_flags(self):
        parsed = parse_card_query(card_query(777, 1, True, False))
        self.assertEqual(parsed['code'], 777)
        self.assertEqual(parsed['position'], 1)
        self.assertTrue(parsed['is_public'])
        self.assertFalse(parsed['is_hidden'])

    def test_identity_filter_never_leaks_opponent_hidden_card(self):
        with patch('reborn.observation.raw_query_card', return_value=card_query(999, 8, False, False)):
            hidden = _identity_for(object(), 0, 1, LOCATION_HAND, 0)
            self.assertNotIn('code', hidden)
        with patch('reborn.observation.raw_query_card', return_value=card_query(999, 1, True, False)):
            revealed = _identity_for(object(), 0, 1, LOCATION_HAND, 0)
            self.assertEqual(revealed['code'], 999)
        with patch('reborn.observation.raw_query_card', return_value=card_query(999, 1, True, True)):
            darkness_hidden = _identity_for(object(), 0, 1, LOCATION_MZONE, 0)
            self.assertNotIn('code', darkness_hidden)
        with patch('reborn.observation.raw_query_card', return_value=card_query(999, 8, False, False)):
            own_set = _identity_for(object(), 0, 0, LOCATION_MZONE, 0)
            self.assertEqual(own_set['code'], 999)

    def test_public_tracker(self):
        tracker = PublicTracker()
        tracker.consume([bytes([40, 1]), bytes([41]) + struct.pack('<H', 4)])
        self.assertEqual(tracker.turn_player, 1)
        self.assertEqual(tracker.turn_number, 1)
        self.assertEqual(tracker.phase, 4)

    def test_field_query_layout(self):
        data = bytearray(struct.pack('<I', 0x1234))
        for player in range(2):
            data += struct.pack('<I', 8000 - player * 1000)
            for sequence in range(7):
                if player == 0 and sequence == 0:
                    data += bytes([1, 1]) + struct.pack('<I', 2)
                else:
                    data += b'\x00'
            for sequence in range(8):
                if player == 1 and sequence == 4:
                    data += bytes([1, 8]) + struct.pack('<I', 0)
                else:
                    data += b'\x00'
            data += struct.pack('<IIIIII', 35, 5, 0, 0, 0, 0)
        data += struct.pack('<I', 1)
        data += struct.pack('<IBBII', 321, 0, 4, 0, 1)
        data += struct.pack('<BBIQ', 0, 4, 0, 456)
        parsed = parse_field_query(bytes(data))
        self.assertEqual(parsed['duel_options'], 0x1234)
        self.assertEqual(parsed['players'][0]['lp'], 8000)
        self.assertEqual(parsed['players'][0]['mzone'][0]['overlay_count'], 2)
        self.assertEqual(parsed['players'][1]['szone'][4]['position'], 8)
        self.assertEqual(parsed['chains'][0]['code'], 321)
        self.assertEqual(parsed['chains'][0]['description'], 456)


if __name__ == '__main__':
    unittest.main()
