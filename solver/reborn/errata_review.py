"""Validate durable, hash-bound reviews of non-exact current card text.

This module never infers semantic equivalence. A rules review can resolve a
lexical blocker in exactly two ways:

1. the current official text and engine display text are behaviorally equivalent
   wording; or
2. the display text is genuinely stale/non-equivalent, but the exact executable
   Lua implementation has been directly reviewed and matches current official
   behavior.

Both review types are bound to the exact Reborn identity, passcode, and normalized
hashes of the text pair. Implementation reviews are additionally bound to the
exact script SHA-256, so a script change automatically makes the review stale.
"""
from __future__ import annotations

import argparse
import hashlib
import json

from .import_pool import ROOT, dump
from .text_audit import _text_key, classify_text_pair


WORDING_REVIEW_STATUS = 'behavior_equivalent_wording_reviewed'
IMPLEMENTATION_REVIEW_STATUS = 'implementation_matches_official_reviewed'
VALID_REVIEW_STATUSES = {WORDING_REVIEW_STATUS, IMPLEMENTATION_REVIEW_STATUS}
DEFAULT_REVIEW_PATHS = (
    ROOT/'data/reviewed_text_equivalence.json',
    ROOT/'data/reviewed_implementation_equivalence.json',
)
REVIEW_BATCH_DIR = ROOT/'data/errata_review_batches'


def normalized_text_sha256(text):
    return hashlib.sha256(_text_key(text).encode('utf-8')).hexdigest()


def load_reviews(path=None):
    """Load one explicit ledger, or merge all canonical review ledgers/batches.

    Duplicate review keys are rejected instead of silently allowing one ledger to
    override another. This keeps review batches separately auditable while
    presenting one validation set to the certification gate.
    """
    if path is not None:
        paths = (path,)
    else:
        batch_paths = tuple(sorted(REVIEW_BATCH_DIR.glob('*.json'))) if REVIEW_BATCH_DIR.exists() else ()
        paths = DEFAULT_REVIEW_PATHS + batch_paths
    merged = {}
    for review_path in paths:
        review_path = review_path if hasattr(review_path, 'exists') else ROOT/review_path
        if not review_path.exists():
            continue
        rows = json.loads(review_path.read_text()).get('reviews', {})
        duplicate = set(merged) & set(rows)
        if duplicate:
            raise ValueError(f'duplicate errata review keys across ledgers: {sorted(duplicate)}')
        merged.update(rows)
    return merged


def validate_review(review, card, entry):
    official = (card.get('official') or {}).get('text') or ''
    engine = entry.get('engine_text') or ''
    status = review.get('status')
    expected = {
        'reborn_id': entry['reborn_id'],
        'passcode': int(entry['passcode']),
        'official_text_sha256': normalized_text_sha256(official),
        'engine_text_sha256': normalized_text_sha256(engine),
    }
    mismatches = []

    if status not in VALID_REVIEW_STATUSES:
        mismatches.append('status')
    if status == IMPLEMENTATION_REVIEW_STATUS:
        script_sha = entry.get('script_sha256')
        if not script_sha:
            mismatches.append('current_script_sha256_missing')
        else:
            expected['script_sha256'] = script_sha

    for key, value in expected.items():
        recorded = review.get(key)
        if key == 'passcode' and recorded is not None:
            recorded = int(recorded)
        if recorded != value:
            mismatches.append(key)
    return not mismatches, expected, mismatches


def build_review_report(cards, mapped, reviews=None):
    reviews = reviews if reviews is not None else load_reviews()
    by_id = {card['id']: card for card in cards}
    mapped_by_id = {row['reborn_id']: row for row in mapped}
    valid = []
    valid_wording = []
    valid_implementation = []
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
            'script_source': entry.get('script_source'),
            'script_path': entry.get('script_path'),
        }
        if ok:
            official = (card.get('official') or {}).get('text') or ''
            category = classify_text_pair(official, entry.get('engine_text') or '')
            if category == 'lexical_difference_requires_audit':
                valid.append(row)
                if review.get('status') == WORDING_REVIEW_STATUS:
                    valid_wording.append(row)
                else:
                    valid_implementation.append(row)
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
        'purpose': 'hash_bound_rules_text_and_implementation_review_not_strategy_prior',
        'lexical_effect_rows': len(lexical_ids),
        'valid_behavior_equivalence_reviews': len(valid),
        'valid_wording_equivalence_reviews': len(valid_wording),
        'valid_implementation_behavior_reviews': len(valid_implementation),
        'stale_or_invalid_reviews': len(stale),
        'orphan_reviews': len(orphan),
        'unresolved_lexical_behavior_blockers': len(unresolved),
        'valid_reviews': valid,
        'valid_wording_reviews': valid_wording,
        'valid_implementation_reviews': valid_implementation,
        'stale_reviews': stale,
        'orphan_review_rows': orphan,
        'unresolved_reborn_ids': unresolved,
        'note': (
            'A wording review clears only the text-wording audit for its exact hash-bound pair. '
            'An implementation review is additionally bound to the exact executable script SHA-256 and is used '
            'only when display text is stale/non-equivalent but the reviewed Lua behavior matches current official '
            'behavior. Neither review type certifies unrelated interactions, pilot skill, or deck strength. '
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
        'valid_wording_reviews': report['valid_wording_equivalence_reviews'],
        'valid_implementation_reviews': report['valid_implementation_behavior_reviews'],
        'stale_reviews': report['stale_or_invalid_reviews'],
        'unresolved': report['unresolved_lexical_behavior_blockers'],
    }))


if __name__ == '__main__':
    main()
