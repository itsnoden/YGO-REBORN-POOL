import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def key(name):
    return ' '.join(unicodedata.normalize('NFKC', name).replace('’', "'").split()).casefold()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def parse_pool(text, expected=2273):
    section = text.split('SECTION A — 100% CONFIRMED (', 1)[1].split('SECTION B —', 1)[0]
    rows = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if line.startswith('SECTION B —'):
            break
        m = re.match(r'^(\d+)\.\s+(.+?)(?:\s+\[(.*)\])?$', line)
        if m:
            index, name, locator = m.groups()
            rows.append(dict(id=f'reborn-{int(index):04d}', name=name.strip(),
                             source_line=line_number, source_locator=locator))
    assert len(rows) == expected, (len(rows), expected)
    assert len({key(c['name']) for c in rows}) == expected, 'duplicate title'
    assert [int(c['id'][7:]) for c in rows] == list(range(1, expected+1)), 'index gap'
    assert int(section.split(')', 1)[0]) == expected
    return rows


def apply_source_corrections(cards, spec):
    """Apply explicit source re-verifications before legality/text processing.

    This layer exists because the repository raw MASTER can lag a later visual
    correction that has already been accepted into the persistent authoritative
    Library MASTER. Corrections must identify the exact Reborn row and expected
    stale title so an unrelated future edit cannot be silently overwritten.
    """
    by_id = {c['id']: c for c in cards}
    applied = []
    for correction in spec.get('corrections', ()):
        rid = correction['reborn_id']
        if rid not in by_id:
            raise ValueError(f'source correction references unknown pool id {rid}')
        card = by_id[rid]
        expected = correction['from_name']
        if key(card['name']) != key(expected):
            raise ValueError(
                f'source correction {rid} expected stale title {expected!r}, found {card["name"]!r}'
            )
        card['name'] = correction['to_name']
        card['source_correction'] = {
            k: v for k, v in correction.items() if k not in {'reborn_id', 'from_name', 'to_name'}
        }
        applied.append({
            'reborn_id': rid,
            'from_name': expected,
            'to_name': correction['to_name'],
            'status': correction.get('status'),
        })

    names = [key(c['name']) for c in cards]
    if len(set(names)) != len(names):
        raise ValueError('source correction created duplicate pool title')
    for correction in spec.get('corrections', ()):
        stale = correction.get('prohibited_stale_name')
        if stale and key(stale) in names:
            raise ValueError(f'prohibited stale pool title survived correction: {stale}')
    return applied


def parse_limits(text):
    limits = {}
    active = None
    for line in text.splitlines():
        if line.startswith(('FORBIDDEN —', 'LIMITED —', 'SEMI-LIMITED —')):
            active = int(re.search(r'MAX (\d)', line)[1])
        if line.startswith('USER-CONFIRMED FORMAT'):
            active = None
        m = re.match(r'^\d+\. (.+)$', line)
        if m and active is not None:
            name = key(m[1])
            assert name not in limits or limits[name] == active, 'conflicting limits'
            limits[name] = active
        override = re.match(r'^- (.+?) — .*MAX (\d)', line)
        if override:
            limits[key(override[1])] = int(override[2])
    return limits


def main():
    raw = ROOT / 'data/raw'
    cards = parse_pool((raw/'MASTER.txt').read_text())
    correction_path = ROOT/'data/source_corrections.json'
    correction_spec = json.loads(correction_path.read_text()) if correction_path.exists() else {}
    applied_corrections = apply_source_corrections(cards, correction_spec)
    limits = parse_limits((raw/'BANLIST_MASTER.txt').read_text())
    for card in cards:
        limit = limits.get(key(card['name']), 3)
        card.update(copy_limit=limit, legal=limit > 0, placement=None,
                    official=None, effects=[], implementation_status='unimplemented')
    dump(ROOT/'data/processed/cards.json', cards)
    dump(ROOT/'data/processed/input_audit.json', {
        'expected_pool':2273, 'imported_pool':len(cards),
        'source_corrections':applied_corrections,
        'limits':{str(i):sum(c['copy_limit']==i for c in cards) for i in range(4)},
        'banlist_names_outside_pool':sorted(set(limits)-{key(c['name']) for c in cards}),
        'inputs':{
            **{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(raw.glob('*.txt'))},
            **({correction_path.name: hashlib.sha256(correction_path.read_bytes()).hexdigest()}
               if correction_path.exists() else {}),
        },
        'findings_policy':'Archived checkpoint only; NO rankings, decklists or heuristic weights imported into search.',
        'text_policy':'Latest official English TCG text, per user instruction 2026-09-06; never historical errata.',
    })


if __name__ == '__main__':
    main()
