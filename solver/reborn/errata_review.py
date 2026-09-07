"""Validate durable, hash-bound reviews of non-exact current card text.

This module does not infer semantic equivalence. A human/AI rules review may be
recorded separately only after the wording pair has been examined. The review is
accepted solely while the exact Reborn identity, engine passcode, and normalized
SHA-256 hashes of both texts still match. Any upstream/database/official-text
change therefore makes the old review stale automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json

from .import_pool import ROOT, dump
from .text_audit import _text_key, classify_text_pair


def normalized_text_sha256(text):
    return hashlib.sha256(_text_key(text).encode('utf-8')).hexdigest()


def load_reviews(path=None):
    path = path or (ROOT/'data/reviewed_text_equivalence.json')
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get('reviews', {})


def validate_review(review, card, entry):
    official = (card.get('official') or {}).get('text') or ''
    engine = entry.get('engine_text') or ''
    expected = {
        'reborn_id': entry['reborn_id'],
        'passcode': int(entry['passcode']),
        'official_text_sha256': normalized_text_sha256(official),
        'engine_text_sha256': normalized_text_sha256(engine),
    }
    mismatches = []
    for key, value in expected.items():
        recorded = review.get(key)
        if key == 'passcode' and recorded is not None:
            recorded = int(recorded)
        if recorded != value:
            mismatches.append(key)
    valid_status = review.get('status') == 'behavior_equivalent_wording_reviewed'
    if not valid_status:
        mismatches.append('status')
    return not mismatches, expected, mismatches


def build_review_report(cards, mapped, reviews=None):
    reviews = reviews if reviews is not None else load_reviews()
    by_id = {card['id']: card for card in cards}
    mapped_by_id = {row['reborn_id']: row for row in mapped}
    valid = []
    stale = []
    orphan = []

    for review_key, review in sorted(reviews.items()):
        reborn_id = review.get('reborn_id') or review_key
        entry = mapped_by_id.get(reborn_id)
        card = by_id.get(reborn_id)
        if entry is None or card is None:
            orphan.append({'review_key': review_key, 'reborn_id': reborn_id})
            continue
        ok, expected, mismatches = validate_review(review, card, entry)
        row = {
            'review_key': review_key,
            'reborn_id': reborn_id,
            'name': entry['name'],
            'passcode': entry['passcode'],
            'status': review.get('status'),
            'rationale': review.get('rationale'),
            'evidence': review.get('evidence'),
            'expected_hashes': expected,
        }
        if ok:
            # A valid review may clear only a real lexical wording mismatch. It
            # cannot convert missing text or already-exact text into a review.
            official = (card.get('official') or {}).get('text') or ''
            category = classify_text_pair(official, entry.get('engine_text') or '')
            if category == 'lexical_difference_requires_audit':
                valid.append(row)
            else:
                row['mismatches'] = ['current_pair_not_lexical_difference']
                stale.append(row)
        else:
            row['mismatches'] = mismatches
            stale.append(row)

    lexical_ids = set()
    for entry in mapped:
        if entry.get('normal_monster'):
            continue
        card = by_id[entry['reborn_id']]
        official = (card.get('official') or {}).get('text') or ''
        if classify_text_pair(official, entry.get('engine_text') or '') == 'lexical_difference_requires_audit':
            lexical_ids.add(entry['reborn_id'])
    reviewed_ids = {row['reborn_id'] for row in valid}
    unresolved = sorted(lexical_ids - reviewed_ids)

    return {
        'purpose': 'hash_bound_rules_text_review_not_strategy_prior',
        'lexical_effect_rows': len(lexical_ids),
        'valid_behavior_equivalence_reviews': len(valid),
        'stale_or_invalid_reviews': len(stale),
        'orphan_reviews': len(orphan),
        'unresolved_lexical_behavior_blockers': len(unresolved),
        'valid_reviews': valid,
        'stale_reviews': stale,
        'orphan_review_rows': orphan,
        'unresolved_reborn_ids': unresolved,
        'note': (
            'A valid review clears only the text-wording audit for the exact hash-bound pair. '
            'It does not certify the Lua implementation, interactions, pilot skill, or deck strength. '
            'Upstream script drift remains a separate mandatory certification gate.'
        ),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='reports/errata_review.json')
    a = p.parse_args()
    cards = json.loads((ROOT/'data/processed/cards.json').read_text())
    mapped = json.loads((ROOT/'data/processed/engine_cards.json').read_text())
    report = build_review_report(cards, mapped)
    dump(ROOT/a.output, report)
    print(json.dumps({
        'lexical_effect_rows': report['lexical_effect_rows'],
        'valid_reviews': report['valid_behavior_equivalence_reviews'],
        'stale_reviews': report['stale_or_invalid_reviews'],
        'unresolved': report['unresolved_lexical_behavior_blockers'],
    }))


if __name__ == '__main__':
    main()
