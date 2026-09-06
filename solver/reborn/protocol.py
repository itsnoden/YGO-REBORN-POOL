"""Strict parsers/encoders for ocgcore decision messages.

The raw ocgcore message stream is privileged referee data.  Learning policies
must never receive it directly.  This module extracts only the legal prompt for
the acting player and generates responses that the pinned core accepts.

Protocol source: edo9300/ygopro-core commit b8c05dff14da0b13608950a73906287dc0b601f9.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import struct
from typing import Any

from .effects import UnsupportedInteraction

# Decision message IDs from the pinned ocgapi_constants.h.
MSG_SELECT_BATTLECMD = 10
MSG_SELECT_IDLECMD = 11
MSG_SELECT_EFFECTYN = 12
MSG_SELECT_YESNO = 13
MSG_SELECT_OPTION = 14
MSG_SELECT_CARD = 15
MSG_SELECT_CHAIN = 16
MSG_SELECT_PLACE = 18
MSG_SELECT_POSITION = 19
MSG_SELECT_TRIBUTE = 20
MSG_SORT_CHAIN = 21
MSG_SELECT_COUNTER = 22
MSG_SELECT_SUM = 23
MSG_SELECT_DISFIELD = 24
MSG_SORT_CARD = 25
MSG_SELECT_UNSELECT_CARD = 26
MSG_ROCK_PAPER_SCISSORS = 132
MSG_ANNOUNCE_RACE = 140
MSG_ANNOUNCE_ATTRIB = 141
MSG_ANNOUNCE_CARD = 142
MSG_ANNOUNCE_NUMBER = 143

ALL_DECISION_TYPES = {
    MSG_SELECT_BATTLECMD, MSG_SELECT_IDLECMD, MSG_SELECT_EFFECTYN,
    MSG_SELECT_YESNO, MSG_SELECT_OPTION, MSG_SELECT_CARD, MSG_SELECT_CHAIN,
    MSG_SELECT_PLACE, MSG_SELECT_POSITION, MSG_SELECT_TRIBUTE, MSG_SORT_CHAIN,
    MSG_SELECT_COUNTER, MSG_SELECT_SUM, MSG_SELECT_DISFIELD, MSG_SORT_CARD,
    MSG_SELECT_UNSELECT_CARD, MSG_ROCK_PAPER_SCISSORS, MSG_ANNOUNCE_RACE,
    MSG_ANNOUNCE_ATTRIB, MSG_ANNOUNCE_CARD, MSG_ANNOUNCE_NUMBER,
}

LOCATION_MZONE = 0x04
LOCATION_SZONE = 0x08


class Reader:
    def __init__(self, data: bytes):
        self.data = memoryview(data)
        self.pos = 0

    def _take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ValueError("truncated ocgcore decision message")
        out = self.data[self.pos:self.pos+n].tobytes()
        self.pos += n
        return out

    def u8(self) -> int:
        return self._take(1)[0]

    def u32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self._take(8))[0]

    def done(self) -> None:
        if self.pos != len(self.data):
            raise ValueError(f"unexpected trailing bytes: {len(self.data) - self.pos}")


@dataclass(frozen=True)
class CardRef:
    code: int
    controller: int
    location: int
    sequence: int
    position: int | None = None

    def public(self) -> dict[str, int]:
        out = {
            "code": self.code,
            "controller": self.controller,
            "location": self.location,
            "sequence": self.sequence,
        }
        if self.position is not None:
            out["position"] = self.position
        return out


@dataclass(frozen=True)
class Action:
    label: str
    response: bytes
    card: CardRef | None = None
    description: int | None = None
    client_mode: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    kind: str
    player: int
    actions: tuple[Action, ...] = ()
    cards: tuple[CardRef, ...] = ()
    minimum: int = 0
    maximum: int = 0
    cancelable: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def view_for(self, viewer: int) -> dict[str, Any]:
        """Return policy input only to the player who owns this prompt."""
        if viewer != self.player:
            raise UnsupportedInteraction(
                f"decision for player {self.player} cannot be observed by player {viewer}"
            )
        return {
            "kind": self.kind,
            "player": self.player,
            "actions": [
                {
                    "label": a.label,
                    **({"card": a.card.public()} if a.card else {}),
                    **({"description": a.description} if a.description is not None else {}),
                    **({"client_mode": a.client_mode} if a.client_mode is not None else {}),
                    **a.extra,
                }
                for a in self.actions
            ],
            "cards": [c.public() for c in self.cards],
            "minimum": self.minimum,
            "maximum": self.maximum,
            "cancelable": self.cancelable,
            "meta": dict(self.meta),
        }


def _loc(r: Reader) -> tuple[int, int, int, int]:
    return r.u8(), r.u8(), r.u32(), r.u32()


def _card_loc(r: Reader) -> CardRef:
    code = r.u32()
    controller, location, sequence, position = _loc(r)
    return CardRef(code, controller, location, sequence, position)


def _simple_card(r: Reader, sequence_u32: bool = True) -> CardRef:
    code = r.u32()
    controller = r.u8()
    location = r.u8()
    sequence = r.u32() if sequence_u32 else r.u8()
    return CardRef(code, controller, location, sequence)


def _command_response(kind: int, index: int = 0) -> bytes:
    if not (0 <= kind <= 0xFFFF and 0 <= index <= 0xFFFF):
        raise ValueError("command response out of range")
    return struct.pack("<I", kind | (index << 16))


def _parse_idle(r: Reader) -> Decision:
    player = r.u8()
    actions: list[Action] = []
    groups = [
        ("normal_summon", 0, True),
        ("special_summon", 1, True),
        ("change_position", 2, False),
        ("set_monster", 3, True),
        ("set_spell_trap", 4, True),
    ]
    for label, cmd, sequence_u32 in groups:
        count = r.u32()
        for i in range(count):
            card = _simple_card(r, sequence_u32=sequence_u32)
            actions.append(Action(label, _command_response(cmd, i), card=card))
    count = r.u32()
    for i in range(count):
        card = _simple_card(r, sequence_u32=True)
        desc = r.u64()
        mode = r.u8()
        actions.append(Action("activate", _command_response(5, i), card, desc, mode))
    to_bp, to_ep, can_shuffle = r.u8(), r.u8(), r.u8()
    if to_bp:
        actions.append(Action("battle_phase", _command_response(6)))
    if to_ep:
        actions.append(Action("end_phase", _command_response(7)))
    if can_shuffle:
        actions.append(Action("shuffle_hand", _command_response(8)))
    r.done()
    if not actions:
        raise UnsupportedInteraction("MSG_SELECT_IDLECMD contained no legal actions")
    return Decision("idle", player, tuple(actions), meta={
        "to_battle_phase": bool(to_bp),
        "to_end_phase": bool(to_ep),
        "can_shuffle_hand": bool(can_shuffle),
    })


def _parse_battle(r: Reader) -> Decision:
    player = r.u8()
    actions: list[Action] = []
    count = r.u32()
    for i in range(count):
        card = _simple_card(r, sequence_u32=True)
        desc = r.u64()
        mode = r.u8()
        actions.append(Action("activate", _command_response(0, i), card, desc, mode))
    count = r.u32()
    for i in range(count):
        code = r.u32()
        controller, location, sequence, direct = r.u8(), r.u8(), r.u8(), r.u8()
        card = CardRef(code, controller, location, sequence)
        actions.append(Action("attack", _command_response(1, i), card=card,
                              extra={"direct_attackable": bool(direct)}))
    to_m2, to_ep = r.u8(), r.u8()
    if to_m2:
        actions.append(Action("main_phase_2", _command_response(2)))
    if to_ep:
        actions.append(Action("end_phase", _command_response(3)))
    r.done()
    if not actions:
        raise UnsupportedInteraction("MSG_SELECT_BATTLECMD contained no legal actions")
    return Decision("battle", player, tuple(actions), meta={
        "to_main_phase_2": bool(to_m2), "to_end_phase": bool(to_ep)
    })


def _parse_effect_yesno(r: Reader) -> Decision:
    player = r.u8()
    card = _card_loc(r)
    desc = r.u64()
    r.done()
    return Decision("effect_yesno", player, (
        Action("no", struct.pack("<i", 0), card, desc),
        Action("yes", struct.pack("<i", 1), card, desc),
    ))


def _parse_yesno(r: Reader) -> Decision:
    player = r.u8()
    desc = r.u64()
    r.done()
    return Decision("yesno", player, (
        Action("no", struct.pack("<i", 0), description=desc),
        Action("yes", struct.pack("<i", 1), description=desc),
    ))


def _parse_option(r: Reader) -> Decision:
    player = r.u8()
    count = r.u8()
    actions = tuple(
        Action("option", struct.pack("<i", i), description=r.u64(), extra={"index": i})
        for i in range(count)
    )
    r.done()
    if not actions:
        raise UnsupportedInteraction("empty MSG_SELECT_OPTION")
    return Decision("option", player, actions)


def _parse_card(r: Reader) -> Decision:
    player = r.u8()
    cancelable = bool(r.u8())
    minimum, maximum, count = r.u32(), r.u32(), r.u32()
    cards = tuple(_card_loc(r) for _ in range(count))
    r.done()
    if maximum > count or minimum > maximum:
        raise ValueError("invalid MSG_SELECT_CARD bounds")
    return Decision("select_card", player, cards=cards, minimum=minimum,
                    maximum=maximum, cancelable=cancelable)


def encode_card_selection(decision: Decision, indices: list[int] | tuple[int, ...] | None) -> bytes:
    if decision.kind != "select_card":
        raise ValueError("not a select-card decision")
    if indices is None:
        if not decision.cancelable:
            raise ValueError("selection is not cancelable")
        return struct.pack("<i", -1)
    indices = list(indices)
    if not (decision.minimum <= len(indices) <= decision.maximum):
        raise ValueError("selection count out of bounds")
    if len(set(indices)) != len(indices):
        raise ValueError("duplicate selection index")
    if any(i < 0 or i >= len(decision.cards) or i > 255 for i in indices):
        raise ValueError("selection index out of range")
    # Pinned core parse_response_cards type 2: u8 indices after 8-byte header.
    return struct.pack("<iI", 2, len(indices)) + bytes(indices)


def _parse_chain(r: Reader) -> Decision:
    player = r.u8()
    spe_count, forced = r.u8(), bool(r.u8())
    hint_self, hint_other, count = r.u32(), r.u32(), r.u32()
    actions: list[Action] = []
    for i in range(count):
        card = _card_loc(r)
        desc = r.u64()
        mode = r.u8()
        actions.append(Action("chain", struct.pack("<i", i), card, desc, mode,
                              {"index": i}))
    if not forced:
        actions.insert(0, Action("pass_chain", struct.pack("<i", -1)))
    r.done()
    if forced and not count:
        raise ValueError("forced chain prompt has no chain")
    return Decision("chain", player, tuple(actions), meta={
        "special_count": spe_count, "forced": forced,
        "hint_timing_self": hint_self, "hint_timing_other": hint_other,
    })


def _allowed_places(player: int, flag: int) -> list[tuple[int, int, int]]:
    # field::process(SelectPlace) treats flag as forbidden locations.  The bit
    # layout is relative to the selecting player:
    #   bits 0..7 own MZONE, 8..15 own SZONE,
    #   16..23 opponent MZONE, 24..31 opponent SZONE.
    out: list[tuple[int, int, int]] = []
    for rel_player, base in ((player, 0), (1-player, 16)):
        for loc, shift, max_seq in ((LOCATION_MZONE, base, 6), (LOCATION_SZONE, base+8, 7)):
            for seq in range(max_seq + 1):
                if not (flag & (1 << (shift + seq))):
                    out.append((rel_player, loc, seq))
    return out


def _parse_place(r: Reader, disable: bool) -> Decision:
    player, count, flag = r.u8(), r.u8(), r.u32()
    r.done()
    places = _allowed_places(player, flag)
    if len(places) < count:
        raise ValueError("place prompt has fewer allowed zones than requested")
    return Decision("disable_field" if disable else "select_place", player,
                    minimum=count, maximum=count,
                    meta={"flag": flag, "places": places})


def encode_place_selection(decision: Decision, places: list[tuple[int, int, int]]) -> bytes:
    if decision.kind not in {"select_place", "disable_field"}:
        raise ValueError("not a place decision")
    allowed = {tuple(p) for p in decision.meta["places"]}
    places = [tuple(p) for p in places]
    if len(places) != decision.minimum or len(set(places)) != len(places):
        raise ValueError("wrong number of unique places")
    if any(p not in allowed for p in places):
        raise ValueError("selected forbidden place")
    return b"".join(bytes((p, loc, seq)) for p, loc, seq in places)


def _parse_position(r: Reader) -> Decision:
    player, code, positions = r.u8(), r.u32(), r.u8()
    r.done()
    legal = [bit for bit in (0x1, 0x2, 0x4, 0x8) if positions & bit]
    if not legal:
        raise ValueError("position prompt has no legal positions")
    return Decision("position", player, tuple(
        Action("position", struct.pack("<i", bit),
               extra={"position": bit, "code": code})
        for bit in legal
    ), meta={"code": code, "positions": positions})


PARSERS = {
    MSG_SELECT_IDLECMD: _parse_idle,
    MSG_SELECT_BATTLECMD: _parse_battle,
    MSG_SELECT_EFFECTYN: _parse_effect_yesno,
    MSG_SELECT_YESNO: _parse_yesno,
    MSG_SELECT_OPTION: _parse_option,
    MSG_SELECT_CARD: _parse_card,
    MSG_SELECT_CHAIN: _parse_chain,
    MSG_SELECT_PLACE: lambda r: _parse_place(r, False),
    MSG_SELECT_DISFIELD: lambda r: _parse_place(r, True),
    MSG_SELECT_POSITION: _parse_position,
}


def parse_decision(message: bytes) -> Decision:
    if not message:
        raise ValueError("empty message")
    msg_type = message[0]
    if msg_type not in ALL_DECISION_TYPES:
        raise ValueError(f"not a decision message: {msg_type}")
    parser = PARSERS.get(msg_type)
    if parser is None:
        raise UnsupportedInteraction(f"unsupported decision message {msg_type}")
    return parser(Reader(message[1:]))


def extract_decision(messages: list[bytes] | tuple[bytes, ...]) -> Decision | None:
    decision_messages = [m for m in messages if m and m[0] in ALL_DECISION_TYPES]
    if not decision_messages:
        return None
    if len(decision_messages) != 1:
        raise UnsupportedInteraction(
            f"expected one decision message, received {len(decision_messages)}"
        )
    return parse_decision(decision_messages[0])


def conservative_response(decision: Decision) -> bytes:
    """Deterministic legal baseline used only to exercise complete game flow.

    This is intentionally not a strength policy and must never be used as deck
    evidence.  It prefers passing/ending phases and otherwise the first legal
    option so protocol regressions are easy to reproduce.
    """
    if decision.kind == "select_card":
        return encode_card_selection(decision, list(range(decision.minimum)))
    if decision.kind in {"select_place", "disable_field"}:
        return encode_place_selection(
            decision, list(decision.meta["places"][:decision.minimum])
        )
    preferred = (
        "pass_chain", "end_phase", "main_phase_2", "battle_phase",
        "no", "option", "position", "attack", "activate",
        "normal_summon", "special_summon", "change_position",
        "set_monster", "set_spell_trap", "shuffle_hand", "chain",
    )
    for label in preferred:
        for action in decision.actions:
            if action.label == label:
                return action.response
    if decision.actions:
        return decision.actions[0].response
    raise UnsupportedInteraction(f"no response strategy for {decision.kind}")
