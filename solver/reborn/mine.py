"""Full-pool text screening. ALL output is an unverified hypothesis layer."""
import collections
import hashlib
import json
import re
from .import_pool import ROOT, dump, key

# Positive and negative wording can co-occur. These tags deliberately cannot
# authorize effects: the complete clause must be compiled and tested first.
PATTERNS = {
 'draw':r'\bdraw\b', 'search':r'(?:add|place).{0,100}(?:Deck|deck).{0,60}(?:hand|top)',
 'discard':r'\bdiscard', 'send_gy':r'(?:send|sent).{0,140}(?:GY|Graveyard)',
 'summon':r'Special Summon', 'revive':r'Special Summon.{0,180}(?:GY|Graveyard)',
 'summon_trigger':r'(?:If|When).{0,100}(?:is|are) (?:Normal or Special |Special |Normal )?Summoned',
 'gy_trigger':r'(?:If|When).{0,100}(?:sent|send).{0,100}(?:GY|Graveyard)',
 'tribute':r'\bTribute|\bTributing', 'burn':r'inflict.{0,100}damage',
 'banish':r'banish|remove.{0,30}from play', 'recover_banished':r'(?:Special Summon|add|return).{0,160}(?:banished|removed from play)',
 'return_hand':r'return.{0,140}hand', 'spell_recovery':r'(?:Spell.{0,100}(?:GY|Graveyard).{0,100}hand|(?:GY|Graveyard).{0,100}Spell.{0,100}hand)',
 'hand_attack':r'(?:opponent.{0,80}hand|hand.{0,80}opponent)',
 'negate':r'\bnegate', 'restriction':r'cannot|neither player|Neither player',
 'alternate_win':r'win the Duel', 'repeatable_candidate':r'You can.{0,120};',
 'once_turn':r'once per turn|1 .{0,80}per turn', 'once_duel':r'once per Duel',
 'delay':r'End Phase|Standby Phase|next turn|except the turn|the turn this card was sent',
 'replacement':r'\binstead\b', 'battle_amplifier':r'ATK.{0,100}(?:double|gain)|(?:double|gain).{0,100}ATK|attack.{0,50}(?:twice|second|all)',
}

# An edge is an investigation queue item, not evidence of compatibility.
RELATIONS = [('send_gy','gy_trigger'),('send_gy','revive'),('revive','summon_trigger'),
             ('summon','tribute'),('tribute','gy_trigger'),('banish','recover_banished'),
             ('discard','gy_trigger'),('return_hand','summon_trigger')]


def screen(card):
    official=card.get('official')
    if not official:
        return dict(id=card['id'],status='missing_text',tags=[],evidence={},named_refs=[])
    text=official['text']
    evidence={}
    for tag,pattern in PATTERNS.items():
        m=re.search(pattern,text,re.I)
        if m:evidence[tag]=dict(start=m.start(),end=m.end())
    return dict(id=card['id'],status='screened_not_implemented',tags=sorted(evidence),evidence=evidence,
                text_sha256=official['text_sha256'],named_refs=re.findall(r'"([^"\n]+)"',text))


def main():
    cards=json.loads((ROOT/'data/processed/cards.json').read_text())
    legal=[c for c in cards if c['legal']]
    screens=[screen(c) for c in legal]
    indexes=collections.defaultdict(list)
    for row in screens:
        for tag in row['tags']:indexes[tag].append(row['id'])
    byname={key(c['name']):c['id'] for c in legal}
    named_edges=sorted({(row['id'],byname[key(name)]) for row in screens for name in row['named_refs']
                       if key(name) in byname and row['id']!=byname[key(name)]})
    # Store the exact relation factorization rather than millions of duplicated
    # edges. Every source/destination pair is recoverable without truncation.
    relation_counts={f'{a}->{b}':len(indexes[a])*len(indexes[b])-len(set(indexes[a])&set(indexes[b]))
                     for a,b in RELATIONS}
    dump(ROOT/'data/processed/screening.json',screens)
    dump(ROOT/'data/processed/synergy_graph.json',dict(status='unverified_text_hypotheses',
        tag_indexes=dict(indexes),relations=RELATIONS,named_edges=named_edges,
        relation_pair_counts=relation_counts))
    themes={
      'ftk_burn':[r['id'] for r in screens if 'burn' in r['tags']],
      'alternate_win':[r['id'] for r in screens if 'alternate_win' in r['tags']],
      'recursive_resources':[r['id'] for r in screens if set(r['tags'])&{'revive','spell_recovery','recover_banished'}],
      'hand_loops':[r['id'] for r in screens if 'hand_attack' in r['tags']],
      'hard_locks':[r['id'] for r in screens if set(r['tags'])&{'restriction','negate'}],
      'card_advantage':[r['id'] for r in screens if set(r['tags'])&{'draw','search','summon_trigger'}],
      'otk_damage':[r['id'] for r in screens if 'battle_amplifier' in r['tags']],
    }
    dump(ROOT/'reports/mining.json',dict(legal_cards=len(legal),screened=sum(r['status']!='missing_text' for r in screens),
        missing_text=[r['id'] for r in screens if r['status']=='missing_text'],
        category_counts={k:len(v) for k,v in themes.items()},queues=themes,
        relation_pair_counts=relation_counts,named_edges=len(named_edges),
        proven_ftks=0,proven_loops=0,proven_locks=0,
        caveat='Regex includes negated, restricted and mutually incompatible clauses; NEVER score these as actual effect power.'))


if __name__=='__main__':main()
