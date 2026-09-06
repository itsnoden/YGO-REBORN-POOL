"""Exercise real engine initialization/first decision; NEVER a win-rate test."""
import argparse
import json
from .import_pool import ROOT,dump
from .ocgcore import Duel
from .search import validate


def main():
    p=argparse.ArgumentParser();p.add_argument('--library',required=True);p.add_argument('--database',required=True)
    p.add_argument('--scripts',required=True);p.add_argument('--count',type=int,default=8);a=p.parse_args()
    cards={c['id']:c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped={r['reborn_id']:r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    candidates=json.loads((ROOT/'data/processed/candidates-20260906.json').read_text())['candidates']
    results=[]
    for candidate in candidates:
        if len(results)>=a.count:break
        deck=[cid for cid,n in candidate['main'].items() for _ in range(n)]
        if any(cid not in mapped for cid in deck):continue
        validate(deck,cards)
        row=dict(candidate=candidate['id'],seed=1000+len(results),status='pending')
        try:
            with Duel(a.library,a.database,a.scripts,seed=row['seed']) as duel:
                for player in (0,1):
                    for index,cid in enumerate(deck):duel.add(mapped[cid]['passcode'],player,sequence=index)
                duel.start();message_types=[]
                for _ in range(100):
                    status,messages=duel.process();message_types.extend(m[0] for m in messages)
                    if status!=2:break
                row.update(status='reached_decision' if status==1 else 'ended_or_budget',
                    engine_status=status,message_types=message_types,logs=duel.logs,
                    hand_counts=[duel.count(p,2) for p in (0,1)],flags=duel.flags)
        except Exception as exc:row.update(status='blocked',error=f'{type(exc).__name__}: {exc}')
        results.append(row)
    dump(ROOT/'reports/engine_smoke.json',dict(profile='experimental_current_tcg_not_reborn_confirmed',
        results=results,completed_duels=0,note='Initial draw and first decision only. No piloting or strength evidence.'))
    print(json.dumps({'attempted':len(results),'reached_decision':sum(r['status']=='reached_decision' for r in results),
                      'blocked':sum(r['status']=='blocked' for r in results)}))


if __name__=='__main__':main()
