"""Seeded legal-action pilots with no card-specific or metagame priors.

The stochastic pilot is intentionally weak. Its purpose is to exercise diverse
engine paths using only the acting player's filtered observation and the legal
prompt produced by ocgcore. It is a correctness/adversarial-coverage baseline,
not strength evidence and not a search prior.
"""
from __future__ import annotations

from itertools import combinations
import random
import struct

from .effects import UnsupportedInteraction
from .protocol import encode_card_selection, encode_place_selection
from .protocol_extra import (
    encode_counter_selection, encode_sort, encode_sum_selection,
    encode_tribute_selection,
)


class StochasticLegalPilot:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.seed = seed

    def _choice(self, values):
        values = list(values)
        if not values:
            raise UnsupportedInteraction('pilot received an empty legal choice set')
        return values[self.rng.randrange(len(values))]

    def choose_announce_card(self, legal_codes):
        """Choose uniformly from a complete externally verified legal code set."""
        return struct.pack('<i', int(self._choice(legal_codes)))

    def _card_selection(self, decision):
        if decision.cancelable and self.rng.random() < 0.08:
            return encode_card_selection(decision, None)
        count = self.rng.randint(decision.minimum, decision.maximum)
        indices = self.rng.sample(range(len(decision.cards)), count)
        return encode_card_selection(decision, indices)

    def _tribute(self, decision):
        release = decision.meta['release_values']
        legal = []
        if decision.cancelable:
            legal.append(None)
        for size in range(0, min(decision.maximum, len(release)) + 1):
            for subset in combinations(range(len(release)), size):
                if sum(release[i] for i in subset) >= decision.minimum:
                    legal.append(subset)
        selected = self._choice(legal)
        return encode_tribute_selection(decision, selected)

    def _counter(self, decision):
        available = decision.meta['available']
        remaining = decision.minimum
        counts = [0] * len(available)
        order = list(range(len(available)))
        self.rng.shuffle(order)
        for pos, idx in enumerate(order):
            future_capacity = sum(available[j] for j in order[pos + 1:])
            low = max(0, remaining - future_capacity)
            high = min(available[idx], remaining)
            take = self.rng.randint(low, high)
            counts[idx] = take
            remaining -= take
        if remaining:
            raise UnsupportedInteraction('stochastic counter allocator failed')
        return encode_counter_selection(decision, counts)

    def _sum(self, decision, node_limit=30000):
        indices = list(range(len(decision.cards)))
        self.rng.shuffle(indices)
        checked = 0
        sizes = list(range(len(indices) + 1))
        self.rng.shuffle(sizes)
        for size in sizes:
            subsets = list(combinations(indices, size)) if len(indices) <= 14 else None
            if subsets is not None:
                self.rng.shuffle(subsets)
                iterator = subsets
            else:
                # Large prompts are rare. Sample bounded subsets first and fall
                # back to the strict deterministic encoder search elsewhere.
                iterator = (tuple(self.rng.sample(indices, size)) for _ in range(min(512, node_limit)))
            for subset in iterator:
                checked += 1
                if checked > node_limit:
                    break
                try:
                    return encode_sum_selection(decision, subset)
                except ValueError:
                    pass
            if checked > node_limit:
                break
        raise UnsupportedInteraction('no legal select-sum response found inside pilot node limit')

    def _bits(self, available, count):
        bits = [1 << i for i in range(available.bit_length()) if available & (1 << i)]
        if len(bits) < count:
            raise UnsupportedInteraction('announce bit prompt has insufficient legal bits')
        chosen = self.rng.sample(bits, count)
        value = 0
        for bit in chosen:
            value |= bit
        return value

    def choose(self, decision, observation):
        """Return one legal encoded response from filtered information only."""
        if observation.get('viewer') != decision.player:
            raise UnsupportedInteraction('pilot observation belongs to wrong player')

        kind = decision.kind
        if kind == 'select_card':
            return self._card_selection(decision)
        if kind in {'select_place', 'disable_field'}:
            places = self.rng.sample(list(decision.meta['places']), decision.minimum)
            return encode_place_selection(decision, places)
        if kind == 'tribute':
            return self._tribute(decision)
        if kind == 'counter':
            return self._counter(decision)
        if kind == 'select_sum':
            return self._sum(decision)
        if kind in {'sort_chain', 'sort_card'}:
            order = list(range(len(decision.cards)))
            self.rng.shuffle(order)
            return encode_sort(decision, order)
        if kind == 'select_unselect':
            return self._choice(decision.actions).response
        if kind == 'announce_race':
            return struct.pack('<Q', self._bits(decision.meta['available'], decision.minimum))
        if kind == 'announce_attribute':
            return struct.pack('<I', self._bits(decision.meta['available'], decision.minimum))
        if kind == 'announce_card':
            raise UnsupportedInteraction('announce-card requires a database-backed legal-code set')
        if kind in {'announce_number', 'rock_paper_scissors'}:
            return self._choice(decision.actions).response
        if decision.actions:
            return self._choice(decision.actions).response
        raise UnsupportedInteraction(f'stochastic pilot has no response for {kind}')
