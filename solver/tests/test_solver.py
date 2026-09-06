import dataclasses
import json
import random
import struct
import unittest
from reborn.import_pool import ROOT,parse_pool,parse_limits,key
from reborn.search import validate,fill,mutate,crossover
from reborn.effects import EffectIR,EffectKind,UnsupportedInteraction,require_supported,UsageLedger
from reborn.ocgcore import split_messages
from reborn.oracle import maximin,wilson_lower


class PoolTests(unittest.TestCase):
    def test_full_exact_import(self):
        cards=parse_pool((ROOT/'data/raw/MASTER.txt').read_text())
        self.assertEqual(len(cards),2273)

    def test_duplicate_or_gap_fails(self):
        text=(ROOT/'data/raw/MASTER.txt').read_text()
        with self.assertRaises(AssertionError):parse_pool(text.replace('002. Book of Moon','001. Backs to the Wall',1))

    def test_authoritative_overrides(self):
        limits=parse_limits((ROOT/'data/raw/BANLIST_MASTER.txt').read_text())
        self.assertEqual(limits[key('Bottomless Trap Hole')],2)
        self.assertEqual(limits[key('Pot of Greed')],0)
        self.assertEqual(limits.get(key('Destiny HERO - Disk Commander'),3),3)


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.cards={str(i):dict(placement='main',copy_limit=3) for i in range(20)}
        self.rng=random.Random(42)

    def test_mutation_and_crossover_conserve_legality(self):
        a=fill([],self.cards,self.rng);b=fill([],self.cards,self.rng)
        for _ in range(50):
            a=mutate(a,self.cards,self.rng,2);b=crossover(a,b,self.cards,self.rng)
            self.assertTrue(validate(a,self.cards));self.assertTrue(validate(b,self.cards))

    def test_forbidden_extra_unknown_rejected(self):
        deck=list(fill([],self.cards,self.rng));cid=deck[0]
        for placement,limit in [('extra',3),(None,3),('main',0)]:
            cards={**self.cards,cid:dict(placement=placement,copy_limit=limit)}
            with self.assertRaises(ValueError):validate(deck,cards)

    def test_shared_name_limit(self):
        cards={**self.cards,'0':dict(placement='main',copy_limit=3,deck_name_group='shared'),
               '1':dict(placement='main',copy_limit=3,deck_name_group='shared')}
        deck=['0','0','1','1']+list(fill([],self.cards,self.rng))[:36]
        with self.assertRaises(ValueError):validate(deck,cards)
        for _ in range(10):self.assertTrue(validate(fill([],cards,self.rng),cards))

    def test_saved_candidates_valid(self):
        path=ROOT/'data/processed/candidates-20260906.json'
        if not path.exists():self.skipTest('Run candidate generation first')
        cards={c['id']:c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
        candidates=json.loads(path.read_text())['candidates']
        for row in candidates:
            validate([c for c,n in row['main'].items() for _ in range(n)],cards)
            self.assertIsNone(row['win_rate'])


class AccuracyTests(unittest.TestCase):
    def test_stale_text_and_missing_rules_block(self):
        effect=EffectIR('c','e','hash',EffectKind.TRIGGER,{},(),(),{},(),{}, {},frozenset({'chain'}),certified=True)
        with self.assertRaises(UnsupportedInteraction):require_supported(effect,'changed',{'chain'})
        with self.assertRaises(UnsupportedInteraction):require_supported(effect,'hash',set())
        with self.assertRaises(UnsupportedInteraction):require_supported(dataclasses.replace(effect,certified=False),'hash',{'chain'})

    def test_name_limit_shared_instances_and_duel_reset(self):
        ledger=UsageLedger();ledger.claim(0,'Disk Commander','draw','duel',1)
        with self.assertRaises(ValueError):ledger.claim(0,'Disk Commander','draw','duel',5)
        ledger.claim(1,'Disk Commander','draw','duel',5)
        ledger.claim(0,'Sangan','search','turn',1);ledger.claim(0,'Sangan','search','turn',2)

    def test_protocol_frames(self):
        self.assertEqual(split_messages(struct.pack('<I',2)+b'\x0b\x00'),[b'\x0b\x00'])
        for data in [b'\x01',struct.pack('<I',5)+b'x',struct.pack('<I',0)]:
            with self.assertRaises(ValueError):split_messages(data)

    def test_no_fake_maximin(self):
        with self.assertRaises(ValueError):maximin({'a':{'b':{}}})
        sample=dict(certified=True,wins=80,games=100,unsupported=1)
        with self.assertRaises(ValueError):maximin({'a':{'b':{'first':sample,'second':sample}}})
        self.assertGreater(wilson_lower(80,100),.70)
        self.assertLess(wilson_lower(80,100),.80)


if __name__=='__main__':unittest.main()
