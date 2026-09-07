"""Policy-driven legal pilot that learns only from filtered self-play data."""
from __future__ import annotations

from .effects import UnsupportedInteraction
from .learning import PolicyStep
from .pilot import StochasticLegalPilot
from .protocol import encode_card_selection


class LearningPilot:
    def __init__(self, policy, seed=1):
        self.policy = policy
        self.fallback = StochasticLegalPilot(seed)
        self.steps = []
        self.learned_decisions = 0
        self.fallback_decisions = 0

    def reset_episode(self):
        self.steps = []
        self.learned_decisions = 0
        self.fallback_decisions = 0

    def choose(self, decision, prompt, observation):
        if prompt.get('player') != decision.player or observation.get('viewer') != decision.player:
            raise UnsupportedInteraction('learning pilot received mismatched player data')

        # Most strategic engine prompts already expose an explicit legal action
        # list. Score only the filtered policy-view actions; use the raw Decision
        # solely after selection to retrieve the opaque response bytes.
        if decision.actions:
            if len(prompt.get('actions', ())) != len(decision.actions):
                raise UnsupportedInteraction('filtered action count differs from referee action count')
            option_features = [
                self.policy.action_features(prompt, observation, action)
                for action in prompt['actions']
            ]
            chosen = self.policy.sample(option_features)
            self.steps.append(PolicyStep(decision.player, option_features, chosen))
            self.learned_decisions += 1
            return decision.actions[chosen].response

        # Single-card targeting/search prompts can be learned safely too. The
        # candidate code is present only when policy_view judged it visible.
        if decision.kind == 'select_card' and decision.minimum == 1 and decision.maximum == 1 and decision.cards:
            if len(prompt.get('cards', ())) != len(decision.cards):
                raise UnsupportedInteraction('filtered card count differs from referee card count')
            option_features = [
                self.policy.card_features(prompt, observation, card)
                for card in prompt['cards']
            ]
            chosen = self.policy.sample(option_features)
            self.steps.append(PolicyStep(decision.player, option_features, chosen))
            self.learned_decisions += 1
            return encode_card_selection(decision, [chosen])

        # Complex combinatorial legality (sum/counter/tribute/multi-card/place)
        # stays in a non-learning legal fallback until it has a safe action-set
        # enumerator. Pass the information-safe observation, not the prompt; the
        # fallback's privacy assertion is intentionally keyed to observation.viewer.
        self.fallback_decisions += 1
        return self.fallback.choose(decision, observation)

    def finish(self, winner):
        self.policy.update_episode(self.steps, winner)
