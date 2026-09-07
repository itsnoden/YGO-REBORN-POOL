"""Prioritize latest-official-text vs pinned-engine text differences.

This module is deliberately conservative about effect text. It never declares a
non-exact Effect/Spell/Trap wording behaviorally equivalent from similarity. It
separates exact/presentation differences, a tiny allowlist of mechanically
identical legacy/current rules terminology, true lexical differences requiring
review, reviewed non-TCG provenance, and Normal Monster lore.
"""
from __future__ import annotations

import argparse
from collections import Counter
from difflib import SequenceMatcher
import json
import re

from .import_pool import ROOT, dump


_BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
_RACE_TERMINALS = {
    'aqua', 'beast', 'warrior', 'god', 'cyberse', 'dinosaur', 'dragon', 'fairy',
    'fiend', 'fish', 'illusion', 'insect', 'machine', 'plant', 'psychic', 'pyro',
    'reptile', 'rock', 'serpent', 'spellcaster', 'thunder', 'wyrm', 'zombie',
}


def _text_key(text):
    # Neuron can encode line breaks as literal HTML <br> while BabelCDB stores
    # the same boundary as a newline. Normalize only that known presentation tag.
    text = _BR_RE.sub(' ', text or '')
    return ' '.join(text.replace('\r', ' ').split())


def lexical_tokens(text):
    """Literal words after presentation normalization; no rules synonyms."""
    return tuple(re.findall(r'[a-z0-9]+', _text_key(text).casefold()))


def rules_terminology_tokens(text):
    """Canonicalize only established old/current Yu-Gi-Oh rules vocabulary.

    This intentionally does NOT normalize general synonyms such as select/target,
    choose/reveal, send/destroy, or timing language. Those remain audit blockers.
    """
    source = lexical_tokens(text)
    out = []
    i = 0
    while i < len(source):
        token = source[i]
        if token == 'graveyard':
            out.append('gy')
            i += 1
            continue
        if i + 1 < len(source) and token == 'life' and source[i + 1] in {'point', 'points'}:
            out.append('lp')
            i += 2
            continue
        # Legacy race wording such as "Machine-Type monster" is the same race
        # terminology as current "Machine monster". Do not remove generic
        # "Type" elsewhere (e.g. "declare 1 Type of monster").
        if (
            token == 'type' and i > 0 and source[i - 1] in _RACE_TERMINALS
            and i + 1 < len(source) and source[i + 1] in {'monster', 'monsters'}
        ):
            i += 1
            continue
        out.append(token)
        i += 1
    return tuple(out)


def classify_text_pair(official_text, engine_text):
    """Return a conservative audit category, never a free-form semantic guess."""
    official = _text_key(official_text)
    engine = _text_key(engine_text)
    if not official:
        return 'missing_latest_official_text'
    if official == engine:
        return 'exact'
    if lexical_tokens(official) == lexical_tokens(engine):
        return 'token_sequence_identical_formatting_only'
    if rules_terminology_tokens(official) == rules_terminology_tokens(engine):
        return 'rules_terminology_equivalent_only'
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
        if (
            entry.get('mapping_source') == 'reviewed_nonstandard_card'
            and entry.get('nonstandard_text_match')
        ):
            category = 'reviewed_nonstandard_text_not_tcg_blocker'
        else:
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
            'nonstandard_status': entry.get('nonstandard_status'),
            'nonstandard_implementation_source': entry.get('nonstandard_implementation_source'),
        })

    priority = {
        'lexical_difference_requires_audit': 0,
        'missing_latest_official_text': 1,
        'reviewed_nonstandard_text_not_tcg_blocker': 2,
        'rules_terminology_equivalent_only': 3,
        'token_sequence_identical_formatting_only': 4,
        'normal_monster_lore_only_not_behavior_blocker': 5,
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
            'HTML br line breaks are presentation-only. The rules-terminology category is restricted to an '
            'explicit canonical vocabulary: Graveyard/GY, Life Point(s)/LP, and legacy Race-Type monster wording. '
            'Generic synonyms, targeting/timing language, and effect operations are never normalized here. '
            'Every lexical_difference_requires_audit remains a blocker unless separately hash-bound reviewed. '
            'Reviewed non-TCG exact records and Normal Monster lore are tracked outside the TCG behavior blocker count.'
        ),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='reports/text_difference_audit.json')
    a = p.parse_args()
    cards = json.loads((ROOT/'data/processed/cards.json').read_text())
    mapped = json.loads((ROOT/'data/processed/engine_cards.json').read_text())
    report = build_report(cards, mapped)
    dump(ROOT/a.output, report)
    print(json.dumps({
        'mapped_cards': report['mapped_cards'],
        'exact': report['counts'].get('exact', 0),
        'formatting_only_nonexact': report['counts'].get('token_sequence_identical_formatting_only', 0),
        'rules_terminology_only': report['counts'].get('rules_terminology_equivalent_only', 0),
        'normal_monster_lore_only': report['counts'].get('normal_monster_lore_only_not_behavior_blocker', 0),
        'reviewed_nonstandard_text': report['counts'].get('reviewed_nonstandard_text_not_tcg_blocker', 0),
        'lexical_audit': report['counts'].get('lexical_difference_requires_audit', 0),
        'missing_official': report['counts'].get('missing_latest_official_text', 0),
        'behavior_text_audit_blockers': report['behavior_text_audit_blockers'],
    }))


if __name__ == '__main__':
    main()
