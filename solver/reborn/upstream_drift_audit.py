"""Audit whether newer Project Ignis scripts touch the exact Reborn pool.

Canonical duels remain pinned and reproducible. This audit never changes a pin;
it only compares the pinned CardScripts revision with the current upstream HEAD,
extracts changed official script passcodes, and intersects them with the mapped
Reborn identities. Any intersection is a latest-errata review candidate.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from .import_pool import ROOT, dump


SCRIPT_RE = re.compile(r'(?:^|/)official/c(\d+)\.lua$')


def script_passcodes(paths):
    ids = set()
    for path in paths:
        normalized = str(path).replace('\\', '/')
        match = SCRIPT_RE.search(normalized)
        if match:
            ids.add(int(match.group(1)))
    return ids


def intersect_pool_changes(changed_ids, mapped_rows):
    by_passcode = {}
    for row in mapped_rows:
        by_passcode.setdefault(int(row['passcode']), []).append(row)
    out = []
    for passcode in sorted(set(int(v) for v in changed_ids) & set(by_passcode)):
        rows = by_passcode[passcode]
        out.append({
            'passcode': passcode,
            'reborn_ids': [row['reborn_id'] for row in rows],
            'pool_names': [row['name'] for row in rows],
            'engine_names': sorted({row.get('engine_name') for row in rows if row.get('engine_name')}),
        })
    return out


def _git(args, cwd):
    return subprocess.check_output(['git', '-C', str(cwd), *args], text=True).strip()


def current_remote_head(repo):
    line = subprocess.check_output(
        ['git', '-C', str(repo), 'ls-remote', 'origin', 'HEAD'], text=True
    ).strip()
    if not line:
        raise RuntimeError('CardScripts origin HEAD could not be resolved')
    return line.split()[0]


def build_report(scripts_repo, mapped_rows, fetch=True):
    scripts_repo = Path(scripts_repo).resolve()
    pinned = _git(['rev-parse', 'HEAD'], scripts_repo)
    upstream = current_remote_head(scripts_repo)
    if fetch and upstream != pinned:
        subprocess.run(
            ['git', '-C', str(scripts_repo), 'fetch', '--quiet', 'origin', upstream],
            check=True,
        )
    if upstream == pinned:
        paths = []
    else:
        text = _git(['diff', '--name-only', pinned, upstream, '--', 'official'], scripts_repo)
        paths = [line for line in text.splitlines() if line.strip()]
    changed_ids = script_passcodes(paths)
    pool_changes = intersect_pool_changes(changed_ids, mapped_rows)
    return {
        'purpose': 'latest_upstream_script_drift_audit_not_automatic_pin_update',
        'pinned_scripts_commit': pinned,
        'upstream_scripts_head': upstream,
        'upstream_ahead': upstream != pinned,
        'changed_official_script_files': len(paths),
        'changed_official_passcodes': len(changed_ids),
        'changed_reborn_passcodes': len(pool_changes),
        'changed_reborn_cards': pool_changes,
        'note': (
            'An intersection means newer Project Ignis code touched a Reborn card and must be reviewed. '
            'It does not prove the pinned implementation is wrong or the newer implementation is correct. '
            'Canonical dependency pins are never changed by this audit.'
        ),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scripts', required=True)
    p.add_argument('--output', default='reports/upstream_script_drift.json')
    p.add_argument('--no-fetch', action='store_true')
    a = p.parse_args()
    mapped = json.loads((ROOT/'data/processed/engine_cards.json').read_text())
    report = build_report(a.scripts, mapped, fetch=not a.no_fetch)
    dump(ROOT/a.output, report)
    print(json.dumps({
        'pinned': report['pinned_scripts_commit'],
        'upstream': report['upstream_scripts_head'],
        'changed_official_passcodes': report['changed_official_passcodes'],
        'changed_reborn_passcodes': report['changed_reborn_passcodes'],
        'changed_reborn_cards': report['changed_reborn_cards'],
    }))


if __name__ == '__main__':
    main()
