"""Policy-driven legal pilot that learns only from filtered self-play data."""
from __future__ import annotations

from collections import Counter

from .effects import UnsupportedInteraction
from .learning import PolicyStep
from .legal_options import enumerate_policy_options
from .pilot import StochasticLegalPilot


class LearningPilot:
    def __init__(self, policy, seed=1, max_complex_options=512):
        self.policy = policy
        self.fallback = StochasticLegalPilot(seed)
        self.max_complex_options = int(max_complex_options)
        self.steps = []
        self.learned_decisions = 0
        self.complex_learned_decisions = 0
        self.fallback_decisions = 0
        self.fallback_kinds = Counter()

    def reset_episode(self):
        self.steps = []
        self.learned_decisions = 0
        self.complex_learned_decisions = 0
        self.fallback_decisions = 0
        self.fallback_kinds = Counter()

    def _learn(self, player, option_features):
        if not option_features:
            raise UnsupportedInteraction('learning pilot received empty option set')
        chosen = self.policy.sample(option_features)
        self.steps.append(PolicyStep(player, option_features, chosen))
        self.learned_decisions += 1
        return chosen

    def choose(self, decision, prompt, observation):
        if prompt.get('player') != decision.player or observation.get('viewer') != decision.player:
            raise UnsupportedInteraction('learning pilot received mismatched player data')

        # First expand implicit combinatorial response families when (and only
        # when) their complete legal action set is bounded. Raw legality helpers
        # are used inside legal_options.py but never enter the option view or
        # policy features.
        complex_options = enumerate_policy_options(
            decision, prompt, max_options=self.max_complex_options
        )
        if complex_options is not None:
            option_features = [
                self.policy.complex_features(prompt, observation, option.view)
                for option in complex_options
            ]
            chosen = self._learn(decision.player, option_features)
            self.complex_learned_decisions += 1
            return complex_options[chosen].response

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
            chosen = self._learn(decision.player, option_features)
            return decision.actions[chosen].response

        # Unbounded combinatorial prompts stay on the seeded legal fallback. The
        # information-safe observation, not raw prompt/referee metadata, is sent
        # to that fallback. Track the exact remaining families so future work can
        # target the real uncovered strategic surface.
        self.fallback_decisions += 1
        self.fallback_kinds[decision.kind] += 1
        return self.fallback.choose(decision, observation)

    def finish(self, winner):
        self.policy.update_episode(self.steps, winner)
