import random
import unittest
from collections import Counter

from reborn.structural_mutation import (
    add_target_copies, duplicate_consolidation, relation_pair_injection,
)
from reborn.search import validate


def cards(n=50):
    return {
        f'c{i:02d}': {
            'placement': 'main',
            'copy_limit': 3,
            'deck_name_group': f'c{i:02d}',
        }
        for i in range(n)
    }


class StructuralMutationTests(unittest.TestCase):
    def setUp(self):
        self.cards = cards()
        self.deck = tuple(f'c{i:02d}' for i in range(40))
        validate(list(self.deck), self.cards)

    def test_add_target_copies_reaches_three_when_legal(self):
        out, changed = add_target_copies(
            self.deck, self.cards, 'c00', random.Random(1), desired_total=3
        )
        self.assertEqual(Counter(out)['c00'], 3)
        self.assertEqual(changed, 2)
        validate(list(out), self.cards)

    def test_duplicate_consolidation_keeps_40_card_legality(self):
        out, meta = duplicate_consolidation(
            self.deck, self.cards, random.Random(2)
        )
        self.assertEqual(len(out), 40)
        self.assertEqual(meta['method'], 'duplicate_consolidation')
        self.assertGreater(meta['copies_added'], 0)
        validate(list(out), self.cards)

    def test_relation_pair_injection_uses_graph_only_as_proposal(self):
        graph = {
            'relations': [['send_gy', 'gy_trigger']],
            'tag_indexes': {
                'send_gy': ['c41'],
                'gy_trigger': ['c42'],
            },
        }
        out, meta = relation_pair_injection(
            self.deck, self.cards, graph, random.Random(3), desired_each=2
        )
        counts = Counter(out)
        self.assertEqual(counts['c41'], 2)
        self.assertEqual(counts['c42'], 2)
        self.assertEqual(meta['relation_status'], 'unverified_text_hypothesis_only')
        validate(list(out), self.cards)


if __name__ == '__main__':
    unittest.main()
