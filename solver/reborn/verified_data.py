"""Durable factual overlays for reviewed identity and official-text gaps.

These files contain card identity/text provenance only.  They are not strategy
priors and must never be populated from decklists, metagame data, or community
card evaluations.
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
    path = ROOT/'data/verified_official_records.json'
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get('records', {})


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
