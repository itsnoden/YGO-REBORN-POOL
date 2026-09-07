"""Prioritize latest-official-text vs pinned-engine text differences.

This module is deliberately conservative about effect text. It never declares a
non-exact Effect/Spell/Trap text comparison behaviorally equivalent. It only
separates:

- exact text,
- punctuation/case/spacing-only differences,
- actual lexical differences requiring behavior/errata audit,
- missing latest-official text,
- and non-exact Normal Monster lore.

Normal Monster description text has no card effect to execute, so lore wording
cannot change duel behavior. It remains a provenance/text-quality issue, but it
must not inflate the behavior-changing errata blocker queue.
"""
from __future__ import annotations

import argparse
from collections import Counter
from difflib import SequenceMatcher
import json
import re

from .import_pool import ROOT, dump


def _text_key(text):
    return ' '.join((text or '').replace('\r', ' ').split())


def lexical_tokens(text):
    return tuple(re.findall(r'[a-z0-9]+', _text_key(text).casefold()))


def classify_text_pair(official_text, engine_text):
    """Return a prioritization label, never a semantic certification."""
    official = _text_key(official_text)
    engine = _text_key(engine_text)
    if not official:
        return 'missing_latest_official_text'
    if official == engine:
        return 'exact'
    if lexical_tokens(official) == lexical_tokens(engine):
        return 'token_sequence_identical_formatting_only'
    return 'lexical_difference_requires_audit'


def _first_token_difference(left, right):
    a = lexical_tokens(left)
    b = lexical_tokens(right)
    limit = min(len(a), len(b))
    for index in range(limit):
        if a[index] != b[index]:
            return {
                'index': index,
                'official_token': a[index],
                'engine_token': b[index],
            }
    if len(a) != len(b):
        return {
            'index': limit,
            'official_token': a[limit] if limit < len(a) else None,
            'engine_token': b[limit] if limit < len(b) else None,
        }
    return None


def build_report(cards, mapped):
    by_id = {card['id']: card for card in cards}
    rows = []
    counts = Counter()
    for entry in mapped:
        card = by_id[entry['reborn_id']]
        official = (card.get('official') or {}).get('text') or ''
        engine = entry.get('engine_text') or ''
        category = classify_text_pair(official, engine)
        if category != 'exact' and entry.get('normal_monster'):
            category = 'normal_monster_lore_only_not_behavior_blocker'
        counts[category] += 1
        if category == 'exact':
            continue
        official_tokens = lexical_tokens(official)
        engine_tokens = lexical_tokens(engine)
        rows.append({
            'reborn_id': entry['reborn_id'],
            'name': entry['name'],
            'engine_name': entry.get('engine_name'),
            'passcode': entry.get('passcode'),
            'normal_monster': bool(entry.get('normal_monster')),
            'category': category,
            'official_token_count': len(official_tokens),
            'engine_token_count': len(engine_tokens),
            'token_sequence_similarity': round(
                SequenceMatcher(None, official_tokens, engine_tokens).ratio(), 6
            ) if official_tokens or engine_tokens else 1.0,
            'first_token_difference': _first_token_difference(official, engine),
            'latest_official_text_sha256': entry.get('latest_official_text_sha256'),
        })

    # Real lexical effect-text differences first. Formatting/provenance-only rows
    # remain visible after the behavior blockers.
    priority = {
        'lexical_difference_requires_audit': 0,
        'missing_latest_official_text': 1,
        'token_sequence_identical_formatting_only': 2,
        'normal_monster_lore_only_not_behavior_blocker': 3,
    }
    rows.sort(key=lambda row: (
        priority.get(row['category'], 9),
        row['token_sequence_similarity'],
        row['name'].casefold(),
    ))
    behavior_blockers = sum(
        counts.get(name, 0) for name in (
            'lexical_difference_requires_audit',
            'missing_latest_official_text',
        )
    )
    return {
        'purpose': 'text_difference_prioritization_not_behavior_certification',
        'mapped_cards': len(mapped),
        'counts': dict(sorted(counts.items())),
        'nonexact_rows': len(rows),
        'behavior_text_audit_blockers': behavior_blockers,
        'rows': rows,
        'note': (
            'Only exact text equality is an exact-text match. '
            'token_sequence_identical_formatting_only is a prioritization aid, not a ruling. '
            'Every lexical_difference_requires_audit remains an errata/implementation audit blocker. '
            'normal_monster_lore_only_not_behavior_blocker is separated because a Normal Monster has no '
            'effect text to execute; lore provenance may still be audited but cannot alter duel behavior.'
        ),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='reports/text_difference_audit.json')
    a = p.parse_args()
    cards = json.loads((ROOT/'data/processed/cards.json').read_text())
    mapped = json.loads((ROOT/'data/processed/engine_cards.json').read_text())
    report = build_report(cards, mapped)
    output = ROOT/a.output
    dump(output, report)
    print(json.dumps({
        'mapped_cards': report['mapped_cards'],
        'exact': report['counts'].get('exact', 0),
        'formatting_only_nonexact': report['counts'].get('token_sequence_identical_formatting_only', 0),
        'normal_monster_lore_only': report['counts'].get('normal_monster_lore_only_not_behavior_blocker', 0),
        'lexical_audit': report['counts'].get('lexical_difference_requires_audit', 0),
        'missing_official': report['counts'].get('missing_latest_official_text', 0),
        'behavior_text_audit_blockers': report['behavior_text_audit_blockers'],
    }))


if __name__ == '__main__':
    main()
