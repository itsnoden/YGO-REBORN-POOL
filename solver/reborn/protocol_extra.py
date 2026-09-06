"""Extended strict ocgcore decision coverage.

This module layers less-common decision families on top of ``reborn.protocol``.
All layouts are derived from the exact pinned ygopro-core commit recorded in
engine.lock.json. Unsupported semantics abort rather than guess.
"""
from __future__ import annotations

from itertools import combinations
import struct

from .effects import UnsupportedInteraction
from . import protocol as base

Action = base.Action
Decision = base.Decision
CardRef = base.CardRef

EXTRA_TYPES = {
    base.MSG_SELECT_TRIBUTE,
    base.MSG_SORT_CHAIN,
    base.MSG_SELECT_COUNTER,
    base.MSG_SELECT_SUM,
    base.MSG_SORT_CARD,
    base.MSG_SELECT_UNSELECT_CARD,
    base.MSG_ROCK_PAPER_SCISSORS,
    base.MSG_ANNOUNCE_RACE,
    base.MSG_ANNOUNCE_ATTRIB,
    base.MSG_ANNOUNCE_CARD,
    base.MSG_ANNOUNCE_NUMBER,
}


class Reader(base.Reader):
    def u16(self) -> int:
        return struct.unpack('<H', self._take(2))[0]


def _loc(r: Reader):
    return r.u8(), r.u8(), r.u32(), r.u32()


def _card_loc(r: Reader) -> CardRef:
    code = r.u32()
    controller, location, sequence, position = _loc(r)
    return CardRef(code, controller, location, sequence, position)


def _simple_card(r: Reader, sequence_u32=True) -> CardRef:
    code = r.u32(); controller = r.u8(); location = r.u8()
    sequence = r.u32() if sequence_u32 else r.u8()
    return CardRef(code, controller, location, sequence)


def _index_vector(indices):
    indices = list(indices)
    if len(set(indices)) != len(indices):
        raise ValueError('duplicate selection index')
    if any(i < 0 or i > 255 for i in indices):
        raise ValueError('selection index out of u8 range')
    return struct.pack('<iI', 2, len(indices)) + bytes(indices)


def _parse_tribute(r: Reader) -> Decision:
    player = r.u8(); cancelable = bool(r.u8())
    minimum, maximum, count = r.u32(), r.u32(), r.u32()
    cards, release = [], []
    for _ in range(count):
        cards.append(_simple_card(r, True)); release.append(r.u8())
    r.done()
    if minimum > maximum:
        raise ValueError('invalid tribute bounds')
    return Decision('tribute', player, cards=tuple(cards), minimum=minimum,
                    maximum=maximum, cancelable=cancelable,
                    meta={'release_values': release})


def encode_tribute_selection(decision, indices):
    if decision.kind != 'tribute':
        raise ValueError('not a tribute decision')
    if indices is None:
        if not decision.cancelable:
            raise ValueError('tribute selection is not cancelable')
        return struct.pack('<i', -1)
    indices = list(indices)
    if len(indices) > decision.maximum:
        raise ValueError('too many tribute cards')
    if any(i < 0 or i >= len(decision.cards) for i in indices):
        raise ValueError('tribute index out of range')
    if sum(decision.meta['release_values'][i] for i in indices) < decision.minimum:
        raise ValueError('insufficient tribute value')
    return _index_vector(indices)


def _parse_counter(r: Reader) -> Decision:
    player, counter_type, total, count = r.u8(), r.u16(), r.u16(), r.u32()
    cards, available = [], []
    for _ in range(count):
        code = r.u32(); controller = r.u8(); location = r.u8(); sequence = r.u8(); amount = r.u16()
        cards.append(CardRef(code, controller, location, sequence)); available.append(amount)
    r.done()
    if total > sum(available):
        raise ValueError('counter request exceeds available counters')
    return Decision('counter', player, cards=tuple(cards), minimum=total, maximum=total,
                    meta={'counter_type': counter_type, 'available': available})


def encode_counter_selection(decision, counts):
    if decision.kind != 'counter':
        raise ValueError('not a counter decision')
    counts = list(counts); available = decision.meta['available']
    if len(counts) != len(available):
        raise ValueError('counter response length mismatch')
    if any(c < 0 or c > a or c > 32767 for c, a in zip(counts, available)):
        raise ValueError('invalid counter allocation')
    if sum(counts) != decision.minimum:
        raise ValueError('counter allocation total mismatch')
    return b''.join(struct.pack('<h', c) for c in counts)


def _parse_sum(r: Reader) -> Decision:
    player, mode = r.u8(), r.u8()
    acc, minimum, maximum = r.u32(), r.u32(), r.u32()
    must_cards, must_params = [], []
    for _ in range(r.u32()):
        must_cards.append(_card_loc(r)); must_params.append(r.u32())
    cards, params = [], []
    for _ in range(r.u32()):
        cards.append(_card_loc(r)); params.append(r.u32())
    r.done()
    if mode not in (0, 1):
        raise ValueError('unknown select-sum mode')
    return Decision('select_sum', player, cards=tuple(cards), minimum=minimum,
                    maximum=maximum, meta={
                        'mode': mode, 'accumulator': acc,
                        'must_cards': [c.public() for c in must_cards],
                        'must_params': must_params, 'sum_params': params,
                    })


def _sum_choices(param):
    a, b = param & 0xffff, param >> 16
    return (a,) if not b or b == a else (a, b)


def _sum_exact_subset(decision):
    acc = decision.meta['accumulator']; must = decision.meta['must_params']; params = decision.meta['sum_params']
    reachable = {0}
    for param in must:
        reachable = {s + v for s in reachable for v in _sum_choices(param) if s + v <= acc}
    max_count = min(decision.maximum, len(params))
    states = {(0, s): () for s in reachable}
    for idx, param in enumerate(params):
        nxt = dict(states)
        for (count, total), subset in states.items():
            if count >= max_count: continue
            for value in _sum_choices(param):
                new_total = total + value
                if new_total <= acc:
                    nxt.setdefault((count + 1, new_total), subset + (idx,))
        states = nxt
    for count in range(decision.minimum, max_count + 1):
        subset = states.get((count, acc))
        if subset is not None: return list(subset)
    return None


def _at_least_valid(params, acc):
    if not params: return False
    min_sum = 0; max_sum = 0; min_component = 0x7fffffff
    for param in params:
        a, b = param & 0xffff, param >> 16
        ms = b if b and b < a else a
        min_sum += ms; max_sum += max(a, b); min_component = min(min_component, ms)
    return max_sum >= acc and min_sum - min_component < acc


def _sum_at_least_subset(decision, node_limit=200000):
    acc = decision.meta['accumulator']; must = decision.meta['must_params']; params = decision.meta['sum_params']
    nodes = 0
    for size in range(len(params) + 1):
        for subset in combinations(range(len(params)), size):
            nodes += 1
            if nodes > node_limit:
                raise UnsupportedInteraction('select-sum search exceeded strict node limit')
            if _at_least_valid(must + [params[i] for i in subset], acc):
                return list(subset)
    return None


def encode_sum_selection(decision, indices):
    if decision.kind != 'select_sum': raise ValueError('not a select-sum decision')
    indices = list(indices)
    if len(set(indices)) != len(indices) or any(i < 0 or i >= len(decision.cards) for i in indices):
        raise ValueError('sum index out of range')
    params = decision.meta['must_params'] + [decision.meta['sum_params'][i] for i in indices]
    acc = decision.meta['accumulator']
    if decision.meta['mode'] == 0:
        if not (decision.minimum <= len(indices) <= decision.maximum):
            raise ValueError('sum selection count out of bounds')
        reachable = {0}
        for param in params:
            reachable = {s + v for s in reachable for v in _sum_choices(param) if s + v <= acc}
        if acc not in reachable: raise ValueError('sum selection does not reach accumulator')
    elif not _at_least_valid(params, acc):
        raise ValueError('sum selection fails core at-least rule')
    return _index_vector(indices)


def _parse_sort(r: Reader, is_chain) -> Decision:
    player, count = r.u8(), r.u32(); cards = []
    for _ in range(count):
        cards.append(CardRef(r.u32(), r.u8(), r.u32(), r.u32()))
    r.done()
    return Decision('sort_chain' if is_chain else 'sort_card', player,
                    actions=(Action('keep_order', b'\xff'),), cards=tuple(cards), meta={'count': count})


def encode_sort(decision, order):
    if decision.kind not in {'sort_chain', 'sort_card'}: raise ValueError('not a sort decision')
    if order is None: return b'\xff'
    order = list(order)
    if sorted(order) != list(range(len(decision.cards))) or len(order) > 127:
        raise ValueError('invalid sort permutation')
    return bytes(order)


def _parse_unselect(r: Reader) -> Decision:
    player, finishable, cancelable = r.u8(), bool(r.u8()), bool(r.u8())
    minimum, maximum = r.u32(), r.u32()
    selectable = tuple(_card_loc(r) for _ in range(r.u32()))
    unselectable = tuple(_card_loc(r) for _ in range(r.u32()))
    r.done(); actions = []
    if finishable or cancelable:
        actions.append(Action('finish' if finishable else 'cancel', struct.pack('<i', -1)))
    for i, card in enumerate(selectable + unselectable):
        actions.append(Action('toggle_card', struct.pack('<ii', 1, i), card=card,
                              extra={'index': i, 'currently_selected': i >= len(selectable)}))
    return Decision('select_unselect', player, tuple(actions), selectable + unselectable,
                    minimum, maximum, cancelable,
                    meta={'finishable': finishable, 'selectable_count': len(selectable)})


def _parse_announce_race(r: Reader) -> Decision:
    player, count, available = r.u8(), r.u8(), r.u64(); r.done()
    if count > available.bit_count(): raise ValueError('announce-race count exceeds available races')
    return Decision('announce_race', player, minimum=count, maximum=count, meta={'available': available})


def _parse_announce_attribute(r: Reader) -> Decision:
    player, count, available = r.u8(), r.u8(), r.u32(); r.done()
    if count > available.bit_count(): raise ValueError('announce-attribute count exceeds available attributes')
    return Decision('announce_attribute', player, minimum=count, maximum=count, meta={'available': available})


def _lowest_bits(mask, count):
    out = 0
    while count:
        bit = mask & -mask
        if not bit: raise ValueError('not enough bits')
        out |= bit; mask ^= bit; count -= 1
    return out


def _parse_announce_card(r: Reader) -> Decision:
    player, count = r.u8(), r.u8(); opcodes = [r.u64() for _ in range(count)]; r.done()
    return Decision('announce_card', player, meta={'opcodes': opcodes})


def _parse_announce_number(r: Reader) -> Decision:
    player, count = r.u8(), r.u8(); options = [r.u64() for _ in range(count)]; r.done()
    actions = tuple(Action('number', struct.pack('<i', i), extra={'index': i, 'value': value})
                    for i, value in enumerate(options))
    if not actions: raise UnsupportedInteraction('empty announce-number prompt')
    return Decision('announce_number', player, actions, meta={'options': options})


def _parse_rps(r: Reader) -> Decision:
    player = r.u8(); r.done()
    return Decision('rock_paper_scissors', player, (
        Action('rock', struct.pack('<i', 1)),
        Action('paper', struct.pack('<i', 2)),
        Action('scissors', struct.pack('<i', 3)),
    ))


PARSERS = {
    base.MSG_SELECT_TRIBUTE: _parse_tribute,
    base.MSG_SELECT_COUNTER: _parse_counter,
    base.MSG_SELECT_SUM: _parse_sum,
    base.MSG_SORT_CHAIN: lambda r: _parse_sort(r, True),
    base.MSG_SORT_CARD: lambda r: _parse_sort(r, False),
    base.MSG_SELECT_UNSELECT_CARD: _parse_unselect,
    base.MSG_ANNOUNCE_RACE: _parse_announce_race,
    base.MSG_ANNOUNCE_ATTRIB: _parse_announce_attribute,
    base.MSG_ANNOUNCE_CARD: _parse_announce_card,
    base.MSG_ANNOUNCE_NUMBER: _parse_announce_number,
    base.MSG_ROCK_PAPER_SCISSORS: _parse_rps,
}


def parse_decision(message):
    if not message: raise ValueError('empty message')
    parser = PARSERS.get(message[0])
    return parser(Reader(message[1:])) if parser else base.parse_decision(message)


def extract_decision(messages):
    decision_messages = [m for m in messages if m and m[0] in base.ALL_DECISION_TYPES]
    if not decision_messages: return None
    if len(decision_messages) != 1:
        raise UnsupportedInteraction(f'expected one decision message, received {len(decision_messages)}')
    return parse_decision(decision_messages[0])


def conservative_response(decision):
    if decision.kind == 'tribute':
        if decision.cancelable: return encode_tribute_selection(decision, None)
        release = decision.meta['release_values']
        for size in range(1, min(decision.maximum, len(release)) + 1):
            for subset in combinations(range(len(release)), size):
                if sum(release[i] for i in subset) >= decision.minimum:
                    return encode_tribute_selection(decision, subset)
        raise UnsupportedInteraction('no legal tribute subset found')
    if decision.kind == 'counter':
        remaining = decision.minimum; counts = []
        for available in decision.meta['available']:
            take = min(available, remaining); counts.append(take); remaining -= take
        if remaining: raise UnsupportedInteraction('counter allocation unexpectedly impossible')
        return encode_counter_selection(decision, counts)
    if decision.kind == 'select_sum':
        subset = _sum_exact_subset(decision) if decision.meta['mode'] == 0 else _sum_at_least_subset(decision)
        if subset is None: raise UnsupportedInteraction('no legal select-sum subset found')
        return encode_sum_selection(decision, subset)
    if decision.kind in {'sort_chain', 'sort_card'}: return encode_sort(decision, None)
    if decision.kind == 'select_unselect':
        if decision.meta['finishable'] or decision.cancelable: return struct.pack('<i', -1)
        for action in decision.actions:
            if action.label == 'toggle_card': return action.response
        raise UnsupportedInteraction('select-unselect prompt has no legal response')
    if decision.kind == 'announce_race':
        return struct.pack('<Q', _lowest_bits(decision.meta['available'], decision.minimum))
    if decision.kind == 'announce_attribute':
        return struct.pack('<I', _lowest_bits(decision.meta['available'], decision.minimum))
    if decision.kind == 'announce_card':
        raise UnsupportedInteraction('announce-card requires database-backed opcode evaluation')
    if decision.kind == 'announce_number': return decision.actions[0].response
    if decision.kind == 'rock_paper_scissors': return decision.actions[0].response
    return base.conservative_response(decision)
