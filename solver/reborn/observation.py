"""Information-safe observation queries for the pinned ocgcore ABI.

ocgcore is a referee and can reveal hidden identities through its query API.  This
module is the policy boundary: it copies referee data, parses the exact pinned
wire format, then releases card codes only when the viewing player is entitled
to know them.  Never pass raw query bytes to a pilot.
"""
from __future__ import annotations

import ctypes as C
import struct
from dataclasses import dataclass

from .effects import UnsupportedInteraction

U8 = C.c_uint8
U32 = C.c_uint32
PTR = C.c_void_p

LOCATION_DECK = 0x01
LOCATION_HAND = 0x02
LOCATION_MZONE = 0x04
LOCATION_SZONE = 0x08
LOCATION_GRAVE = 0x10
LOCATION_REMOVED = 0x20
LOCATION_EXTRA = 0x40
LOCATION_OVERLAY = 0x80

POS_FACEUP_ATTACK = 0x1
POS_FACEDOWN_ATTACK = 0x2
POS_FACEUP_DEFENSE = 0x4
POS_FACEDOWN_DEFENSE = 0x8
POS_FACEUP = POS_FACEUP_ATTACK | POS_FACEUP_DEFENSE
POS_FACEDOWN = POS_FACEDOWN_ATTACK | POS_FACEDOWN_DEFENSE

QUERY_CODE = 0x1
QUERY_POSITION = 0x2
QUERY_IS_PUBLIC = 0x100000
QUERY_IS_HIDDEN = 0x1000000
QUERY_END = 0x80000000
SAFE_QUERY_FLAGS = QUERY_CODE | QUERY_POSITION | QUERY_IS_PUBLIC | QUERY_IS_HIDDEN

MSG_NEW_TURN = 40
MSG_NEW_PHASE = 41

MZONE_SLOTS = 7
SZONE_SLOTS = 8


class QueryInfo(C.Structure):
    _fields_ = [
        ('flags', U32),
        ('con', U8),
        ('loc', U32),
        ('seq', U32),
        ('overlay_seq', U32),
    ]


class Reader:
    def __init__(self, data: bytes):
        self.data = memoryview(data)
        self.pos = 0

    def _take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError('truncated query buffer')
        out = self.data[self.pos:self.pos+n].tobytes(); self.pos += n
        return out

    def u8(self): return self._take(1)[0]
    def u16(self): return struct.unpack('<H', self._take(2))[0]
    def u32(self): return struct.unpack('<I', self._take(4))[0]
    def u64(self): return struct.unpack('<Q', self._take(8))[0]

    def done(self):
        if self.pos != len(self.data):
            raise ValueError(f'unexpected trailing query bytes: {len(self.data)-self.pos}')


@dataclass
class PublicTracker:
    """Public turn/phase facts derived only from broadcast engine messages."""
    turn_player: int | None = None
    phase: int | None = None
    turn_number: int = 0

    def consume(self, messages):
        for message in messages:
            if not message: continue
            if message[0] == MSG_NEW_TURN:
                if len(message) != 2 or message[1] > 1:
                    raise ValueError('malformed MSG_NEW_TURN')
                self.turn_player = message[1]
                self.turn_number += 1
                self.phase = None
            elif message[0] == MSG_NEW_PHASE:
                if len(message) != 3:
                    raise ValueError('malformed MSG_NEW_PHASE')
                self.phase = struct.unpack_from('<H', message, 1)[0]
        return self


def _bind(duel):
    lib = duel.lib
    lib.OCG_DuelQuery.argtypes = [PTR, C.POINTER(U32), C.POINTER(QueryInfo)]
    lib.OCG_DuelQuery.restype = PTR
    lib.OCG_DuelQueryField.argtypes = [PTR, C.POINTER(U32)]
    lib.OCG_DuelQueryField.restype = PTR
    return lib


def raw_query_card(duel, controller, location, sequence, flags=SAFE_QUERY_FLAGS, overlay_sequence=0):
    """Privileged referee query; callers must filter before exposing it."""
    if controller not in (0, 1): raise ValueError('invalid controller')
    info = QueryInfo(flags, controller, location, sequence, overlay_sequence)
    size = U32(); ptr = _bind(duel).OCG_DuelQuery(duel.handle, C.byref(size), C.byref(info))
    if not ptr or not size.value: return b''
    return C.string_at(ptr, size.value)


def raw_query_field(duel):
    """Privileged field skeleton; copied immediately from ocgcore storage."""
    size = U32(); ptr = _bind(duel).OCG_DuelQueryField(duel.handle, C.byref(size))
    if not ptr or not size.value: raise UnsupportedInteraction('empty OCG_DuelQueryField result')
    return C.string_at(ptr, size.value)


def parse_card_query(data: bytes):
    """Parse ocgcore's length/tag/value query records for the safe flag subset."""
    if not data: return None
    r = Reader(data); out = {}
    while r.pos < len(r.data):
        length = r.u16()
        if length < 4: raise ValueError('invalid card-query record length')
        tag = r.u32(); payload_len = length - 4
        payload = r._take(payload_len)
        if tag == QUERY_END:
            if payload: raise ValueError('QUERY_END has payload')
            r.done(); return out
        if tag in (QUERY_CODE, QUERY_POSITION):
            if len(payload) != 4: raise ValueError('invalid u32 query payload')
            out['code' if tag == QUERY_CODE else 'position'] = struct.unpack('<I', payload)[0]
        elif tag in (QUERY_IS_PUBLIC, QUERY_IS_HIDDEN):
            if len(payload) != 1: raise ValueError('invalid u8 query payload')
            out['is_public' if tag == QUERY_IS_PUBLIC else 'is_hidden'] = bool(payload[0])
        # Ignore unknown records rather than accidentally exposing their bytes.
    raise ValueError('card query missing QUERY_END')


def parse_field_query(data: bytes):
    """Parse the exact ABI-11 OCG_DuelQueryField layout from the pinned core."""
    r = Reader(data); result = {'duel_options': r.u32(), 'players': []}
    for player in range(2):
        row = {'player': player, 'lp': r.u32(), 'mzone': [], 'szone': []}
        for zone_name, slots in (('mzone', MZONE_SLOTS), ('szone', SZONE_SLOTS)):
            for sequence in range(slots):
                present = r.u8()
                if present not in (0, 1): raise ValueError('invalid field presence byte')
                slot = {'sequence': sequence, 'present': bool(present)}
                if present:
                    slot['position'] = r.u8(); slot['overlay_count'] = r.u32()
                row[zone_name].append(slot)
        names = ('deck_count','hand_count','grave_count','removed_count','extra_count','extra_faceup_count')
        for name in names: row[name] = r.u32()
        result['players'].append(row)
    chains = []
    for index in range(r.u32()):
        chains.append({
            'index': index,
            'code': r.u32(),
            'handler_controller': r.u8(),
            'handler_location': r.u8(),
            'handler_sequence': r.u32(),
            'handler_position': r.u32(),
            'triggering_controller': r.u8(),
            'triggering_location': r.u8(),
            'triggering_sequence': r.u32(),
            'description': r.u64(),
        })
    r.done(); result['chains'] = chains
    return result


def _identity_for(duel, viewer, controller, location, sequence):
    """Return filtered card facts; code is omitted unless legitimately knowable."""
    parsed = parse_card_query(raw_query_card(duel, controller, location, sequence))
    if parsed is None: return None
    result = {k: v for k, v in parsed.items() if k != 'code'}
    hidden = bool(parsed.get('is_hidden', False))
    public = bool(parsed.get('is_public', False))
    own = controller == viewer

    # Never expose deck order/identity from a referee query. Revealed top-deck
    # knowledge must be represented later by explicit public-message tracking.
    can_know = False if location == LOCATION_DECK else (own or public)
    if hidden: can_know = False
    if can_know and 'code' in parsed: result['code'] = parsed['code']
    return result


def observation_for(duel, viewer, tracker=None):
    """Build an information-set observation for one player.

    Public field structure, LP, zone counts and current-chain information are
    shared. Identity queries are filtered per viewer. Opponent hand/face-down
    cards and all deck order remain absent even though the referee can inspect
    them internally.
    """
    if viewer not in (0, 1): raise ValueError('viewer must be player 0 or 1')
    field = parse_field_query(raw_query_field(duel))
    out = {
        'viewer': viewer,
        'duel_options': field['duel_options'],
        'players': [],
        'chains': field['chains'],
    }
    if tracker is not None:
        out.update(turn_player=tracker.turn_player, phase=tracker.phase,
                   turn_number=tracker.turn_number)

    for player, source in enumerate(field['players']):
        row = {k: source[k] for k in ('player','lp','deck_count','hand_count','grave_count',
                                      'removed_count','extra_count','extra_faceup_count')}
        row['mzone'] = []
        for slot in source['mzone']:
            item = dict(slot)
            if slot['present']:
                item['card'] = _identity_for(duel, viewer, player, LOCATION_MZONE, slot['sequence'])
            row['mzone'].append(item)
        row['szone'] = []
        for slot in source['szone']:
            item = dict(slot)
            if slot['present']:
                item['card'] = _identity_for(duel, viewer, player, LOCATION_SZONE, slot['sequence'])
            row['szone'].append(item)

        # Linear zones are ordered by core sequence. Query only identities that
        # can be part of the viewer's information set.
        row['hand'] = []
        if player == viewer:
            row['hand'] = [_identity_for(duel, viewer, player, LOCATION_HAND, i)
                           for i in range(source['hand_count'])]
        else:
            # Publicly revealed opponent hand cards are allowed; hidden entries
            # remain anonymous placeholders so hand size is preserved.
            for i in range(source['hand_count']):
                info = _identity_for(duel, viewer, player, LOCATION_HAND, i)
                row['hand'].append(info if info and 'code' in info else {'hidden': True})

        row['grave'] = [_identity_for(duel, viewer, player, LOCATION_GRAVE, i)
                        for i in range(source['grave_count'])]
        row['removed'] = [_identity_for(duel, viewer, player, LOCATION_REMOVED, i)
                          for i in range(source['removed_count'])]
        row['extra'] = []
        for i in range(source['extra_count']):
            info = _identity_for(duel, viewer, player, LOCATION_EXTRA, i)
            row['extra'].append(info if info and 'code' in info else {'hidden': True})
        out['players'].append(row)
    return out
