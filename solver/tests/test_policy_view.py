import unittest

from reborn.policy_view import policy_prompt_view, assert_no_hidden_code_leak
from reborn.protocol import Action, CardRef, Decision
from reborn.observation import LOCATION_DECK, LOCATION_MZONE


def observation():
    blank_m = [{'sequence': i, 'present': False} for i in range(7)]
    blank_s = [{'sequence': i, 'present': False} for i in range(8)]
    p0 = {
        'player': 0, 'lp': 8000, 'deck_count': 35, 'hand_count': 5,
        'grave_count': 0, 'removed_count': 0, 'extra_count': 0, 'extra_faceup_count': 0,
        'mzone': [dict(x) for x in blank_m], 'szone': [dict(x) for x in blank_s],
        'hand': [{'code': i + 1} for i in range(5)], 'grave': [], 'removed': [], 'extra': [],
    }
    p1 = {
        'player': 1, 'lp': 8000, 'deck_count': 35, 'hand_count': 5,
        'grave_count': 0, 'removed_count': 0, 'extra_count': 0, 'extra_faceup_count': 0,
        'mzone': [dict(x) for x in blank_m], 'szone': [dict(x) for x in blank_s],
        'hand': [{'hidden': True} for _ in range(5)], 'grave': [], 'removed': [], 'extra': [],
    }
    p1['mzone'][0] = {
        'sequence': 0, 'present': True, 'position': 8, 'overlay_count': 0,
        'card': {'position': 8, 'is_public': False, 'is_hidden': False},
    }
    return {'viewer': 0, 'players': [p0, p1], 'chains': []}


class PolicyViewTests(unittest.TestCase):
    def test_opponent_facedown_prompt_code_is_removed(self):
        hidden = CardRef(999, 1, LOCATION_MZONE, 0, 8)
        decision = Decision('select_card', 0, cards=(hidden,), minimum=1, maximum=1)
        obs = observation()
        view = policy_prompt_view(decision, obs)
        self.assertNotIn('code', view['cards'][0])
        self.assertTrue(assert_no_hidden_code_leak(view, obs))

    def test_own_deck_selection_is_prompt_disclosure(self):
        own_search = CardRef(777, 0, LOCATION_DECK, 12, 8)
        decision = Decision('select_card', 0, cards=(own_search,), minimum=1, maximum=1)
        view = policy_prompt_view(decision, observation())
        self.assertEqual(view['cards'][0]['code'], 777)

    def test_unsafe_action_extra_is_not_forwarded(self):
        card = CardRef(123, 0, LOCATION_DECK, 1, 8)
        action = Action('test', b'\x00', card=card, extra={'code': 555, 'index': 3})
        decision = Decision('test', 0, actions=(action,))
        view = policy_prompt_view(decision, observation())
        self.assertNotIn('code', {k: v for k, v in view['actions'][0].items() if k != 'card'})
        self.assertEqual(view['actions'][0]['index'], 3)


if __name__ == '__main__':
    unittest.main()
