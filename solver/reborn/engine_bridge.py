"""Join exact Reborn titles to standard EDOPro IDs; audit text/script coverage."""
import argparse
from difflib import SequenceMatcher
import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path
from .import_pool import ROOT,dump,key


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
    """Return one primary engine row only when latest official text is unique.

    This is deliberately much stricter than fuzzy title matching.  It exists to
    recover verified renames/legacy titles without guessing.  IDs already
    reserved by another exact-title pool card are excluded so two Reborn titles
    cannot silently collapse onto the same engine card.
    """
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


def main():
    p=argparse.ArgumentParser();p.add_argument('--database',required=True)
    p.add_argument('--scripts',required=True);p.add_argument('--core',required=True);a=p.parse_args()
    db=Path(a.database).resolve();scripts=Path(a.scripts).resolve();core=Path(a.core).resolve()
    overrides=ROOT/'script_overrides'
    con=sqlite3.connect(db);con.row_factory=sqlite3.Row
    records={};all_records=[]
    for r in con.execute('SELECT d.*,t.name,t.desc FROM datas d JOIN texts t USING(id)'):
        row=dict(r);all_records.append(row);records.setdefault(key(r['name']),[]).append(row)
    cards=json.loads((ROOT/'data/processed/cards.json').read_text());mapped=[];missing=[]

    # Exact-title matches have priority over every fallback, independent of pool
    # ordering.  Reserve their IDs up front so a legacy-title fallback cannot
    # steal an ID from a separate exact-title card later in the pool.
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
        text_candidates=[]
        if len(primary)==1:
            r=primary[0]
            mapping_source='exact_title'
        else:
            blocked=reserved_exact_ids|used_ids
            official_text=(c.get('official') or {}).get('text')
            r,text_candidates=unique_exact_text_match(official_text,all_records,blocked)
            if r is not None:
                mapping_source='unique_exact_latest_official_text'
            else:
                missing.append(dict(
                    id=c['id'],name=c['name'],candidate_ids=[r['id'] for r in matches],
                    exact_text_candidate_ids=[row['id'] for row in text_candidates],
                    exact_text_candidate_names=[row['name'] for row in text_candidates],
                    suggestions=mapping_suggestions(c['name'], all_records, 5),
                    mapping_status='unverified_suggestions_only',
                ));continue
        rid=int(r['id'])
        if rid in used_ids:
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
        text_match=bool(c.get('official')) and text_key(c['official']['text'])==text_key(r['desc'])
        entry=dict(reborn_id=c['id'],name=c['name'],passcode=rid,copy_limit=c['copy_limit'],
             mapping_source=mapping_source,engine_name=r['name'],
             data={k:v for k,v in r.items() if k not in ('name','desc')},
             script_path=script_path,script_source=script_source,
             script_sha256=hashlib.sha256(implementation.read_bytes()).hexdigest() if implementation else None,
             normal_monster=is_normal,official_text_match=text_match,
             engine_text=r['desc'],latest_official_text_sha256=c['official']['text_sha256'] if c.get('official') else None,
             status=status)
        mapped.append(entry)
        c['engine']={k:v for k,v in entry.items() if k not in ('data','engine_text')}
        c['deck_name_group']=str(r['alias'] or rid)
        # Placement is determined by authoritative official text when present;
        # do not silently promote missing official matches using simulator data.
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
        exact_title_mappings=sum(r['mapping_source']=='exact_title' for r in mapped),
        exact_text_fallback_mappings=sum(r['mapping_source']=='unique_exact_latest_official_text' for r in mapped),
        exact_text_fallbacks=[
            {'reborn_id':r['reborn_id'],'pool_name':r['name'],'engine_name':r['engine_name'],'passcode':r['passcode']}
            for r in mapped if r['mapping_source']=='unique_exact_latest_official_text'
        ],
        scripts=sum(bool(r['script_path']) for r in mapped),
        upstream_scripts=sum(r['script_source']=='upstream_official' for r in mapped),
        reviewed_overrides=sum(r['script_source']=='reviewed_override' for r in mapped),
        normal_without_script=sum(r['status']=='normal_monster_no_script' for r in mapped),
        missing_script=[r['name'] for r in mapped if r['status']=='missing_script'],
        exact_official_text_matches=sum(r['official_text_match'] for r in mapped),
        text_differences=[r['name'] for r in mapped if not r['official_text_match']],
        certified_interactions=0,
        note=(
            'Implementation availability, including reviewed overrides, is not Reborn correctness certification. '
            'Unique exact latest-official-text fallback can resolve renamed titles; fuzzy title suggestions remain '
            'advisory only and never authorize an automatic mapping.'
        )))
    # Whitelist mode is crucial: cards not present here must not default to 3.
    lines=['# Reborn exact pool; latest standard scripts plus reviewed solver overrides','!Reborn solver 2026-09-06','$whitelist']
    lines += [f"{r['passcode']} {r['copy_limit']} -- {r['name']}" for r in mapped if r['copy_limit']>0]
    (ROOT/'data/processed/reborn.lflist.conf').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
