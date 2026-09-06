"""Join exact Reborn titles to standard EDOPro IDs; audit text/script coverage."""
import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path
from .import_pool import ROOT,dump,key


def text_key(text):
    return ' '.join(text.replace('\r',' ').split())


def main():
    p=argparse.ArgumentParser();p.add_argument('--database',required=True)
    p.add_argument('--scripts',required=True);p.add_argument('--core',required=True);a=p.parse_args()
    db=Path(a.database).resolve();scripts=Path(a.scripts).resolve();core=Path(a.core).resolve()
    con=sqlite3.connect(db);con.row_factory=sqlite3.Row
    records={}
    for r in con.execute('SELECT d.*,t.name,t.desc FROM datas d JOIN texts t USING(id)'):
        records.setdefault(key(r['name']),[]).append(dict(r))
    cards=json.loads((ROOT/'data/processed/cards.json').read_text());mapped=[];missing=[]
    for c in cards:
        matches=records.get(key(c['name']),[])
        # Standard card only; alternate art can alias to the same primary.
        primary=matches if len(matches)==1 else [r for r in matches if r['alias']==0]
        if len(primary)!=1:
            missing.append(dict(id=c['id'],name=c['name'],candidate_ids=[r['id'] for r in matches]));continue
        r=primary[0];script=scripts/'official'/f"c{r['id']}.lua"
        is_normal=bool(r['type']&0x10) and not bool(r['type']&0x20)
        text_match=bool(c['official']) and text_key(c['official']['text'])==text_key(r['desc'])
        entry=dict(reborn_id=c['id'],name=c['name'],passcode=r['id'],copy_limit=c['copy_limit'],
             data={k:v for k,v in r.items() if k not in ('name','desc')},
             script_path=f"official/c{r['id']}.lua" if script.exists() else None,
             script_sha256=hashlib.sha256(script.read_bytes()).hexdigest() if script.exists() else None,
             normal_monster=is_normal,official_text_match=text_match,
             engine_text=r['desc'],latest_official_text_sha256=c['official']['text_sha256'] if c['official'] else None,
             status='upstream_script_unvalidated' if script.exists() else ('normal_monster_no_script' if is_normal else 'missing_script'))
        mapped.append(entry)
        c['engine']={k:v for k,v in entry.items() if k not in ('data','engine_text')}
        c['deck_name_group']=str(r['alias'] or r['id'])
        # Placement is determined by authoritative official text when present;
        # do not silently promote missing official matches using simulator data.
    dump(ROOT/'data/processed/cards.json',cards)
    dump(ROOT/'data/processed/engine_cards.json',mapped)
    locks={}
    for name,path,url in [('core',core,'https://github.com/edo9300/ygopro-core.git'),
                          ('scripts',scripts,'https://github.com/ProjectIgnis/CardScripts.git'),
                          ('database',db.parent,'https://github.com/ProjectIgnis/BabelCDB.git')]:
        locks[name]=dict(url=url,commit=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip())
    dump(ROOT/'engine.lock.json',locks)
    dump(ROOT/'reports/engine_coverage.json',dict(mapped=len(mapped),unmapped=missing,
        scripts=sum(bool(r['script_path']) for r in mapped),
        normal_without_script=sum(r['status']=='normal_monster_no_script' for r in mapped),
        missing_script=[r['name'] for r in mapped if r['status']=='missing_script'],
        exact_official_text_matches=sum(r['official_text_match'] for r in mapped),
        text_differences=[r['name'] for r in mapped if not r['official_text_match']],
        certified_interactions=0,note='Upstream implementation availability is not Reborn correctness certification.'))
    # Whitelist mode is crucial: cards not present here must not default to 3.
    lines=['# Reborn exact pool; latest standard scripts only','!Reborn solver 2026-09-06','$whitelist']
    lines += [f"{r['passcode']} {r['copy_limit']} -- {r['name']}" for r in mapped if r['copy_limit']>0]
    (ROOT/'data/processed/reborn.lflist.conf').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
