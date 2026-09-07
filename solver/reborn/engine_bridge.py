"""Join exact Reborn identities to pinned ocgcore data; audit coverage."""
import argparse
from difflib import SequenceMatcher
import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path
from .import_pool import (
    ROOT, apply_source_corrections, dump, key, load_source_corrections,
)
from .verified_data import (
    apply_nonstandard_card_records,
    apply_verified_official_records,
    load_identity_aliases,
    nonstandard_engine_rows,
)


def text_key(text):
    return ' '.join(text.replace('\r',' ').split())


def _name_shape(name):
    """Comparison-only normalized title; never authorizes an engine mapping."""
    return re.sub(r'[^a-z0-9]+', '', key(name))


def _name_tokens(name):
    return set(re.findall(r'[a-z0-9]+', key(name)))


def mapping_suggestions(name, rows, limit=5):
    """Rank likely database titles for manual audit without auto-mapping them."""
    source_shape = _name_shape(name)
    source_tokens = _name_tokens(name)
    scored = []
    seen = set()
    for row in rows:
        rid = int(row['id'])
        if rid in seen:
            continue
        seen.add(rid)
        candidate_name = row['name']
        target_shape = _name_shape(candidate_name)
        sequence = SequenceMatcher(None, source_shape, target_shape).ratio() if source_shape and target_shape else 0.0
        target_tokens = _name_tokens(candidate_name)
        union = source_tokens | target_tokens
        token_jaccard = len(source_tokens & target_tokens) / len(union) if union else 0.0
        # Ranking aid only. Exact mapping still requires explicit verification.
        score = max(sequence, 0.65 * sequence + 0.35 * token_jaccard)
        scored.append((score, candidate_name.casefold(), rid, candidate_name))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [
        {'id': rid, 'name': candidate_name, 'similarity': round(score, 4)}
        for score, _, rid, candidate_name in scored[:max(0, int(limit))]
    ]


def unique_exact_text_match(official_text, rows, blocked_ids=()):
    """Return one primary engine row only when latest official text is unique."""
    if not official_text:
        return None, []
    wanted = text_key(official_text)
    blocked = {int(v) for v in blocked_ids}
    matches = [
        row for row in rows
        if int(row['id']) not in blocked and int(row.get('alias', 0) or 0) == 0
        and text_key(row.get('desc') or '') == wanted
    ]
    if len(matches) == 1:
        return matches[0], matches
    return None, matches


def _exact_primary(matches):
    return matches if len(matches) == 1 else [r for r in matches if r['alias'] == 0]


def _load_identity_aliases():
    return load_identity_aliases()


def reviewed_alias_match(pool_name, records, aliases, blocked_ids=(), shared_ids=()):
    """Resolve only an explicitly reviewed pool-title identity alias.

    Ordinary aliases may never collide with an already reserved/mapped engine ID.
    A much narrower exception exists for an alias explicitly marked as the same
    current card identity: it may reuse an ID only after that exact engine ID has
    already been mapped by another pool record. This preserves source records
    while making both names share one rules identity and one deck-name limit.
    """
    spec = aliases.get(pool_name)
    if not spec:
        return None, None
    target_name = spec.get('engine_name')
    if not target_name:
        raise ValueError(f'reviewed alias {pool_name!r} has no engine_name')
    primary = _exact_primary(records.get(key(target_name), []))
    if len(primary) != 1:
        raise ValueError(
            f'reviewed alias {pool_name!r}->{target_name!r} resolved to {len(primary)} primary engine cards'
        )
    row = primary[0]
    rid = int(row['id'])
    blocked = {int(v) for v in blocked_ids}
    shared = {int(v) for v in shared_ids}
    allow_shared = bool(spec.get('allow_shared_engine_identity')) and rid in shared
    if rid in blocked and not allow_shared:
        raise ValueError(
            f'reviewed alias {pool_name!r}->{target_name!r} collides with a reserved/used engine ID'
        )
    return row, spec


def _whitelist_lines(mapped):
    """Emit one whitelist row per current engine identity."""
    by_passcode = {}
    for row in mapped:
        if row['copy_limit'] <= 0:
            continue
        rid = int(row['passcode'])
        current = by_passcode.get(rid)
        if current is None or int(row['copy_limit']) < int(current['copy_limit']):
            by_passcode[rid] = row
    return [
        f"{rid} {row['copy_limit']} -- {row['engine_name']}"
        for rid, row in sorted(by_passcode.items())
    ]


def main():
    p=argparse.ArgumentParser();p.add_argument('--database',required=True)
    p.add_argument('--scripts',required=True);p.add_argument('--core',required=True);a=p.parse_args()
    db=Path(a.database).resolve();scripts=Path(a.scripts).resolve();core=Path(a.core).resolve()
    overrides=ROOT/'script_overrides'
    aliases,non_aliases=_load_identity_aliases()
    con=sqlite3.connect(db);con.row_factory=sqlite3.Row
    records={};all_records=[]
    existing_ids=set()
    for r in con.execute('SELECT d.*,t.name,t.desc FROM datas d JOIN texts t USING(id)'):
        row=dict(r);all_records.append(row);records.setdefault(key(r['name']),[]).append(row)
        existing_ids.add(int(row['id']))

    # Exact reviewed anime/game-only cards may be absent from the pinned Babel
    # database. Add only explicit records from data/nonstandard_cards.json.
    nonstandard_rows=nonstandard_engine_rows()
    for row in nonstandard_rows:
        rid=int(row['id'])
        if rid in existing_ids:
            raise ValueError(f'nonstandard engine id collides with pinned database: {rid}')
        all_records.append(row);records.setdefault(key(row['name']),[]).append(row)
        existing_ids.add(rid)

    cards=json.loads((ROOT/'data/processed/cards.json').read_text())
    applied_source_corrections=apply_source_corrections(cards,load_source_corrections())
    applied_official_overlays=apply_verified_official_records(cards)
    applied_nonstandard_overlays=apply_nonstandard_card_records(cards)
    mapped=[];missing=[]

    # Exact-title matches have priority over every fallback, independent of pool
    # ordering. Reserve their IDs up front so ordinary aliases cannot steal an ID
    # from a separate exact-title card later in the pool.
    reserved_exact_ids=set()
    for c in cards:
        primary=_exact_primary(records.get(key(c['name']),[]))
        if len(primary)==1:
            reserved_exact_ids.add(int(primary[0]['id']))

    used_ids=set()
    for c in cards:
        matches=records.get(key(c['name']),[])
        primary=_exact_primary(matches)
        mapping_source=None
        alias_spec=None
        text_candidates=[]
        if len(primary)==1:
            r=primary[0]
            mapping_source=(
                'reviewed_nonstandard_card'
                if r.get('_nonstandard_pool_name') == c['name']
                else 'exact_title'
            )
        else:
            blocked=reserved_exact_ids|used_ids
            r,alias_spec=reviewed_alias_match(
                c['name'],records,aliases,blocked,shared_ids=used_ids
            )
            if r is not None:
                mapping_source=(
                    'reviewed_shared_identity_alias'
                    if alias_spec.get('allow_shared_engine_identity')
                    else 'reviewed_identity_alias'
                )
            else:
                official_text=(c.get('official') or {}).get('text')
                r,text_candidates=unique_exact_text_match(official_text,all_records,blocked)
                if r is not None:
                    mapping_source='unique_exact_latest_official_text'
                else:
                    non_alias=non_aliases.get(c['name'])
                    missing.append(dict(
                        id=c['id'],name=c['name'],candidate_ids=[r['id'] for r in matches],
                        exact_text_candidate_ids=[row['id'] for row in text_candidates],
                        exact_text_candidate_names=[row['name'] for row in text_candidates],
                        suggestions=mapping_suggestions(c['name'], all_records, 5),
                        mapping_status=(
                            non_alias.get('status') if non_alias else 'unverified_suggestions_only'
                        ),
                        identity_blocker=non_alias,
                    ));continue
        rid=int(r['id'])
        shared_duplicate=(
            rid in used_ids and alias_spec is not None
            and bool(alias_spec.get('allow_shared_engine_identity'))
        )
        if rid in used_ids and not shared_duplicate:
            raise RuntimeError(f'duplicate engine mapping {rid} for {c["name"]}')
        used_ids.add(rid)
        upstream=scripts/'official'/f"c{rid}.lua"
        override=overrides/f"c{rid}.lua"
        if override.exists():
            implementation=override
            script_source='reviewed_override'
            script_path=f"script_overrides/c{rid}.lua"
            status='reviewed_override_unvalidated'
        elif upstream.exists():
            implementation=upstream
            script_source='upstream_official'
            script_path=f"official/c{rid}.lua"
            status='upstream_script_unvalidated'
        else:
            implementation=None
            script_source=None
            script_path=None
            status=None
        is_normal=bool(r['type']&0x10) and not bool(r['type']&0x20)
        if implementation is None:
            status='normal_monster_no_script' if is_normal else 'missing_script'
        official=c.get('official') or {}
        nonstandard=c.get('nonstandard') or {}
        official_text_match=bool(official) and text_key(official.get('text',''))==text_key(r['desc'])
        nonstandard_text_match=(
            mapping_source=='reviewed_nonstandard_card'
            and bool(nonstandard.get('text'))
            and text_key(nonstandard.get('text',''))==text_key(r['desc'])
        )
        entry=dict(reborn_id=c['id'],name=c['name'],passcode=rid,copy_limit=c['copy_limit'],
             mapping_source=mapping_source,engine_name=r['name'],
             identity_alias_status=alias_spec.get('status') if alias_spec else None,
             identity_alias_evidence=alias_spec.get('evidence') if alias_spec else None,
             identity_alias_source_url=alias_spec.get('source_url') if alias_spec else None,
             shared_engine_identity=bool(alias_spec and alias_spec.get('allow_shared_engine_identity')),
             nonstandard_status=r.get('_nonstandard_status'),
             nonstandard_implementation_source=r.get('_nonstandard_implementation_source'),
             data={k:v for k,v in r.items() if k not in ('name','desc') and not k.startswith('_')},
             script_path=script_path,script_source=script_source,
             script_sha256=hashlib.sha256(implementation.read_bytes()).hexdigest() if implementation else None,
             normal_monster=is_normal,official_text_match=official_text_match,
             nonstandard_text_match=nonstandard_text_match,
             engine_text=r['desc'],latest_official_text_sha256=official.get('text_sha256'),
             status=status)
        mapped.append(entry)
        c['engine']={k:v for k,v in entry.items() if k not in ('data','engine_text')}
        c['deck_name_group']=str(r['alias'] or rid)
        # Placement is determined by authoritative official text/verified factual
        # overlay or explicit reviewed non-TCG record, never title similarity.
    con.close()
    dump(ROOT/'data/processed/cards.json',cards)
    dump(ROOT/'data/processed/engine_cards.json',mapped)
    locks={}
    for name,path,url in [('core',core,'https://github.com/edo9300/ygopro-core.git'),
                          ('scripts',scripts,'https://github.com/ProjectIgnis/CardScripts.git'),
                          ('database',db.parent,'https://github.com/ProjectIgnis/BabelCDB.git')]:
        locks[name]=dict(url=url,commit=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip())
    dump(ROOT/'engine.lock.json',locks)
    dump(ROOT/'reports/engine_coverage.json',dict(mapped=len(mapped),unmapped=missing,
        source_corrections_applied=applied_source_corrections,
        verified_official_overlays_applied=applied_official_overlays,
        nonstandard_overlays_applied=applied_nonstandard_overlays,
        exact_title_mappings=sum(r['mapping_source']=='exact_title' for r in mapped),
        reviewed_nonstandard_mappings=sum(r['mapping_source']=='reviewed_nonstandard_card' for r in mapped),
        reviewed_nonstandard_cards=[
            {'reborn_id':r['reborn_id'],'pool_name':r['name'],'engine_name':r['engine_name'],
             'engine_id':r['passcode'],'status':r['nonstandard_status'],
             'implementation_source':r['nonstandard_implementation_source']}
            for r in mapped if r['mapping_source']=='reviewed_nonstandard_card'
        ],
        reviewed_identity_alias_mappings=sum(r['mapping_source']=='reviewed_identity_alias' for r in mapped),
        reviewed_shared_identity_alias_mappings=sum(r['mapping_source']=='reviewed_shared_identity_alias' for r in mapped),
        reviewed_identity_aliases=[
            {'reborn_id':r['reborn_id'],'pool_name':r['name'],'engine_name':r['engine_name'],
             'passcode':r['passcode'],'status':r['identity_alias_status'],
             'shared_engine_identity':r['shared_engine_identity']}
            for r in mapped if r['mapping_source'] in {'reviewed_identity_alias','reviewed_shared_identity_alias'}
        ],
        exact_text_fallback_mappings=sum(r['mapping_source']=='unique_exact_latest_official_text' for r in mapped),
        exact_text_fallbacks=[
            {'reborn_id':r['reborn_id'],'pool_name':r['name'],'engine_name':r['engine_name'],'passcode':r['passcode']}
            for r in mapped if r['mapping_source']=='unique_exact_latest_official_text'
        ],
        unique_engine_identities=len({r['passcode'] for r in mapped}),
        scripts=sum(bool(r['script_path']) for r in mapped),
        upstream_scripts=sum(r['script_source']=='upstream_official' for r in mapped),
        reviewed_overrides=sum(r['script_source']=='reviewed_override' for r in mapped),
        normal_without_script=sum(r['status']=='normal_monster_no_script' for r in mapped),
        missing_script=[r['name'] for r in mapped if r['status']=='missing_script'],
        exact_official_text_matches=sum(r['official_text_match'] for r in mapped),
        reviewed_nonstandard_text_matches=sum(r['nonstandard_text_match'] for r in mapped),
        text_differences=[r['name'] for r in mapped if not r['official_text_match'] and not r['nonstandard_text_match']],
        certified_interactions=0,
        note=(
            'Implementation availability, including reviewed overrides, is not Reborn correctness certification. '
            'Source corrections are hard pool-identity constraints. Reviewed aliases are explicit audited identity '
            'corrections only; same-card shared aliases may reuse an already mapped passcode and share one deck-name '
            'limit. Reviewed non-TCG cards are exact Reborn identities with separate provenance and must never be '
            'substituted for similarly named TCG cards. Fuzzy suggestions remain advisory only.'
        )))
    # Whitelist mode is crucial: cards not present here must not default to 3.
    lines=['# Reborn exact pool; latest standard scripts plus reviewed solver overrides','!Reborn solver 2026-09-06','$whitelist']
    lines += _whitelist_lines(mapped)
    (ROOT/'data/processed/reborn.lflist.conf').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
