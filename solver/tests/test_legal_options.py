import json
import unittest

from reborn.legal_options import enumerate_policy_options
from reborn.protocol import CardRef, Decision
from reborn.protocol_extra import (
    encode_sum_selection,
    encode_tribute_selection,
)


def card(code, sequence, controller=0, location=4):
    return CardRef(code, controller, location, sequence, 1)


def safe_card(ref):
    return {
        'controller': ref.controller,
        'location': ref.location,
        'sequence': ref.sequence,
        'position': ref.position,
        'code': ref.code,
    }


def prompt_for(decision, *, meta=None):
    return {
        'kind': decision.kind,
        'player': decision.player,
        'minimum': decision.minimum,
        'maximum': decision.maximum,
        'cancelable': decision.cancelable,
        'actions': [],
        'cards': [safe_card(c) for c in decision.cards],
        'meta': {} if meta is None else meta,
    }


class LegalOptionTests(unittest.TestCase):
    def test_tribute_enumerates_only_legal_subsets_without_release_values(self):
        cards = (card(101, 0), card(102, 1), card(103, 2))
        decision = Decision(
            'tribute', 0, cards=cards, minimum=2, maximum=2,
            meta={'release_values': [1, 2, 1]},
        )
        prompt = prompt_for(decision)
        options = enumerate_policy_options(decision, prompt)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 4)
        for option in options:
            # Every returned response must be one accepted by the strict encoder.
            indices = option.view['selected_indices']
            self.assertEqual(option.response, encode_tribute_selection(decision, indices))
            serialized = json.dumps(option.view, sort_keys=True)
            self.assertNotIn('release_values', serialized)
            self.assertNotIn('release_param', serialized)

    def test_place_enumerates_complete_safe_zone_set(self):
        places = [(0, 4, 0), (0, 4, 1), (0, 8, 0)]
        decision = Decision(
            'select_place', 0, minimum=1, maximum=1,
            meta={'places': places},
        )
        options = enumerate_policy_options(
            decision, prompt_for(decision, meta={'places': list(places)})
        )
        self.assertEqual(len(options), 3)
        self.assertEqual(
            {tuple(option.view['places'][0]) for option in options},
            set(places),
        )

    def test_sort_three_cards_exposes_all_six_permutations(self):
        cards = (card(201, 0), card(202, 1), card(203, 2))
        decision = Decision('sort_card', 0, cards=cards, meta={'count': 3})
        options = enumerate_policy_options(decision, prompt_for(decision))
        self.assertEqual(len(options), 6)
        self.assertEqual(
            {tuple(option.view['order']) for option in options},
            {
                (0, 1, 2), (0, 2, 1), (1, 0, 2),
                (1, 2, 0), (2, 0, 1), (2, 1, 0),
            },
        )

    def test_select_sum_uses_raw_params_only_as_legality_oracle(self):
        cards = (card(301, 0), card(302, 1))
        decision = Decision(
            'select_sum', 0, cards=cards, minimum=1, maximum=2,
            meta={
                'mode': 0,
                'accumulator': 3,
                'must_cards': [],
                'must_params': [],
                'sum_params': [1, 2],
            },
        )
        prompt = prompt_for(decision, meta={'mode': 0, 'accumulator': 3})
        options = enumerate_policy_options(decision, prompt)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 1)
        option = options[0]
        self.assertEqual(option.view['selected_indices'], [0, 1])
        self.assertEqual(option.response, encode_sum_selection(decision, [0, 1]))
        serialized = json.dumps(option.view, sort_keys=True)
        self.assertNotIn('sum_params', serialized)
        self.assertNotIn('must_params', serialized)

    def test_large_multicard_prompt_returns_none_instead_of_truncating(self):
        cards = tuple(card(400 + i, i, location=2) for i in range(13))
        decision = Decision(
            'select_card', 0, cards=cards, minimum=6, maximum=6,
        )
        self.assertIsNone(enumerate_policy_options(decision, prompt_for(decision)))

    def test_announce_bits_enumerates_all_combinations(self):
        available = 0b1011
        decision = Decision(
            'announce_race', 0, minimum=2, maximum=2,
            meta={'available': available},
        )
        options = enumerate_policy_options(
            decision, prompt_for(decision, meta={'available': available})
        )
        self.assertEqual(len(options), 3)
        self.assertEqual(
            {option.view['announced_mask'] for option in options},
            {0b0011, 0b1001, 0b1010},
        )


if __name__ == '__main__':
    unittest.main()
