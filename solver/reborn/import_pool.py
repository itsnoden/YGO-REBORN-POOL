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
    limits = parse_limits((raw/'BANLIST_MASTER.txt').read_text())
    for card in cards:
        limit = limits.get(key(card['name']), 3)
        card.update(copy_limit=limit, legal=limit > 0, placement=None,
                    official=None, effects=[], implementation_status='unimplemented')
    dump(ROOT/'data/processed/cards.json', cards)
    dump(ROOT/'data/processed/input_audit.json', {
        'expected_pool':2273, 'imported_pool':len(cards),
        'limits':{str(i):sum(c['copy_limit']==i for c in cards) for i in range(4)},
        'banlist_names_outside_pool':sorted(set(limits)-{key(c['name']) for c in cards}),
        'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(raw.glob('*.txt'))},
        'findings_policy':'Archived checkpoint only; NO rankings, decklists or heuristic weights imported into search.',
        'text_policy':'Latest official English TCG text, per user instruction 2026-09-06; never historical errata.',
    })


if __name__ == '__main__':
    main()
