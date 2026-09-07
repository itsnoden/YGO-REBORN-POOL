"""Risk-prioritize non-exact card-effect text without certifying semantics.

This is an audit scheduler, not a strategy model and not a rules equivalence
checker. It compares latest verified text against pinned-engine text and raises
objective flags when lexical differences touch mechanics that commonly change a
legal game state: numeric values, activation/use limits, targeting, locations,
actions such as Summon/destroy/banish/negate, timing windows, and player scope.

Every lexical difference remains an audit blocker regardless of tier.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import re

from .import_pool import ROOT, dump
from .text_audit import lexical_tokens


TOKEN_CANONICAL = {
    'targets': 'target', 'targeting': 'target', 'targeted': 'target',
    'summoned': 'summon', 'summons': 'summon', 'summoning': 'summon',
    'destroyed': 'destroy', 'destroys': 'destroy', 'destroying': 'destroy',
    'banished': 'banish', 'banishes': 'banish', 'banishing': 'banish',
    'removed': 'remove', 'removes': 'remove', 'removing': 'remove',
    'sent': 'send', 'sends': 'send', 'sending': 'send',
    'discarded': 'discard', 'discards': 'discard', 'discarding': 'discard',
    'returned': 'return', 'returns': 'return', 'returning': 'return',
    'shuffled': 'shuffle', 'shuffles': 'shuffle', 'shuffling': 'shuffle',
    'draws': 'draw', 'drawing': 'draw',
    'negated': 'negate', 'negates': 'negate', 'negating': 'negate',
    'gained': 'gain', 'gains': 'gain', 'gaining': 'gain',
    'lost': 'lose', 'loses': 'lose', 'losing': 'lose',
    'paid': 'pay', 'pays': 'pay', 'paying': 'pay',
    'equipped': 'equip', 'equips': 'equip', 'equipping': 'equip',
    'changed': 'change', 'changes': 'change', 'changing': 'change',
    'controls': 'control', 'controlled': 'control', 'controlling': 'control',
    'attacks': 'attack', 'attacked': 'attack', 'attacking': 'attack',
    'zones': 'zone',
}

SIGNAL_GROUPS = {
    'frequency_or_restriction': {
        'once', 'twice', 'only', 'cannot', 'must', 'either', 'neither', 'except',
    },
    'targeting': {'target'},
    'summoning': {
        'summon', 'special', 'normal', 'flip', 'fusion', 'ritual', 'tribute',
    },
    'state_change': {
        'destroy', 'banish', 'remove', 'send', 'discard', 'return', 'shuffle',
        'draw', 'negate', 'gain', 'lose', 'pay', 'equip', 'change', 'control',
    },
    'timing': {
        'when', 'if', 'during', 'after', 'before', 'until', 'end', 'start',
        'standby', 'main', 'battle', 'damage', 'step', 'phase', 'turn',
    },
    'location': {
        'hand', 'deck', 'graveyard', 'gy', 'field', 'zone', 'removed', 'banished',
        'extra',
    },
    'player_or_scope': {
        'you', 'your', 'opponent', 'both', 'each', 'all', 'any', 'one', 'another',
    },
    'battle_stats': {'atk', 'def', 'attack', 'battle', 'damage', 'level'},
}

HIGH_GROUPS = {
    'frequency_or_restriction', 'targeting', 'summoning', 'state_change', 'timing',
}


def _canonical_tokens(tokens):
    return tuple(TOKEN_CANONICAL.get(token, token) for token in tokens)


def _numbers(tokens):
    return tuple(token for token in tokens if re.fullmatch(r'\d+', token))


def _changed_signal_groups(official_tokens, engine_tokens):
    official = set(_canonical_tokens(official_tokens))
    engine = set(_canonical_tokens(engine_tokens))
    changed = []
    for group, words in SIGNAL_GROUPS.items():
        if (official & words) != (engine & words):
            changed.append(group)
    return tuple(sorted(changed))


def classify_risk(official_text, engine_text):
    """Return objective audit flags; never return semantic equivalence."""
    official_tokens = lexical_tokens(official_text)
    engine_tokens = lexical_tokens(engine_text)
    number_difference = _numbers(official_tokens) != _numbers(engine_tokens)
    changed_groups = _changed_signal_groups(official_tokens, engine_tokens)
    high_groups = tuple(group for group in changed_groups if group in HIGH_GROUPS)

    if number_difference or high_groups:
        tier = 'high'
    elif changed_groups:
        tier = 'medium'
    else:
        tier = 'low'
    return {
        'risk_tier': tier,
        'numeric_sequence_changed': number_difference,
        'changed_signal_groups': list(changed_groups),
        'high_signal_groups': list(high_groups),
    }


def build_risk_report(cards, mapped):
    by_id = {card['id']: card for card in cards}
    rows = []
    counts = Counter()
    for entry in mapped:
        if entry.get('normal_monster'):
            continue
        card = by_id[entry['reborn_id']]
        official_record = card.get('official') or {}
        official = official_record.get('text') or ''
        engine = entry.get('engine_text') or ''
        if not official:
            # Non-TCG reviewed implementations such as Level Down! are handled by
            # their separate provenance gate, not by pretending a TCG text exists.
            continue
        if ' '.join(official.replace('\r', ' ').split()) == ' '.join(engine.replace('\r', ' ').split()):
            continue
        if lexical_tokens(official) == lexical_tokens(engine):
            continue
        risk = classify_risk(official, engine)
        counts[risk['risk_tier']] += 1
        rows.append({
            'reborn_id': entry['reborn_id'],
            'name': entry['name'],
            'engine_name': entry.get('engine_name'),
            'passcode': entry.get('passcode'),
            'official_display_name': official_record.get('official_display_name') or official_record.get('name'),
            'official_source_url': official_record.get('source_url'),
            'official_text': official,
            'engine_text': engine,
            **risk,
        })

    tier_order = {'high': 0, 'medium': 1, 'low': 2}
    rows.sort(key=lambda row: (
        tier_order[row['risk_tier']],
        not row['numeric_sequence_changed'],
        -len(row['high_signal_groups']),
        -len(row['changed_signal_groups']),
        row['name'].casefold(),
    ))
    return {
        'purpose': 'rules_risk_prioritization_not_semantic_certification',
        'lexical_effect_rows_prioritized': len(rows),
        'counts': dict(sorted(counts.items())),
        'rows': rows,
        'note': (
            'All rows remain behavior/errata audit blockers. Risk tier only schedules review. '
            'Common grammatical inflections of mechanical verbs are normalized before signal comparison. '
            'Full verified-current and pinned-engine texts are retained in each row for deterministic review. '
            'No card is certified equivalent from token signals, and no deck-strength prior is used.'
        ),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='reports/text_risk_audit.json')
    a = p.parse_args()
    cards = json.loads((ROOT/'data/processed/cards.json').read_text())
    mapped = json.loads((ROOT/'data/processed/engine_cards.json').read_text())
    report = build_risk_report(cards, mapped)
    dump(ROOT/a.output, report)
    print(json.dumps({
        'lexical_effect_rows_prioritized': report['lexical_effect_rows_prioritized'],
        'counts': report['counts'],
        'top_high_risk': [row['name'] for row in report['rows'][:20] if row['risk_tier'] == 'high'],
    }))


if __name__ == '__main__':
    main()
