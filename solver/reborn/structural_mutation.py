"""Zero-prior structural deck mutations for YGO Reborn search.

These operators improve search reach without assigning strength to any card.

- duplicate_consolidation: increase copies of a randomly chosen card already in
  the deck, up to legal copy/name-group limits.
- relation_pair_injection: choose a random producer/consumer relation from the
  full-pool text-screening hypothesis graph and inject copies of one random card
  from each side.

The relation graph is only a proposal mechanism.  It is never a payoff, card
value, or proof of synergy.  Actual duel outcomes must decide whether a proposal
survives.
"""
from __future__ import annotations

import collections
import random

from .search import canonical, validate


def _try_replace_one(deck, cards, target, rng):
    """Replace one non-target card with target if a legal replacement exists."""
    base = list(deck)
    indices = [i for i, cid in enumerate(base) if cid != target]
    rng.shuffle(indices)
    for index in indices:
        trial = list(base)
        trial[index] = target
        trial = list(canonical(trial))
        try:
            validate(trial, cards)
        except ValueError:
            continue
        return trial, True
    return base, False


def add_target_copies(deck, cards, target, rng, desired_total=3):
    """Increase one target's count toward desired_total without breaking legality."""
    if target not in cards:
        raise ValueError(f'unknown mutation target: {target}')
    validate(list(deck), cards)
    out = list(deck)
    limit = min(int(cards[target]['copy_limit']), int(desired_total), 3)
    changed = 0
    while collections.Counter(out)[target] < limit:
        out, ok = _try_replace_one(out, cards, target, rng)
        if not ok:
            break
        changed += 1
    validate(out, cards)
    return canonical(out), changed


def duplicate_consolidation(deck, cards, rng):
    """Randomly choose an in-deck card that can legally gain more copies."""
    validate(list(deck), cards)
    counts = collections.Counter(deck)
    options = [
        cid for cid in counts
        if counts[cid] < min(int(cards[cid]['copy_limit']), 3)
    ]
    rng.shuffle(options)
    for target in options:
        out, changed = add_target_copies(deck, cards, target, rng, desired_total=3)
        if changed:
            return out, {
                'method': 'duplicate_consolidation',
                'target': target,
                'copies_added': changed,
            }
    raise ValueError('no legal duplicate-consolidation mutation available')


def relation_pair_injection(deck, cards, synergy_graph, rng, desired_each=2, attempts=100):
    """Inject a randomly sampled text-relation pair as an unverified hypothesis."""
    validate(list(deck), cards)
    indexes = synergy_graph.get('tag_indexes', {})
    relations = [tuple(row) for row in synergy_graph.get('relations', ())]
    if not relations:
        raise ValueError('synergy graph has no relation families')

    for _ in range(attempts):
        source_tag, dest_tag = rng.choice(relations)
        sources = [cid for cid in indexes.get(source_tag, ()) if cid in cards]
        dests = [cid for cid in indexes.get(dest_tag, ()) if cid in cards]
        if not sources or not dests:
            continue
        source = rng.choice(sources)
        dest = rng.choice(dests)
        if source == dest:
            continue

        first, add_a = add_target_copies(
            deck, cards, source, rng, desired_total=desired_each
        )
        second, add_b = add_target_copies(
            first, cards, dest, rng, desired_total=desired_each
        )
        if add_a + add_b <= 0:
            continue
        validate(list(second), cards)
        return second, {
            'method': 'relation_pair_injection',
            'relation': f'{source_tag}->{dest_tag}',
            'source': source,
            'destination': dest,
            'source_copies_added': add_a,
            'destination_copies_added': add_b,
            'relation_status': 'unverified_text_hypothesis_only',
        }
    raise ValueError('unable to construct legal relation-pair mutation')


def generate_structural_challengers(
    parents, cards, synergy_graph, count, seed, baseline_mutator=None
):
    """Generate unique legal proposals from structural and optional baseline moves."""
    if count < 1:
        raise ValueError('count must be positive')
    if not parents:
        raise ValueError('at least one parent deck is required')
    rng = random.Random(seed)
    generated = {}
    cursor = 0

    while len(generated) < count:
        parent_id, parent = parents[cursor % len(parents)]
        mode = cursor % (3 if baseline_mutator is not None else 2)
        try:
            if mode == 0:
                deck, meta = duplicate_consolidation(parent, cards, rng)
            elif mode == 1:
                deck, meta = relation_pair_injection(
                    parent, cards, synergy_graph, rng, desired_each=2
                )
            else:
                deck = baseline_mutator(parent, cards, rng)
                meta = {'method': 'baseline_mutation'}
        except ValueError:
            cursor += 1
            if cursor > count * 300:
                raise RuntimeError('unable to generate requested structural challengers')
            continue

        deck = canonical(deck)
        validate(list(deck), cards)
        if deck == canonical(parent):
            cursor += 1
            continue
        identity = '|'.join(deck)
        if identity not in generated:
            generated[identity] = {
                'parent': parent_id,
                'deck': list(deck),
                **meta,
            }
        cursor += 1
        if cursor > count * 300:
            raise RuntimeError('unable to generate requested structural challengers')

    return list(generated.values())
