"""Algorithmic proposals only. Surrogate prioritizes experiments, never wins."""
import argparse
import collections
import hashlib
import json
import random
from .import_pool import ROOT,dump
from .mine import RELATIONS


def canonical(deck):return tuple(sorted(deck))


def group_counts(deck,cards):
    return collections.Counter(cards[c].get('deck_name_group',c) for c in deck)


def available(deck,cards):
    counts=collections.Counter(deck);groups=group_counts(deck,cards)
    return [cid for cid,c in cards.items() if counts[cid]<c['copy_limit']
            and groups[c.get('deck_name_group',cid)]<3]


def validate(deck,cards):
    if len(deck)!=40:raise ValueError('Main Deck must contain exactly 40 cards')
    for cid,n in collections.Counter(deck).items():
        if cid not in cards:raise ValueError(f'Outside pool: {cid}')
        c=cards[cid]
        if c['placement']!='main':raise ValueError(f'Unverified or non-Main Deck placement: {cid}')
        if n>c['copy_limit']:raise ValueError(f'Copy limit exceeded: {cid}')
    if any(n>3 for n in group_counts(deck,cards).values()):
        raise ValueError('Shared card-name deck limit exceeded')
    return True


def fill(seed,cards,rng):
    deck=list(seed)
    for cid,n in collections.Counter(deck).items():
        if cid not in cards or n>cards[cid]['copy_limit']:raise ValueError('Invalid seed')
    if len(deck)>40:raise ValueError('Seed over 40')
    while len(deck)<40:
        options=available(deck,cards)
        if not options:raise ValueError('Insufficient legal capacity')
        deck.append(rng.choice(options))
    return canonical(deck)


def mutate(deck,cards,rng,n=1):
    if not 0<n<=len(deck):raise ValueError('Invalid mutation size')
    remaining=list(deck)
    for i in sorted(rng.sample(range(len(deck)),n),reverse=True):remaining.pop(i)
    return fill(remaining,cards,rng)


def crossover(a,b,cards,rng):
    merged=list(a+b);rng.shuffle(merged);child=[];counts=collections.Counter()
    for cid in merged:
        if cid in available(child,cards) and len(child)<40:
            child.append(cid);counts[cid]+=1
    return fill(child,cards,rng)


def proxy(deck,tags):
    # Number of potential distinct producer/consumer relationships. Not power.
    ids=set(deck)
    return sum(1 for a in ids for b in ids if a!=b
               for x,y in RELATIONS if x in tags.get(a,set()) and y in tags.get(b,set()))


def beam_seeds(cards,tags,rng,width=8,depth=6):
    ids=list(cards)
    beam=[(rng.choice(ids),) for _ in range(width)]
    for _ in range(depth-1):
        proposals=set()
        for deck in beam:
            for cid in rng.sample(ids,min(80,len(ids))):
                if cid in available(deck,cards):
                    proposals.add(canonical(deck+(cid,)))
        beam=sorted(proposals,key=lambda d:(-proxy(d,tags),d))[:width]
    return beam


def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=20260906)
    p.add_argument('--population',type=int,default=256);args=p.parse_args()
    allcards=json.loads((ROOT/'data/processed/cards.json').read_text())
    cards={c['id']:c for c in allcards if c['legal'] and c['placement']=='main'}
    if sum(c['copy_limit'] for c in cards.values())<40:raise ValueError('Not enough verified Main Deck cards')
    tags={r['id']:set(r['tags']) for r in json.loads((ROOT/'data/processed/screening.json').read_text())}
    rng=random.Random(args.seed);population={}
    def add(deck,method):
        validate(deck,cards);population.setdefault(deck,method)
    # Mandatory all-card exposure; no popularity/type/theme prefilter.
    ids=list(cards);rng.shuffle(ids)
    seed=[]
    for cid in ids:
        if len(seed)==40 or cid not in available(seed,cards):
            add(fill(seed,cards,rng),'coverage_restart');seed=[]
        seed.append(cid)
    if seed:add(fill(seed,cards,rng),'coverage_restart')
    for seed in beam_seeds(cards,tags,rng):add(fill(seed,cards,rng),'graph_beam')
    while len(population)<args.population:
        mode=len(population)%4
        if mode==0:deck=fill([],cards,rng);method='random_restart'
        else:
            parents=list(population)
            if mode==1:deck=mutate(rng.choice(parents),cards,rng,1);method='one_card_mutation'
            elif mode==2:deck=mutate(rng.choice(parents),cards,rng,2);method='two_card_mutation'
            else:
                sampled=rng.sample(parents,min(12,len(parents)))
                sampled.sort(key=lambda d:proxy(d,tags),reverse=True)
                deck=crossover(sampled[0],sampled[1],cards,rng);method='genetic_proxy'
        add(deck,method)
    rows=[]
    for deck,method in population.items():
        identity=hashlib.sha256('|'.join(deck).encode()).hexdigest()[:16]
        rows.append(dict(id=identity,main=dict(collections.Counter(deck)),method=method,
                         status='legal_untested_proposal',hypothesis_density=proxy(deck,tags),
                         win_rate=None,ftk_rate=None,otk_rate=None,brick_rate=None,
                         recovery=None,card_advantage=None,worst_matchup=None,
                         going_first=None,going_second=None))
    used={cid for deck in population for cid in deck}
    dump(ROOT/f'data/processed/candidates-{args.seed}.json',dict(seed=args.seed,
        card_database_sha256=hashlib.sha256((ROOT/'data/processed/cards.json').read_bytes()).hexdigest(),
        candidates=rows))
    dump(ROOT/'reports/candidates.json',dict(seed=args.seed,population=len(rows),
        methods=dict(collections.Counter(population.values())),eligible_main_cards=len(cards),
        main_cards_exposed=len(used),unexposed=sorted(set(cards)-used),
        blocked_unknown_placement=[c['id'] for c in allcards if c['legal'] and c['placement'] is None],
        certified_duels=0,current_number_one=None,
        note='Hypothesis density is not a strength estimate. No deck has been promoted.'))


if __name__=='__main__':main()
