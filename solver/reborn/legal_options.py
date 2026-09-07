"""Bounded complete legal-option enumeration for learned pilots.

Raw Decision metadata may contain referee-side helper values (tribute values,
sum parameters, counter capacities). Those values are used only to determine
legality and encode the opaque response. They are never copied into the policy
view. Policy features are built only from the already-filtered prompt plus the
player's information-safe observation.

Enumeration is deliberately all-or-nothing. If the complete legal option set is
larger than ``max_options`` (or its theoretical search space is too large), this
module returns ``None`` and the caller can use a non-learning legal fallback.
This avoids training on a silently biased truncated action set.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations, product
import math
import struct

from .protocol import encode_card_selection, encode_place_selection
from .protocol_extra import (
    encode_counter_selection, encode_sort, encode_sum_selection,
    encode_tribute_selection,
)


@dataclass(frozen=True)
class PolicyOption:
    response: bytes
    view: dict


def _selected_cards(prompt, indices):
    cards = prompt.get('cards', ())
    return [cards[i] for i in indices]


def _option(label, response, **safe):
    return PolicyOption(response=response, view={'label': label, **safe})


def _theoretical_subsets(n, minimum, maximum, cancelable=False):
    maximum = min(maximum, n)
    if minimum < 0 or minimum > maximum:
        return 0
    total = sum(math.comb(n, size) for size in range(minimum, maximum + 1))
    return total + int(cancelable)


def _select_card(decision, prompt, max_options):
    n = len(decision.cards)
    if len(prompt.get('cards', ())) != n:
        raise ValueError('filtered card count differs from referee card count')
    if _theoretical_subsets(n, decision.minimum, decision.maximum, decision.cancelable) > max_options:
        return None
    out = []
    if decision.cancelable:
        out.append(_option('cancel_selection', encode_card_selection(decision, None),
                           selected_cards=[], selected_count=0))
    for size in range(decision.minimum, decision.maximum + 1):
        for subset in combinations(range(n), size):
            out.append(_option('select_cards', encode_card_selection(decision, subset),
                               selected_cards=_selected_cards(prompt, subset),
                               selected_indices=list(subset), selected_count=size))
    return out


def _places(decision, prompt, max_options):
    places = list(prompt.get('meta', {}).get('places', ()))
    if places != list(decision.meta.get('places', ())):
        # Places contain only controller/location/sequence legal-zone facts and
        # are explicitly released by policy_view, so exact agreement is required.
        raise ValueError('filtered place set differs from referee legal places')
    count = decision.minimum
    if math.comb(len(places), count) > max_options:
        return None
    return [
        _option('select_places', encode_place_selection(decision, subset),
                places=[list(p) for p in subset], selected_count=count)
        for subset in combinations(places, count)
    ]


def _tribute(decision, prompt, max_options):
    n = len(decision.cards)
    if len(prompt.get('cards', ())) != n:
        raise ValueError('filtered tribute card count mismatch')
    # Use the raw release values only as a legality oracle; never expose them.
    theoretical = sum(math.comb(n, size) for size in range(0, min(decision.maximum, n) + 1))
    theoretical += int(decision.cancelable)
    if theoretical > max_options:
        return None
    release = decision.meta['release_values']
    out = []
    if decision.cancelable:
        out.append(_option('cancel_tribute', encode_tribute_selection(decision, None),
                           selected_cards=[], selected_count=0))
    for size in range(0, min(decision.maximum, n) + 1):
        for subset in combinations(range(n), size):
            if sum(release[i] for i in subset) < decision.minimum:
                continue
            out.append(_option('select_tributes', encode_tribute_selection(decision, subset),
                               selected_cards=_selected_cards(prompt, subset),
                               selected_indices=list(subset), selected_count=size))
    return out


def _counter(decision, prompt, max_options):
    n = len(decision.cards)
    if len(prompt.get('cards', ())) != n:
        raise ValueError('filtered counter card count mismatch')
    available = list(decision.meta['available'])
    # Product is an upper bound. Falling back when the bound is large is safer
    # than partially enumerating a constrained integer-composition space.
    search_space = math.prod(a + 1 for a in available)
    if search_space > max_options * 8:
        return None
    out = []
    for counts in product(*(range(a + 1) for a in available)):
        if sum(counts) != decision.minimum:
            continue
        selected = [i for i, count in enumerate(counts) if count]
        out.append(_option('allocate_counters', encode_counter_selection(decision, counts),
                           selected_cards=_selected_cards(prompt, selected),
                           selected_indices=selected, allocations=list(counts),
                           selected_count=len(selected)))
        if len(out) > max_options:
            return None
    return out or None


def _select_sum(decision, prompt, max_options):
    n = len(decision.cards)
    if len(prompt.get('cards', ())) != n:
        raise ValueError('filtered sum card count mismatch')
    if 2 ** n > max_options * 8:
        return None
    out = []
    for size in range(n + 1):
        for subset in combinations(range(n), size):
            try:
                response = encode_sum_selection(decision, subset)
            except ValueError:
                continue
            out.append(_option('select_sum_cards', response,
                               selected_cards=_selected_cards(prompt, subset),
                               selected_indices=list(subset), selected_count=size))
            if len(out) > max_options:
                return None
    return out or None


def _sort(decision, prompt, max_options):
    n = len(decision.cards)
    if len(prompt.get('cards', ())) != n:
        raise ValueError('filtered sort card count mismatch')
    if math.factorial(n) > max_options:
        return None
    out = []
    for order in permutations(range(n)):
        ordered_cards = _selected_cards(prompt, order)
        out.append(_option('sort_cards', encode_sort(decision, order),
                           ordered_cards=ordered_cards, order=list(order), selected_count=n))
    return out


def _bit_choices(decision, prompt, max_options, width):
    available = int(prompt.get('meta', {}).get('available', 0) or 0)
    if available != int(decision.meta.get('available', 0)):
        raise ValueError('filtered announcement mask differs from referee mask')
    bits = [1 << i for i in range(width) if available & (1 << i)]
    count = decision.minimum
    if math.comb(len(bits), count) > max_options:
        return None
    out = []
    for chosen in combinations(bits, count):
        value = 0
        for bit in chosen: value |= bit
        response = struct.pack('<Q' if width == 64 else '<I', value)
        out.append(_option('announce_bits', response, announced_mask=value, selected_count=count))
    return out


def enumerate_policy_options(decision, prompt, max_options=512):
    """Return a complete bounded option list, or ``None`` if not enumerable.

    Existing explicit engine actions are handled by ``LearningPilot`` directly;
    this function covers decision families whose legal responses are implicit in
    cards/meta rather than represented by ``Decision.actions``.
    """
    if max_options < 1:
        raise ValueError('max_options must be positive')
    kind = decision.kind
    if kind == 'select_card':
        return _select_card(decision, prompt, max_options)
    if kind in {'select_place', 'disable_field'}:
        return _places(decision, prompt, max_options)
    if kind == 'tribute':
        return _tribute(decision, prompt, max_options)
    if kind == 'counter':
        return _counter(decision, prompt, max_options)
    if kind == 'select_sum':
        return _select_sum(decision, prompt, max_options)
    if kind in {'sort_chain', 'sort_card'}:
        return _sort(decision, prompt, max_options)
    if kind == 'announce_race':
        return _bit_choices(decision, prompt, max_options, 64)
    if kind == 'announce_attribute':
        return _bit_choices(decision, prompt, max_options, 32)
    return None
