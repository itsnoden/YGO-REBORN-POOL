import unittest

from reborn.rule_tag_context_ab_eval import RuleTagContextPolicy


def observation():
    return {
        'viewer': 0,
        'phase': 4,
        'turn_player': 0,
        'chains': [],
        'players': [
            {
                'lp': 8000, 'hand_count': 2, 'grave_count': 0,
                'mzone': [], 'szone': [],
            },
            {
                'lp': 8000, 'hand_count': 2, 'grave_count': 0,
                'mzone': [
                    {'present': True, 'card': {'code': 777, 'position': 1}},
                    {'present': True, 'card': {'position': 8}},
                ],
                'szone': [],
            },
        ],
    }


class RuleTagContextTests(unittest.TestCase):
    def setUp(self):
        self.policy = RuleTagContextPolicy(
            seed=1,
            passcode_tags={
                123: ('draw', 'search'),
                777: ('restriction',),
                999: ('burn',),
            },
        )

    def test_action_card_gets_neutral_rule_tags(self):
        features = self.policy.action_features(
            {'kind': 'idle'}, observation(),
            {'label': 'activate', 'card': {'code': 123}},
        )
        self.assertIn('action_rule_tag:draw|activate', features)
        self.assertIn('action_rule_tag:search|activate', features)

    def test_public_opponent_rule_tag_conditions_action(self):
        features = self.policy.action_features(
            {'kind': 'yesno'}, observation(),
            {'label': 'yes', 'description': 55},
        )
        self.assertIn(
            'opp_rule_ctx:restriction|kind_label:yesno|yes',
            features,
        )

    def test_hidden_opponent_card_does_not_supply_tags(self):
        obs = observation()
        obs['players'][1]['mzone'].append(
            {'present': True, 'card': {'position': 8}}
        )
        features = self.policy.action_features(
            {'kind': 'yesno'}, obs,
            {'label': 'yes', 'description': 55},
        )
        self.assertFalse(any('burn' in f for f in features))


if __name__ == '__main__':
    unittest.main()
