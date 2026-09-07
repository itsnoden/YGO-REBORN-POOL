"""Durable factual overlays for reviewed identity and card-text gaps.

These files contain card identity/text/rules provenance only. They are not
strategy priors and must never be populated from decklists, metagame data, or
community card evaluations.
"""
from __future__ import annotations

import json

from .import_pool import ROOT


def load_identity_aliases():
    aliases = {}
    non_aliases = {}
    base = ROOT/'data/identity_aliases.json'
    if base.exists():
        data = json.loads(base.read_text())
        aliases.update(data.get('aliases', {}))
        non_aliases.update(data.get('explicit_non_aliases', {}))

    shared = ROOT/'data/shared_identity_aliases.json'
    if shared.exists():
        data = json.loads(shared.read_text())
        reviewed = data.get('aliases', {})
        aliases.update(reviewed)
        # A later, stronger same-identity review supersedes an earlier
        # conservative non-alias hold, but only for the explicitly named record.
        for name in reviewed:
            non_aliases.pop(name, None)
    return aliases, non_aliases


def load_verified_official_records():
    """Merge durable objective official-text overlays with collision guards."""
    records = {}
    for filename in (
        'verified_official_records.json',
        'verified_alias_official_records.json',
    ):
        path = ROOT/'data'/filename
        if not path.exists():
            continue
        batch = json.loads(path.read_text()).get('records', {})
        duplicate = sorted(set(records) & set(batch))
        if duplicate:
            raise ValueError(
                f'duplicate verified official record keys across overlays: {duplicate}'
            )
        records.update(batch)
    return records


def apply_verified_official_records(cards):
    """Fill only missing official snapshots from durable verified records."""
    records = load_verified_official_records()
    applied = []
    for card in cards:
        record = records.get(card['name'])
        if not record or card.get('official'):
            continue
        card['official'] = dict(record)
        if record.get('placement') is not None:
            card['placement'] = record['placement']
        applied.append(card['name'])
    return applied


def load_nonstandard_cards():
    """Return explicitly reviewed anime/game-only cards required by Reborn."""
    path = ROOT/'data/nonstandard_cards.json'
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get('cards', {})


def apply_nonstandard_card_records(cards):
    """Attach reviewed non-TCG provenance/placement to exact pool identities."""
    records = load_nonstandard_cards()
    applied = []
    for card in cards:
        spec = records.get(card['name'])
        if not spec:
            continue
        card['nonstandard'] = {
            k: v for k, v in spec.items() if k not in {'data'}
        }
        if spec.get('placement') is not None:
            card['placement'] = spec['placement']
        applied.append(card['name'])
    return applied


def nonstandard_engine_rows():
    """Normalize reviewed non-TCG records to BabelCDB-like engine rows."""
    rows = []
    for pool_name, spec in load_nonstandard_cards().items():
        data = dict(spec['data'])
        rows.append({
            'id': int(spec['engine_id']),
            'ot': 0,
            'alias': int(data.get('alias', 0)),
            'setcode': int(data.get('setcode', 0)),
            'type': int(data['type']),
            'atk': int(data.get('atk', 0)),
            'def': int(data.get('def', 0)),
            'level': int(data.get('level', 0)),
            'race': int(data.get('race', 0)),
            'attribute': int(data.get('attribute', 0)),
            'category': 0,
            'name': spec.get('engine_name', pool_name),
            'desc': spec.get('text', ''),
            '_nonstandard_pool_name': pool_name,
            '_nonstandard_status': spec.get('status'),
            '_nonstandard_implementation_source': spec.get('implementation_source'),
        })
    return rows
